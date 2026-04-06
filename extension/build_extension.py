"""Build helper for Chrome Web Store packaging.

Usage:
    python build_extension.py

Generates:
    1. Missing icon sizes (16px, 48px) from 128px source
    2. extension.zip ready for Chrome Web Store upload
"""

import os
import shutil
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow necessário: pip install Pillow")
    exit(1)

EXT_DIR = Path(__file__).parent
ICONS_DIR = EXT_DIR / "icons"
OUTPUT_ZIP = EXT_DIR.parent / "companion-app" / "dist" / "whats-gpu-extension.zip"

REQUIRED_SIZES = [16, 38, 48, 64, 128]
SOURCE_ICON = ICONS_DIR / "128.png"

# Files to include in the zip
EXTENSION_FILES = [
    "manifest.json",
    "popup.html",
    "popup.js",
    "content.js",
    "page.js",
    "service_worker.js",
]


def generate_icons():
    """Generate missing icon sizes from 128px source."""
    if not SOURCE_ICON.exists():
        print(f"Ícone fonte não encontrado: {SOURCE_ICON}")
        return

    img = Image.open(SOURCE_ICON)
    for size in REQUIRED_SIZES:
        target = ICONS_DIR / f"{size}.png"
        if not target.exists():
            resized = img.resize((size, size), Image.LANCZOS)
            resized.save(target)
            print(f"Gerado: {target.name}")
        else:
            print(f"Já existe: {target.name}")


def build_zip():
    """Package extension into zip for Chrome Web Store."""
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in EXTENSION_FILES:
            fpath = EXT_DIR / fname
            if fpath.exists():
                zf.write(fpath, fname)
                print(f"Adicionado: {fname}")

        # Add all icons
        for icon in ICONS_DIR.glob("*.png"):
            arcname = f"icons/{icon.name}"
            zf.write(icon, arcname)
            print(f"Adicionado: {arcname}")

    print(f"\nExtensão empacotada: {OUTPUT_ZIP}")
    print(f"Tamanho: {OUTPUT_ZIP.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    print("=== Whats GPU — Build Extension ===\n")
    print("1. Gerando ícones...")
    generate_icons()
    print("\n2. Empacotando extensão...")
    build_zip()
    print("\nPronto! Faça upload do .zip na Chrome Web Store.")
