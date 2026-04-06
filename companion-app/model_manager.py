import logging
import os
import shutil
import threading
import json
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# faster-whisper CTranslate2 model files needed
MODEL_FILES = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt", "preprocessor_config.json"]

# Model catalog
MODELS = {
    "large-v3": {
        "repo": "Systran/faster-whisper-large-v3",
        "size_mb": 3100,
        "min_vram_gb": 10,
        "precision": "Excelente",
        "description": "Melhor precisão geral - ideal para RTX 4070+",
        "url": "https://huggingface.co/Systran/faster-whisper-large-v3",
        "category": "general",
    },
    "large-v3-pt-br": {
        "repo": "jlondonobo/whisper-large-v3-pt-cv17-ct2",
        "size_mb": 3100,
        "min_vram_gb": 10,
        "precision": "Excelente PT-BR",
        "description": "Fine-tuned para PT-BR - superior em sotaques e gírias",
        "url": "https://huggingface.co/jlondonobo/whisper-large-v3-pt-cv17-ct2",
        "category": "pt-br",
    },
    "medium": {
        "repo": "Systran/faster-whisper-medium",
        "size_mb": 1500,
        "min_vram_gb": 5,
        "precision": "Muito boa",
        "description": "Bom equilíbrio entre velocidade e precisão - RTX 3060/4060",
        "url": "https://huggingface.co/Systran/faster-whisper-medium",
        "category": "general",
    },
    "small": {
        "repo": "Systran/faster-whisper-small",
        "size_mb": 466,
        "min_vram_gb": 2,
        "precision": "Boa",
        "description": "Rápido e leve - GTX 1060/1070",
        "url": "https://huggingface.co/Systran/faster-whisper-small",
        "category": "general",
    },
    "base": {
        "repo": "Systran/faster-whisper-base",
        "size_mb": 142,
        "min_vram_gb": 1,
        "precision": "Razoável",
        "description": "Muito rápido, precisão básica",
        "url": "https://huggingface.co/Systran/faster-whisper-base",
        "category": "general",
    },
    "tiny": {
        "repo": "Systran/faster-whisper-tiny",
        "size_mb": 75,
        "min_vram_gb": 1,
        "precision": "Baixa",
        "description": "Ultra rápido - apenas para testes",
        "url": "https://huggingface.co/Systran/faster-whisper-tiny",
        "category": "general",
    },
}


def _get_models_dir():
    """Return ~/Documents/WhatsGPU/Modelos/, creating if needed."""
    docs = Path.home() / "Documents" / "WhatsGPU" / "Modelos"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def _download_file(url, dest_path, progress_callback=None, cancel_check=None):
    """Download a single file with streaming progress, like Vibe does."""
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    dest_path_tmp = dest_path + ".tmp"
    with open(dest_path_tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if cancel_check and cancel_check():
                f.close()
                os.remove(dest_path_tmp)
                return False
            f.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total_size > 0:
                progress_callback(downloaded, total_size)

    os.rename(dest_path_tmp, dest_path)
    return True


class ModelManager:
    def __init__(self, status_callback=None):
        self.models_dir = _get_models_dir()
        self._status_callback = status_callback
        self._download_thread = None
        self._downloading = False
        self._cancel_requested = False
        self._downloading_model = None
        logger.info("Pasta de modelos: %s", self.models_dir)

    def _emit(self, stage, detail=None):
        logger.info("ModelManager: %s | %s", stage, detail or "")
        if self._status_callback:
            self._status_callback(stage, detail)

    def list_available(self, vram_gb=0):
        """Return list of models with download status and recommendation."""
        recommended = self.recommend(vram_gb)
        result = []
        for name, info in MODELS.items():
            result.append({
                "name": name,
                "size_mb": info["size_mb"],
                "precision": info["precision"],
                "description": info["description"],
                "min_vram_gb": info["min_vram_gb"],
                "downloaded": self.is_downloaded(name),
                "recommended": name == recommended,
                "url": info["url"],
                "category": info.get("category", "general"),
            })
        return result

    def is_downloaded(self, model_name):
        """Check if model exists locally with model.bin."""
        model_dir = self.models_dir / model_name
        if not model_dir.exists():
            return False
        return (model_dir / "model.bin").exists()

    def get_path(self, model_name):
        """Return local path if downloaded, else None."""
        if self.is_downloaded(model_name):
            return str(self.models_dir / model_name)
        return None

    def recommend(self, vram_gb):
        """Recommend best model for given VRAM."""
        if vram_gb <= 0:
            return "small"
        for name in ["large-v3", "medium", "small", "base", "tiny"]:
            if MODELS[name]["min_vram_gb"] <= vram_gb:
                return name
        return "tiny"

    def delete(self, model_name):
        """Delete a downloaded model."""
        model_dir = self.models_dir / model_name
        if model_dir.exists():
            shutil.rmtree(model_dir, ignore_errors=True)
            logger.info("Modelo removido: %s", model_name)
            return True
        return False

    @property
    def is_downloading(self):
        return self._downloading

    @property
    def downloading_model(self):
        return self._downloading_model

    def cancel_download(self):
        """Request cancellation of current download."""
        if self._downloading:
            self._cancel_requested = True
            logger.info("Cancelamento solicitado")
            return True
        return False

    def download(self, model_name):
        """Download model files via HTTP streaming with real progress."""
        if model_name not in MODELS:
            raise ValueError(f"Modelo desconhecido: {model_name}")
        if self.is_downloaded(model_name):
            return
        if self._downloading:
            raise RuntimeError("Já existe um download em andamento")

        self._downloading = True
        self._cancel_requested = False
        self._downloading_model = model_name

        def _do_download():
            repo = MODELS[model_name]["repo"]
            dest_dir = self.models_dir / model_name
            dest_dir.mkdir(parents=True, exist_ok=True)

            try:
                # First, get the list of files from the HF API
                api_url = f"https://huggingface.co/api/models/{repo}"
                logger.info("Consultando arquivos do modelo: %s", api_url)
                self._emit("downloading_model", {
                    "model": model_name,
                    "progress_pct": 0,
                    "downloaded_mb": 0,
                    "total_mb": MODELS[model_name]["size_mb"],
                    "status": "Consultando arquivos...",
                })

                resp = requests.get(api_url, timeout=15)
                resp.raise_for_status()
                repo_info = resp.json()

                # Get files to download (filter to known model files)
                siblings = repo_info.get("siblings", [])
                files_to_download = []
                for s in siblings:
                    fname = s.get("rfilename", "")
                    # Download model.bin and config files
                    if fname in MODEL_FILES or fname.endswith(".json") or fname.endswith(".txt"):
                        files_to_download.append(fname)

                if not files_to_download:
                    raise RuntimeError(f"Nenhum arquivo encontrado no repositório {repo}")

                # Calculate total size by doing HEAD requests for main files
                total_bytes = 0
                file_sizes = {}
                for fname in files_to_download:
                    url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
                    try:
                        head = requests.head(url, allow_redirects=True, timeout=10)
                        size = int(head.headers.get("content-length", 0))
                        file_sizes[fname] = size
                        total_bytes += size
                    except Exception:
                        file_sizes[fname] = 0

                if total_bytes == 0:
                    total_bytes = MODELS[model_name]["size_mb"] * 1024 * 1024

                # Download each file with cumulative progress
                cumulative_downloaded = 0
                total_mb = round(total_bytes / (1024 * 1024))

                for i, fname in enumerate(files_to_download):
                    if self._cancel_requested:
                        break

                    url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
                    dest_path = str(dest_dir / fname)

                    # Create subdirectories if needed
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    logger.info("Baixando [%d/%d]: %s", i + 1, len(files_to_download), fname)

                    def on_file_progress(file_downloaded, file_total, _cum=cumulative_downloaded):
                        current = _cum + file_downloaded
                        pct = min(round(current / total_bytes * 100), 99) if total_bytes > 0 else 0
                        self._emit("downloading_model", {
                            "model": model_name,
                            "progress_pct": pct,
                            "downloaded_mb": round(current / (1024 * 1024)),
                            "total_mb": total_mb,
                            "status": f"Baixando {fname}... ({i+1}/{len(files_to_download)})",
                        })

                    success = _download_file(
                        url, dest_path,
                        progress_callback=on_file_progress,
                        cancel_check=lambda: self._cancel_requested,
                    )

                    if not success:
                        break

                    cumulative_downloaded += file_sizes.get(fname, 0)

                # Check result
                if self._cancel_requested:
                    logger.info("Download cancelado, limpando: %s", dest_dir)
                    shutil.rmtree(dest_dir, ignore_errors=True)
                    self._emit("idle", {"message": f"Download de {model_name} cancelado"})
                elif self.is_downloaded(model_name):
                    self._emit("download_complete", {
                        "model": model_name,
                        "progress_pct": 100,
                    })
                    logger.info("Download concluído: %s", model_name)
                else:
                    raise RuntimeError("model.bin não encontrado após download")

            except Exception as e:
                error_msg = str(e)
                logger.error("Erro no download de %s: %s", model_name, error_msg)
                if self._cancel_requested:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                    self._emit("idle", {"message": f"Download de {model_name} cancelado"})
                else:
                    # Clean partial download on error
                    shutil.rmtree(dest_dir, ignore_errors=True)
                    self._emit("download_error", {
                        "model": model_name,
                        "error": error_msg,
                    })
            finally:
                self._downloading = False
                self._downloading_model = None
                self._cancel_requested = False

        self._download_thread = threading.Thread(target=_do_download, daemon=True)
        self._download_thread.start()
