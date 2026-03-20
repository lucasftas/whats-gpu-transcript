import logging
import os
import sys
import tempfile
import threading

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
                import subprocess
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

    def transcribe(self, audio_bytes, filename="audio.ogg"):
        tmp_path = None
        try:
            suffix = os.path.splitext(filename)[1] or ".ogg"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            # Lock only for model access and transcribe call
            with self._lock:
                self.ensure_model()
                segments, info = self.model.transcribe(
                    tmp_path,
                    language="pt",
                    beam_size=5,
                    best_of=5,
                    temperature=0.0,
                    vad_filter=True,
                    vad_parameters=dict(
                        min_silence_duration_ms=300,
                        speech_pad_ms=200,
                    ),
                    no_speech_threshold=0.5,
                    log_prob_threshold=-1.0,
                    compression_ratio_threshold=2.4,
                    condition_on_previous_text=True,
                    initial_prompt="Transcrição de mensagem de voz do WhatsApp em português brasileiro.",
                )
                duration_s = getattr(info, "duration", 0) or 0

            # Iterate segments OUTSIDE lock — allows /status to respond
            collected = []
            for segment in segments:
                collected.append(segment.text.strip())
                if duration_s > 0:
                    pct = min(round(segment.end / duration_s * 100), 99)
                    self._emit("transcribing", {
                        "progress_pct": pct,
                        "processed_s": round(segment.end, 1),
                        "total_s": round(duration_s, 1),
                    })

            self._emit("done", {"progress_pct": 100})
            return " ".join(collected)
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
