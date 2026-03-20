import json
import logging
import os
import subprocess
import tempfile
import threading

logger = logging.getLogger(__name__)


def _find_transcribe_binary():
    """Find the compiled Swift transcribe binary."""
    # Check same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "transcribe"),
        os.path.join(script_dir, "transcribe_mac"),
        # PyInstaller bundle
        os.path.join(getattr(__import__("sys"), "_MEIPASS", script_dir), "transcribe"),
    ]
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class Transcriber:
    """macOS transcriber using SFSpeechRecognizer via Swift helper binary."""

    def __init__(self, status_callback=None):
        self.model = True  # Always "loaded" — SFSpeechRecognizer is built-in
        self._lock = threading.Lock()
        self._status_callback = status_callback
        self._binary = _find_transcribe_binary()

        # macOS info
        self.has_gpu = False
        self.gpu_name = None
        self.gpu_vram_gb = 0
        self.device = "cpu"
        self.compute_type = "default"

        # Detect Apple Silicon chip name
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                self.gpu_name = result.stdout.strip()  # e.g. "Apple M2 Pro"
        except Exception:
            self.gpu_name = "Apple Silicon"

        if self._binary:
            logger.info("Swift transcribe binary: %s", self._binary)
        else:
            logger.warning("Swift transcribe binary não encontrado! Compile com: swiftc transcribe.swift -o transcribe")

    def _emit(self, stage, detail=None):
        logger.info("Stage: %s | %s", stage, detail or "")
        if self._status_callback:
            self._status_callback(stage, detail)

    @property
    def is_loaded(self):
        return True  # SFSpeechRecognizer is always available

    @property
    def current_model_name(self):
        return "SFSpeechRecognizer"

    def ensure_model(self, model_path=None):
        """No-op on macOS — SFSpeechRecognizer is built-in."""
        pass

    def transcribe(self, audio_bytes, filename="audio.ogg"):
        if not self._binary:
            raise RuntimeError(
                "Swift transcribe binary não encontrado. "
                "Compile com: swiftc transcribe.swift -o transcribe"
            )

        tmp_path = None
        try:
            suffix = os.path.splitext(filename)[1] or ".ogg"
            fd, tmp_path = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            self._emit("transcribing", {"status": "Transcrevendo com SFSpeechRecognizer..."})

            with self._lock:
                result = subprocess.run(
                    [self._binary, tmp_path, "pt-BR"],
                    capture_output=True, text=True, timeout=300,
                )

            if result.returncode != 0:
                # Try to parse error from JSON output
                try:
                    data = json.loads(result.stdout)
                    error = data.get("error", "Erro desconhecido")
                except (json.JSONDecodeError, ValueError):
                    error = result.stderr or result.stdout or "Erro desconhecido"
                raise RuntimeError(f"Erro na transcrição: {error}")

            data = json.loads(result.stdout)

            if data.get("error"):
                raise RuntimeError(f"Erro na transcrição: {data['error']}")

            text = data.get("text", "").strip()
            duration = data.get("duration", 0)

            self._emit("done", {
                "progress_pct": 100,
                "total_s": round(duration, 1),
            })
            return text

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def unload(self):
        """No-op on macOS."""
        pass

    def _clear_gpu(self):
        """No-op on macOS."""
        pass
