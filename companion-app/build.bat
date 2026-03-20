@echo off
echo Building Whats GPU (--onedir)...
"C:\Program Files\Python312\python.exe" -m PyInstaller --onedir --windowed --icon=icon.ico --name="Whats GPU" ^
    --hidden-import=ctranslate2 ^
    --hidden-import=faster_whisper ^
    --hidden-import=huggingface_hub ^
    --hidden-import=nvidia.cublas ^
    --add-data "C:/Users/Lucas/AppData/Roaming/Python/Python312/site-packages/nvidia/cublas/bin/cublas64_12.dll;." ^
    --add-data "C:/Users/Lucas/AppData/Roaming/Python/Python312/site-packages/nvidia/cublas/bin/cublasLt64_12.dll;." ^
    --add-data "C:/Users/Lucas/AppData/Roaming/Python/Python312/site-packages/faster_whisper/assets;faster_whisper/assets" ^
    app.py
echo.
echo Build complete! Check dist\Whats GPU\
pause
