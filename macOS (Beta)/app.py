import logging
import os
import subprocess
import threading
import time

from flask import Flask, request, jsonify
from PIL import Image, ImageDraw
from waitress import serve

from transcriber import Transcriber

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

# ---------------------------------------------------------------------------
# Global status
# ---------------------------------------------------------------------------
current_status = {"stage": "idle", "detail": None, "timestamp": time.time()}

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)


def on_status_change(stage, detail=None):
    global current_status
    current_status = {"stage": stage, "detail": detail, "timestamp": time.time()}


transcriber = Transcriber(status_callback=on_status_change)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "platform": "macos",
        "engine": "SFSpeechRecognizer",
        "chip": transcriber.gpu_name,
        "model_loaded": True,
        "current_stage": current_status["stage"],
    })


@flask_app.route("/status", methods=["GET"])
def status():
    return jsonify(current_status)


@flask_app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    audio_bytes = file.read()
    if not audio_bytes:
        return jsonify({"error": "Empty file"}), 400

    try:
        text = transcriber.transcribe(audio_bytes, filename=file.filename or "audio.ogg")
        on_status_change("idle")
        return jsonify({"text": text})
    except Exception as e:
        on_status_change("idle")
        logger.error("Erro na transcrição: %s", e)
        return jsonify({"error": str(e)}), 500


@flask_app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# ---------------------------------------------------------------------------
# LaunchAgent auto-start
# ---------------------------------------------------------------------------
_PLIST_PATH = os.path.expanduser("~/Library/LaunchAgents/com.whatsgpu.app.plist")
_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whatsgpu.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""


def is_autostart_enabled():
    return os.path.exists(_PLIST_PATH)


def set_autostart(enabled):
    try:
        if enabled:
            import sys
            exe_path = sys.executable if not getattr(sys, "frozen", False) else sys.executable
            os.makedirs(os.path.dirname(_PLIST_PATH), exist_ok=True)
            with open(_PLIST_PATH, "w") as f:
                f.write(_PLIST_TEMPLATE.format(exe_path=exe_path))
            subprocess.run(["launchctl", "load", _PLIST_PATH], capture_output=True)
            logger.info("Auto-start ativado")
        else:
            if os.path.exists(_PLIST_PATH):
                subprocess.run(["launchctl", "unload", _PLIST_PATH], capture_output=True)
                os.remove(_PLIST_PATH)
            logger.info("Auto-start desativado")
        return True
    except Exception as e:
        logger.error("Erro ao configurar auto-start: %s", e)
        return False


# ---------------------------------------------------------------------------
# Server thread
# ---------------------------------------------------------------------------
def run_server():
    logger.info("Servidor iniciando em 127.0.0.1:%d", PORT)
    logger.info("Chip: %s | Engine: SFSpeechRecognizer", transcriber.gpu_name)
    serve(flask_app, host="127.0.0.1", port=PORT, threads=4, channel_timeout=300)


# ---------------------------------------------------------------------------
# Main — rumps menu bar app
# ---------------------------------------------------------------------------
def main():
    try:
        import rumps
    except ImportError:
        logger.warning("rumps não instalado. Rodando sem menu bar.")
        logger.info("Instale com: pip install rumps")
        run_server()
        return

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    class WhatsGPUApp(rumps.App):
        def __init__(self):
            super().__init__(
                "WhatsGPU",
                title="W",
                quit_button=None,
            )
            self.menu = [
                rumps.MenuItem(f"Porta: {PORT}", callback=None),
                rumps.MenuItem(f"Chip: {transcriber.gpu_name or 'Desconhecido'}", callback=None),
                rumps.MenuItem("Engine: SFSpeechRecognizer", callback=None),
                None,  # separator
                rumps.MenuItem(
                    "Iniciar com macOS",
                    callback=self.toggle_autostart,
                ),
                None,  # separator
                rumps.MenuItem("Sair", callback=self.quit_app),
            ]
            # Update autostart checkbox
            self.menu["Iniciar com macOS"].state = is_autostart_enabled()

        def toggle_autostart(self, sender):
            new_state = not is_autostart_enabled()
            set_autostart(new_state)
            sender.state = new_state

        def quit_app(self, _):
            rumps.quit_application()

    app = WhatsGPUApp()
    app.run()


if __name__ == "__main__":
    main()
