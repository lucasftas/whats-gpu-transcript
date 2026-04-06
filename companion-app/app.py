import logging
import sys
import threading
import time
import os
import uuid
import winreg
from collections import OrderedDict

from flask import Flask, request, jsonify
from PIL import Image, ImageDraw
from waitress import serve
import pystray

from transcriber import Transcriber
from model_manager import ModelManager
from updater import UpdateChecker

# ---------------------------------------------------------------------------
# Auto-start helpers (Windows Registry)
# ---------------------------------------------------------------------------
_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_NAME = "WhatsGPU"


def _get_exe_path():
    """Return path to the running .exe (or python script for dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(__file__)


def is_autostart_enabled():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _REG_NAME)
        winreg.CloseKey(key)
        return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enabled):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, _REG_NAME, 0, winreg.REG_SZ, _get_exe_path())
        else:
            try:
                winreg.DeleteValue(key, _REG_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error("Erro ao configurar auto-start: %s", e)
        return False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PORT = 8765
DEFAULT_MODEL = "large-v3"

# ---------------------------------------------------------------------------
# Global status (read by /status, written by status callback)
# ---------------------------------------------------------------------------
current_status = {"stage": "idle", "detail": None, "timestamp": time.time()}

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
app = Flask(__name__)
tray_icon = None


def _get_tray_color(stage):
    """Gray=idle/no model, Yellow=loading/working, Green=model ready."""
    if stage in ("loading_model", "transcribing", "downloading_model", "unloading"):
        return (255, 165, 0)  # yellow/orange
    elif stage in ("model_ready", "done") or (stage == "idle" and transcriber.is_loaded):
        return (76, 175, 80)  # green
    else:
        return (150, 150, 150)  # gray


def on_status_change(stage, detail=None):
    """Called by Transcriber/ModelManager whenever the processing stage changes."""
    global current_status
    current_status = {"stage": stage, "detail": detail, "timestamp": time.time()}
    if tray_icon:
        color = _get_tray_color(stage)
        tray_icon.icon = create_icon_image(color)
        labels = {
            "loading_model": "Carregando modelo...",
            "model_ready": "Modelo pronto",
            "transcribing": "Transcrevendo...",
            "done": "Pronto",
            "unloading": "Descarregando...",
            "unloaded": "Sem modelo",
            "oom_error": "Erro GPU",
            "downloading_model": "Baixando modelo...",
            "download_complete": "Download concluído",
            "download_error": "Erro no download",
            "idle": "Sem modelo" if not transcriber.is_loaded else "Pronto",
        }
        # Add progress % to tooltip on hover
        pct = ""
        if isinstance(detail, dict) and "progress_pct" in detail:
            pct = f" {detail['progress_pct']}%"
        tray_icon.title = f"Whats GPU - {labels.get(stage, stage)}{pct}"


transcriber = Transcriber(model_size=DEFAULT_MODEL, status_callback=on_status_change)
model_manager = ModelManager(status_callback=on_status_change)

# ---------------------------------------------------------------------------
# Transcription queue
# ---------------------------------------------------------------------------
_queue_lock = threading.Lock()
_queue_jobs = OrderedDict()  # job_id -> {status, result, error, ...}
_queue_thread = None
_queue_event = threading.Event()


def _queue_worker():
    """Background worker that processes transcription jobs sequentially."""
    while True:
        _queue_event.wait()
        _queue_event.clear()
        while True:
            job = None
            with _queue_lock:
                for jid, j in _queue_jobs.items():
                    if j["status"] == "queued":
                        j["status"] = "processing"
                        job = (jid, j)
                        break
            if not job:
                break
            jid, j = job
            try:
                result = transcriber.transcribe(
                    j["audio_bytes"],
                    filename=j["filename"],
                    precision=j["precision"],
                )
                with _queue_lock:
                    j["status"] = "done"
                    j["result"] = result
                on_status_change("idle")
            except RuntimeError as e:
                with _queue_lock:
                    j["status"] = "error"
                    j["error"] = str(e)
                    j["retry"] = "GPU sem memoria" in str(e)
                on_status_change("idle")
            except Exception as e:
                with _queue_lock:
                    j["status"] = "error"
                    j["error"] = str(e)
                on_status_change("idle")


def _ensure_queue_worker():
    global _queue_thread
    if _queue_thread is None or not _queue_thread.is_alive():
        _queue_thread = threading.Thread(target=_queue_worker, daemon=True)
        _queue_thread.start()


# ---------------------------------------------------------------------------
# Tray icon helpers
# ---------------------------------------------------------------------------
def create_icon_image(color):
    """Create a simple colored circle icon."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    draw.text((size // 2 - 8, size // 2 - 10), "W", fill="white")
    return img


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    from transcriber import get_vram_usage
    data = {
        "status": "ok",
        "model": transcriber.current_model_name,
        "gpu": transcriber.has_gpu,
        "gpu_name": transcriber.gpu_name,
        "gpu_count": len(transcriber.gpus),
        "active_gpu": transcriber.device_index,
        "vram_gb": transcriber.gpu_vram_gb,
        "model_loaded": transcriber.is_loaded,
        "current_stage": current_status["stage"],
    }
    vram = get_vram_usage()
    if vram:
        data.update(vram)
    return jsonify(data)


@app.route("/status", methods=["GET"])
def status():
    return jsonify(current_status)


# ---------------------------------------------------------------------------
# Model management routes
# ---------------------------------------------------------------------------
@app.route("/models", methods=["GET"])
def list_models():
    models = model_manager.list_available(vram_gb=transcriber.gpu_vram_gb)
    return jsonify({
        "models": models,
        "current_model": transcriber.current_model_name,
        "gpu_name": transcriber.gpu_name or "CPU",
        "vram_gb": transcriber.gpu_vram_gb,
        "models_dir": str(model_manager.models_dir),
        "is_downloading": model_manager.is_downloading,
        "downloading_model": model_manager.downloading_model,
    })


@app.route("/models/<name>/download", methods=["POST"])
def download_model(name):
    try:
        model_manager.download(name)
        return jsonify({"status": "downloading"})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409  # conflict - already downloading


@app.route("/models/cancel", methods=["POST"])
def cancel_download():
    if model_manager.cancel_download():
        return jsonify({"status": "cancelling"})
    return jsonify({"error": "Nenhum download em andamento"}), 404


@app.route("/models/<name>", methods=["DELETE"])
def delete_model(name):
    # Don't delete model that's currently loaded
    if transcriber.is_loaded and transcriber.current_model_name == name:
        return jsonify({"error": "Modelo em uso. Clique 'Limpar GPU' antes de remover."}), 409
    if model_manager.delete(name):
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Modelo não encontrado"}), 404


# ---------------------------------------------------------------------------
# GPU model routes
# ---------------------------------------------------------------------------
@app.route("/gpus", methods=["GET"])
def list_gpus():
    return jsonify({
        "gpus": transcriber.gpus,
        "active_gpu": transcriber.device_index,
        "device": transcriber.device,
    })


@app.route("/gpu/select", methods=["POST"])
def select_gpu():
    data = request.get_json(silent=True) or {}
    idx = data.get("index", 0)
    if idx < 0 or idx >= len(transcriber.gpus):
        return jsonify({"error": f"GPU {idx} não disponível"}), 400
    if transcriber.is_loaded:
        return jsonify({"error": "Descarregue o modelo antes de trocar de GPU"}), 409
    transcriber.device_index = idx
    gpu = transcriber.gpus[idx]
    transcriber.gpu_name = gpu["name"]
    transcriber.gpu_vram_gb = gpu["vram_gb"]
    logger.info("GPU selecionada: %d - %s", idx, gpu["name"])
    return jsonify({"status": "ok", "gpu": gpu})


@app.route("/model/load", methods=["POST"])
def model_load():
    # Accept model name from body
    data = request.get_json(silent=True) or {}
    model_name = data.get("model", DEFAULT_MODEL)

    # Check if already loaded with same model
    if transcriber.is_loaded and transcriber.current_model_name == model_name:
        return jsonify({"status": "already_loaded"})
    if current_status["stage"] == "loading_model":
        return jsonify({"status": "loading"})

    # Resolve model path (local or HF)
    model_path = model_manager.get_path(model_name) or model_name

    def _load():
        try:
            transcriber.ensure_model(model_path=model_path)
        except Exception as e:
            logger.error("Erro ao carregar modelo: %s", e)
            on_status_change("idle", {"error": str(e)})

    threading.Thread(target=_load, daemon=True).start()
    return jsonify({"status": "loading"})


@app.route("/model/unload", methods=["POST"])
def model_unload():
    # Fast unload — drop reference immediately, clean GPU in background
    transcriber.model = None
    transcriber._model_path = None
    on_status_change("idle")

    def _cleanup():
        transcriber._clear_gpu()

    threading.Thread(target=_cleanup, daemon=True).start()
    return jsonify({"status": "unloaded"})


# ---------------------------------------------------------------------------
# Transcription route
# ---------------------------------------------------------------------------
LANGUAGE_PROMPTS = {
    "pt": "Transcrição de mensagem de voz do WhatsApp em português brasileiro. Linguagem informal e coloquial.",
    "en": "Transcription of a WhatsApp voice message in English. Informal and colloquial language.",
    "es": "Transcripción de mensaje de voz de WhatsApp en español. Lenguaje informal y coloquial.",
    "fr": "Transcription d'un message vocal WhatsApp en français. Langage informel et familier.",
    "de": "Transkription einer WhatsApp-Sprachnachricht auf Deutsch. Informelle und umgangssprachliche Sprache.",
    "it": "Trascrizione di un messaggio vocale WhatsApp in italiano. Linguaggio informale e colloquiale.",
    "ja": "WhatsApp音声メッセージの日本語文字起こし。カジュアルな会話。",
    "zh": "WhatsApp语音消息的中文转录。非正式口语化语言。",
    "ko": "WhatsApp 음성 메시지의 한국어 전사. 비격식적이고 구어적인 언어.",
    "ru": "Транскрипция голосового сообщения WhatsApp на русском языке. Неформальная разговорная речь.",
    "ar": "نسخ رسالة صوتية من واتساب باللغة العربية. لغة غير رسمية وعامية.",
    "hi": "WhatsApp वॉइस मैसेज का हिंदी में ट्रांसक्रिप्शन। अनौपचारिक और बोलचाल की भाषा।",
}


def _parse_transcribe_params():
    """Parse precision, language, and context from form data."""
    precision = None
    precision_json = request.form.get("precision")
    if precision_json:
        try:
            import json
            precision = json.loads(precision_json)
        except Exception:
            pass

    language = request.form.get("language", "pt").strip()
    if precision is None:
        precision = {}

    if language == "auto":
        precision["language"] = None
    else:
        precision["language"] = language

    context = request.form.get("context", "").strip()
    base_prompt = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["pt"])
    if context:
        base_prompt += " Contexto da conversa: " + context[:300]
    precision["initial_prompt"] = base_prompt

    return precision


@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    audio_bytes = file.read()
    if not audio_bytes:
        return jsonify({"error": "Empty file"}), 400

    precision = _parse_transcribe_params()
    mode = request.form.get("mode", "sync")

    if mode == "async":
        # Queue mode: return job_id immediately
        job_id = str(uuid.uuid4())[:8]
        with _queue_lock:
            _queue_jobs[job_id] = {
                "status": "queued",
                "audio_bytes": audio_bytes,
                "filename": file.filename or "audio.ogg",
                "precision": precision,
                "result": None,
                "error": None,
                "created": time.time(),
            }
        _ensure_queue_worker()
        _queue_event.set()
        return jsonify({"job_id": job_id, "status": "queued"})

    # Sync mode (default — backwards compatible)
    try:
        result = transcriber.transcribe(audio_bytes, filename=file.filename or "audio.ogg", precision=precision)
        on_status_change("idle")
        return jsonify({"text": result["text"], "words": result["words"]})
    except RuntimeError as e:
        on_status_change("idle")
        if "GPU sem memoria" in str(e):
            logger.error("OOM durante transcricao: %s", e)
            return jsonify({"error": str(e), "retry": True}), 503
        logger.error("Erro na transcricao: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        on_status_change("idle")
        logger.error("Erro na transcricao: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/transcribe/<job_id>", methods=["GET"])
def get_transcription_job(job_id):
    """Check status of an async transcription job."""
    with _queue_lock:
        job = _queue_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado"}), 404
    if job["status"] == "done":
        result = job["result"]
        # Clean up completed job
        with _queue_lock:
            _queue_jobs.pop(job_id, None)
        return jsonify({"status": "done", "text": result["text"], "words": result["words"]})
    if job["status"] == "error":
        error = job["error"]
        retry = job.get("retry", False)
        with _queue_lock:
            _queue_jobs.pop(job_id, None)
        code = 503 if retry else 500
        return jsonify({"status": "error", "error": error, "retry": retry}), code
    # queued or processing
    position = 0
    with _queue_lock:
        for jid, j in _queue_jobs.items():
            if j["status"] == "queued":
                position += 1
            if jid == job_id:
                break
    return jsonify({"status": job["status"], "position": position})


@app.route("/queue", methods=["GET"])
def get_queue():
    """Return current queue status."""
    with _queue_lock:
        jobs = [
            {"id": jid, "status": j["status"], "created": j["created"]}
            for jid, j in _queue_jobs.items()
        ]
    return jsonify({"jobs": jobs, "count": len(jobs)})


# ---------------------------------------------------------------------------
# Ensemble transcription
# ---------------------------------------------------------------------------
@app.route("/transcribe/ensemble", methods=["POST"])
def transcribe_ensemble():
    """Transcribe with two models and merge results by word confidence."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    audio_bytes = file.read()
    if not audio_bytes:
        return jsonify({"error": "Empty file"}), 400

    precision = _parse_transcribe_params()

    # Get the two models to use
    import json
    models_json = request.form.get("models", "[]")
    try:
        model_names = json.loads(models_json)
    except Exception:
        model_names = []

    if len(model_names) < 2:
        return jsonify({"error": "Especifique pelo menos 2 modelos"}), 400

    # Verify both models are downloaded
    for name in model_names[:2]:
        if not model_manager.is_downloaded(name):
            return jsonify({"error": f"Modelo {name} não está baixado"}), 400

    results = []
    try:
        for name in model_names[:2]:
            model_path = model_manager.get_path(name)
            on_status_change("loading_model", f"Ensemble: carregando {name}...")
            transcriber.ensure_model(model_path=model_path)
            result = transcriber.transcribe(
                audio_bytes,
                filename=file.filename or "audio.ogg",
                precision=precision,
            )
            results.append({"model": name, **result})

        # Merge: pick words with highest confidence from either model
        merged = _merge_ensemble(results)
        on_status_change("idle")
        return jsonify(merged)
    except RuntimeError as e:
        on_status_change("idle")
        if "GPU sem memoria" in str(e):
            return jsonify({"error": str(e), "retry": True}), 503
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        on_status_change("idle")
        return jsonify({"error": str(e)}), 500


def _merge_ensemble(results):
    """Merge results from multiple models by picking highest-confidence words."""
    if not results:
        return {"text": "", "words": [], "ensemble": True}

    # Find the result with most words as the base
    best = max(results, key=lambda r: len(r.get("words", [])))
    other = [r for r in results if r is not best]

    if not other or not best.get("words"):
        return {"text": best["text"], "words": best.get("words", []), "ensemble": True, "models": [r["model"] for r in results]}

    # Build word lookup by approximate time for the other model
    other_words = other[0].get("words", [])
    merged_words = []

    for w in best["words"]:
        # Find closest word in other model's output by timestamp
        best_match = None
        best_dist = float("inf")
        for ow in other_words:
            dist = abs(w["start"] - ow["start"])
            if dist < best_dist:
                best_dist = dist
                best_match = ow

        # If close enough in time (< 0.5s) and other model has higher confidence, use it
        if best_match and best_dist < 0.5 and best_match["confidence"] > w["confidence"]:
            merged_words.append({
                **best_match,
                "source": other[0]["model"],
            })
        else:
            merged_words.append({
                **w,
                "source": best["model"],
            })

    merged_text = " ".join(w["word"] for w in merged_words)
    avg_confidence = sum(w["confidence"] for w in merged_words) / len(merged_words) if merged_words else 0

    return {
        "text": merged_text,
        "words": merged_words,
        "ensemble": True,
        "models": [r["model"] for r in results],
        "avg_confidence": round(avg_confidence, 3),
    }


@app.route("/update/check", methods=["GET"])
def check_update():
    from updater import check_for_update
    update = check_for_update()
    if update:
        return jsonify({"available": True, **update})
    return jsonify({"available": False})


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------
def run_server():
    logger.info("Servidor iniciando em 127.0.0.1:%d", PORT)
    logger.info("GPU: %s (%s GB VRAM)" if transcriber.has_gpu else "GPU: nao detectada",
                transcriber.gpu_name, transcriber.gpu_vram_gb)
    serve(app, host="127.0.0.1", port=PORT, threads=4, channel_timeout=300)


# ---------------------------------------------------------------------------
# Tray menu actions
# ---------------------------------------------------------------------------
def on_quit(icon, item):
    # Fast exit — drop model ref, stop icon, kill process
    transcriber.model = None
    icon.stop()
    os._exit(0)


def on_unload_model(icon, item):
    """Unload model from GPU via tray menu."""
    if transcriber.is_loaded:
        logger.info("Descarregando modelo via tray...")
        transcriber.model = None
        transcriber._model_path = None
        on_status_change("idle")
        threading.Thread(target=transcriber._clear_gpu, daemon=True).start()


def on_toggle_autostart(icon, item):
    new_state = not is_autostart_enabled()
    set_autostart(new_state)
    logger.info("Auto-start %s", "ativado" if new_state else "desativado")


# ---------------------------------------------------------------------------
# Update checker integration
# ---------------------------------------------------------------------------
_update_info = {"available": False, "data": None}


def _on_update_available(update):
    _update_info["available"] = True
    _update_info["data"] = update
    if tray_icon:
        tray_icon.title = f"Whats GPU - Atualização disponível: {update['version']}"


def on_download_update(icon, item):
    if _update_info["data"]:
        UpdateChecker.open_download(_update_info["data"])


def _vram_label(item):
    """Dynamic label showing current VRAM usage."""
    from transcriber import get_vram_usage
    vram = get_vram_usage()
    if vram:
        used_gb = round(vram["vram_used_mb"] / 1024, 1)
        total_gb = round(vram["vram_total_mb"] / 1024, 1)
        pct = round(vram["vram_used_mb"] / vram["vram_total_mb"] * 100)
        return f"VRAM: {used_gb}/{total_gb} GB ({pct}%)"
    return "VRAM: indisponível"


def _model_label(item):
    """Dynamic label showing loaded model."""
    if transcriber.is_loaded:
        return f"Modelo: {transcriber.current_model_name}"
    return "Modelo: nenhum"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _handle_download_models():
    """Check sys.argv for --download-models and queue downloads."""
    for i, arg in enumerate(sys.argv):
        if arg == "--download-models" and i + 1 < len(sys.argv):
            models_str = sys.argv[i + 1].strip()
            if not models_str:
                return
            model_names = [m.strip() for m in models_str.split(",") if m.strip()]
            if not model_names:
                return
            logger.info("Instalador solicitou download dos modelos: %s", model_names)

            def _download_queue():
                # Wait for server to be ready
                time.sleep(3)
                for name in model_names:
                    if model_manager.is_downloaded(name):
                        logger.info("Modelo %s já baixado, pulando", name)
                        continue
                    logger.info("Iniciando download: %s", name)
                    try:
                        model_manager.download(name)
                        # Wait for download to finish before starting next
                        while model_manager.is_downloading:
                            time.sleep(1)
                    except Exception as e:
                        logger.error("Erro ao baixar %s: %s", name, e)

            threading.Thread(target=_download_queue, daemon=True).start()
            return


def main():
    global tray_icon

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Start update checker
    update_checker = UpdateChecker(on_update_available=_on_update_available)
    update_checker.start()

    # Check if installer requested model downloads
    _handle_download_models()

    menu = pystray.Menu(
        pystray.MenuItem(f"GPU: {transcriber.gpu_name or 'CPU'}", None, enabled=False),
        pystray.MenuItem(_vram_label, None, enabled=False),
        pystray.MenuItem(_model_label, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Limpar GPU",
            on_unload_model,
            visible=lambda item: transcriber.is_loaded,
        ),
        pystray.MenuItem(
            "Iniciar com Windows",
            on_toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.MenuItem(
            lambda item: f"Atualizar para {_update_info['data']['version']}" if _update_info["available"] else "Sem atualizações",
            on_download_update,
            visible=lambda item: _update_info["available"],
        ),
        pystray.MenuItem(f"Porta: {PORT}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", on_quit),
    )

    tray_icon = pystray.Icon(
        name="WhatsGPU",
        icon=create_icon_image((150, 150, 150)),  # gray = no model loaded
        title="Whats GPU - Sem modelo",
        menu=menu,
    )

    tray_icon.run()


if __name__ == "__main__":
    main()
