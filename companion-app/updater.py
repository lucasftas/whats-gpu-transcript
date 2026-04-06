"""Auto-update checker for WhatsGPU via GitHub Releases."""

import logging
import threading
import time
import webbrowser

import requests

logger = logging.getLogger(__name__)

GITHUB_REPO = "lucasftas/whats-GPU"
CHECK_INTERVAL = 3600 * 6  # check every 6 hours
CURRENT_VERSION = "1.1.4"


def _parse_version(tag):
    """Parse 'v1.2.3' or '1.2.3' into tuple (1, 2, 3)."""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except (ValueError, AttributeError):
        return (0, 0, 0)


def check_for_update():
    """Check GitHub Releases for a newer version. Returns dict or None."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        resp = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code != 200:
            return None
        release = resp.json()
        tag = release.get("tag_name", "")
        remote_ver = _parse_version(tag)
        local_ver = _parse_version(CURRENT_VERSION)
        if remote_ver > local_ver:
            # Find installer asset
            download_url = release.get("html_url", "")
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".exe") and "Setup" in name:
                    download_url = asset.get("browser_download_url", download_url)
                    break
            return {
                "version": tag,
                "current": CURRENT_VERSION,
                "download_url": download_url,
                "release_url": release.get("html_url", ""),
                "body": release.get("body", "")[:500],
            }
    except Exception as e:
        logger.debug("Erro ao verificar atualização: %s", e)
    return None


class UpdateChecker:
    """Background thread that periodically checks for updates."""

    def __init__(self, on_update_available=None):
        self._callback = on_update_available
        self._thread = None
        self._stop = False
        self.latest_update = None

    def start(self):
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop = True

    def _run(self):
        # Initial delay to not slow down startup
        time.sleep(30)
        while not self._stop:
            update = check_for_update()
            if update:
                self.latest_update = update
                logger.info("Nova versão disponível: %s (atual: %s)", update["version"], update["current"])
                if self._callback:
                    self._callback(update)
            time.sleep(CHECK_INTERVAL)

    @staticmethod
    def open_download(update_info):
        """Open the download URL in the default browser."""
        url = update_info.get("download_url") or update_info.get("release_url")
        if url:
            webbrowser.open(url)
