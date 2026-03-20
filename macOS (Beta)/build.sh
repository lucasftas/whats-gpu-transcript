#!/bin/bash
set -e

echo "=== WhatsGPU macOS Build ==="
echo ""

# 1. Compile Swift transcription helper
echo "[1/3] Compilando transcribe.swift..."
swiftc transcribe.swift -o transcribe -framework Speech -framework AVFoundation
echo "  ✓ Binário 'transcribe' criado"

# 2. Install Python dependencies
echo ""
echo "[2/3] Instalando dependências Python..."
pip3 install -r requirements.txt pyinstaller
echo "  ✓ Dependências instaladas"

# 3. Build with PyInstaller
echo ""
echo "[3/3] Criando app bundle com PyInstaller..."
pyinstaller --onedir --windowed --name "WhatsGPU" \
    --add-binary "transcribe:." \
    app.py

echo ""
echo "=== Build concluído! ==="
echo "App bundle: dist/WhatsGPU/"
echo ""
echo "Para testar: python3 app.py"
echo "Para instalar a extensão: abra chrome://extensions e carregue a pasta extension/"
