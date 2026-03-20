import logging
import sys
import threading
import time
import os
import winreg

from flask import Flask, request, jsonify
from PIL import Image, ImageDraw
from waitress import serve
import pystray

from transcriber import Transcriber
from model_manager import ModelManager

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
    return jsonify({
        "status": "ok",
        "model": transcriber.current_model_name,
        "gpu": transcriber.has_gpu,
        "gpu_name": transcriber.gpu_name,
        "vram_gb": transcriber.gpu_vram_gb,
        "model_loaded": transcriber.is_loaded,
        "current_stage": current_status["stage"],
    })


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
@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    audio_bytes = file.read()
    if not audio_bytes:
        return jsonify({"error": "Empty file"}), 400

    # Parse precision parameters from form data
    precision = None
    precision_json = request.form.get("precision")
    if precision_json:
        try:
            import json
            precision = json.loads(precision_json)
        except Exception:
            pass

    try:
        text = transcriber.transcribe(audio_bytes, filename=file.filename or "audio.ogg", precision=precision)
        on_status_change("idle")
        return jsonify({"text": text})
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


def on_toggle_autostart(icon, item):
    new_state = not is_autostart_enabled()
    set_autostart(new_state)
    logger.info("Auto-start %s", "ativado" if new_state else "desativado")


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

    # Check if installer requested model downloads
    _handle_download_models()

    menu = pystray.Menu(
        pystray.MenuItem(f"Porta: {PORT}", None, enabled=False),
        pystray.MenuItem(
            f"GPU: {transcriber.gpu_name or 'CPU'}", None, enabled=False
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Iniciar com Windows",
            on_toggle_autostart,
            checked=lambda item: is_autostart_enabled(),
        ),
        pystray.MenuItem("Sair (limpar GPU)", on_quit),
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
