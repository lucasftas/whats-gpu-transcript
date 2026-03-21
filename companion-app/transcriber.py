import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

logger = logging.getLogger(__name__)


def _load_cuda_libs():
    """Add NVIDIA CUDA DLL directories to search path before importing ctranslate2."""
    try:
        # Find nvidia package DLLs (cublas, cudnn, etc.)
        site_packages_dirs = [p for p in sys.path if "site-packages" in p]
        for sp in site_packages_dirs:
            nvidia_dir = os.path.join(sp, "nvidia")
            if os.path.isdir(nvidia_dir):
                for sub in os.listdir(nvidia_dir):
                    bin_dir = os.path.join(nvidia_dir, sub, "bin")
                    if os.path.isdir(bin_dir):
                        os.add_dll_directory(bin_dir)
                        logger.info("CUDA DLL dir: %s", bin_dir)
        # Also add ctranslate2 dir
        try:
            import ctranslate2
            ct2_dir = os.path.dirname(ctranslate2.__file__)
            os.add_dll_directory(ct2_dir)
        except Exception:
            pass
    except Exception as e:
        logger.warning("Erro ao carregar CUDA libs: %s", e)


_load_cuda_libs()


def _detect_gpu():
    """Detect NVIDIA GPU using ctranslate2 (no torch needed)."""
    try:
        import ctranslate2
        num_gpus = ctranslate2.get_cuda_device_count()
        if num_gpus > 0:
            # Get GPU name and VRAM via subprocess (nvidia-smi)
            gpu_name = "NVIDIA GPU"
            vram_gb = 0
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    parts = result.stdout.strip().split(",")
                    if len(parts) >= 2:
                        gpu_name = parts[0].strip()
                        vram_gb = round(int(parts[1].strip()) / 1024, 1)
            except Exception:
                pass
            logger.info("GPU detectada: %s (%.1f GB VRAM)", gpu_name, vram_gb)
            return True, gpu_name, vram_gb
    except Exception as e:
        logger.warning("Erro ao detectar GPU: %s", e)
    logger.warning("GPU nao detectada - usando CPU")
    return False, None, 0


# VRAM usage cache (avoid spawning nvidia-smi too frequently)
_vram_cache = {"data": None, "ts": 0}
_VRAM_CACHE_TTL = 2  # seconds


def get_vram_usage():
    """Query real-time VRAM usage via nvidia-smi. Returns dict or None."""
    now = time.time()
    if _vram_cache["data"] is not None and (now - _vram_cache["ts"]) < _VRAM_CACHE_TTL:
        return _vram_cache["data"]
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 3:
                data = {
                    "vram_total_mb": int(parts[0].strip()),
                    "vram_used_mb": int(parts[1].strip()),
                    "vram_free_mb": int(parts[2].strip()),
                }
                _vram_cache["data"] = data
                _vram_cache["ts"] = now
                return data
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Audio pre-processing (normalize volume for WhatsApp compressed audio)
# ---------------------------------------------------------------------------
def _normalize_audio(audio_path):
    """Normalize audio volume using peak normalization. Returns path to normalized file."""
    try:
        import av
        import numpy as np

        container = av.open(audio_path)
        stream = container.streams.audio[0]

        # Decode all audio frames
        frames = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray().flatten().astype(np.float32)
            frames.append(arr)
        container.close()

        if not frames:
            return audio_path

        audio_data = np.concatenate(frames)
        peak = np.max(np.abs(audio_data))

        if peak < 1e-6:
            logger.info("Audio silencioso, pulando normalizacao")
            return audio_path

        # Normalize to 95% of max to avoid clipping
        if peak < 0.5:
            scale = 0.95 / peak
            audio_data = audio_data * scale
            audio_data = np.clip(audio_data, -1.0, 1.0)
            logger.info("Audio normalizado: peak %.4f -> %.4f (scale %.2fx)", peak, 0.95, scale)

            # Write normalized audio to WAV (faster_whisper accepts WAV)
            norm_path = audio_path + ".norm.wav"
            out = av.open(norm_path, "w")
            out_stream = out.add_stream("pcm_s16le", rate=stream.rate or 16000)
            out_stream.layout = "mono"

            # Convert float32 [-1,1] to int16
            int_data = (audio_data * 32767).astype(np.int16)
            frame = av.AudioFrame.from_ndarray(
                int_data.reshape(1, -1), format="s16", layout="mono"
            )
            frame.rate = stream.rate or 16000
            for packet in out_stream.encode(frame):
                out.mux(packet)
            for packet in out_stream.encode():
                out.mux(packet)
            out.close()
            return norm_path
        else:
            logger.info("Audio ja com volume adequado (peak %.4f)", peak)
            return audio_path
    except Exception as e:
        logger.warning("Falha na normalizacao, usando audio original: %s", e)
        return audio_path


# ---------------------------------------------------------------------------
# Post-processing (clean transcription artifacts)
# ---------------------------------------------------------------------------
_HALLUCINATION_PATTERNS = re.compile(
    r"\[BLANK_AUDIO\]|"
    r"\(sil[eê]ncio\)|"
    r"Legendas (?:pela|por) comunidade|"
    r"Obrigad[oa] por assistir|"
    r"Thanks for watching|"
    r"Inscreva-se no canal|"
    r"♪",
    re.IGNORECASE,
)


def _clean_transcription(text):
    """Remove common Whisper artifacts from transcription."""
    text = _HALLUCINATION_PATTERNS.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)  # collapse multiple spaces
    return text.strip()


class Transcriber:
    def __init__(self, model_size="large-v3", status_callback=None):
        self.model = None
        self.model_size = model_size
        self._model_path = None  # path or HF model name
        self._lock = threading.Lock()
        self._status_callback = status_callback

        # GPU detection
        self.has_gpu, self.gpu_name, self.gpu_vram_gb = _detect_gpu()
        self.device = "cuda" if self.has_gpu else "cpu"
        self.compute_type = "float16" if self.has_gpu else "int8"

    def _emit(self, stage, detail=None):
        logger.info("Stage: %s | %s", stage, detail or "")
        if self._status_callback:
            self._status_callback(stage, detail)

    def ensure_model(self, model_path=None):
        """Load model from local path or HF name. If model_path changes, reload."""
        target = model_path or self._model_path or self.model_size
        if self.model is not None and self._model_path == target:
            return  # already loaded with same path
        # Unload previous if switching models
        if self.model is not None:
            logger.info("Trocando modelo: %s -> %s", self._model_path, target)
            self.model = None
            self._clear_gpu()

        self._emit("loading_model", f"Carregando {os.path.basename(str(target))} na {self.device.upper()}...")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            target,
            device=self.device,
            compute_type=self.compute_type,
        )
        self._model_path = target
        self._emit("model_ready")

    def transcribe(self, audio_bytes, filename="audio.ogg", precision=None):
        """Transcribe audio bytes. precision dict can override beam_size, best_of, temperature, patience."""
        tmp_path = None
        norm_path = None
        try:
            suffix = os.path.splitext(filename)[1] or ".ogg"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            # Pre-process: normalize audio volume (WhatsApp compression = low volume)
            norm_path = _normalize_audio(tmp_path)
            transcribe_path = norm_path if norm_path != tmp_path else tmp_path

            # Apply precision overrides
            p = precision or {}
            beam_size = p.get("beam_size", 5)
            best_of = p.get("best_of", 5)
            patience = p.get("patience", 1.0)

            # Temperature can be a single float or a list for fallback
            temperature = p.get("temperature", [0.0])
            if isinstance(temperature, list) and len(temperature) == 1:
                temperature = temperature[0]

            logger.info(
                "Transcribindo com beam=%d best_of=%d patience=%.1f temp=%s",
                beam_size, best_of, patience, temperature,
            )

            # Lock only for model access and transcribe call
            with self._lock:
                self.ensure_model()
                segments, info = self.model.transcribe(
                    transcribe_path,
                    language="pt",
                    beam_size=beam_size,
                    best_of=best_of,
                    temperature=temperature,
                    patience=patience,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=300,
                        speech_pad_ms=200,
                    ),
                    no_speech_threshold=0.5,
                    log_prob_threshold=-0.8,
                    compression_ratio_threshold=2.4,
                    condition_on_previous_text=True,
                    initial_prompt=(
                        "Transcrição de mensagem de voz do WhatsApp em português brasileiro. "
                        "Linguagem informal e coloquial."
                    ),
                )
                duration_s = getattr(info, "duration", 0) or 0

            # Iterate segments OUTSIDE lock — allows /status to respond
            collected = []
            for segment in segments:
                # Filter low-confidence segments (likely noise/breathing)
                if getattr(segment, "no_speech_prob", 0) > 0.7:
                    logger.info(
                        "Segmento descartado (no_speech=%.2f): '%s'",
                        segment.no_speech_prob, segment.text.strip()[:50],
                    )
                    continue

                text = segment.text.strip()
                if text:
                    collected.append(text)

                if duration_s > 0:
                    pct = min(round(segment.end / duration_s * 100), 99)
                    self._emit("transcribing", {
                        "progress_pct": pct,
                        "processed_s": round(segment.end, 1),
                        "total_s": round(duration_s, 1),
                    })

            self._emit("done", {"progress_pct": 100})

            # Post-process: clean artifacts
            result = " ".join(collected)
            return _clean_transcription(result)
        except RuntimeError as e:
            if "CUDA out of memory" in str(e) or "OutOfMemoryError" in type(e).__name__:
                logger.error("GPU OOM - descarregando modelo")
                self._emit("oom_error", "GPU sem memoria")
                self.model = None
                self._clear_gpu()
                raise RuntimeError("GPU sem memoria. Modelo descarregado. Tente novamente.") from e
            raise
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if norm_path and norm_path != tmp_path and os.path.exists(norm_path):
                os.unlink(norm_path)

    def unload(self):
        with self._lock:
            self._emit("unloading")
            self.model = None
            self._model_path = None
            self._clear_gpu()
            self._emit("unloaded")

    def _clear_gpu(self):
        try:
            import torch
            torch.cuda.empty_cache()
        except ImportError:
            pass  # torch not installed, ctranslate2 manages its own memory
        except Exception:
            pass

    @property
    def is_loaded(self):
        return self.model is not None

    @property
    def current_model_name(self):
        if self._model_path:
            return os.path.basename(self._model_path)
        return self.model_size
