# WhatsGPU - Instruções do Projeto

## Build

1. **PyInstaller** (gera `companion-app/dist/Whats GPU/`):
   ```
   cd companion-app
   build.bat
   ```

2. **Inno Setup** (gera o instalador final em `companion-app/dist/`):
   ```
   "C:\Users\Lucas\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
   ```

3. **Limpeza pós-build**: após compilar o instalador, remover apenas a pasta de distribuição intermediária:
   ```
   rm -rf "companion-app/dist/Whats GPU/"
   ```
   Manter `companion-app/build/` — contém cache do PyInstaller que acelera rebuilds.
   Manter apenas o instalador final (`WhatsGPU-Setup-v*.exe`) em `companion-app/dist/`.

## Versão

Ao bumpar versão, atualizar nos dois arquivos:
- `companion-app/installer.iss` (`#define MyAppVersion`)
- `extension/manifest.json` (`"version"`)

O nome do instalador inclui a versão automaticamente via `OutputBaseFilename=WhatsGPU-Setup-v{#MyAppVersion}`.
