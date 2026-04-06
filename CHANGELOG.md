# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

## [1.1.4] - 2026-04-06

### Added
- Filtro de redução de ruído (noisereduce) no pipeline de áudio
- Confiança por palavra (word_timestamps) com display visual colorido na extensão
- Prompt dinâmico baseado no contexto das mensagens da conversa
- Modelo fine-tuned PT-BR (large-v3-pt-br) no catálogo de modelos
- Seletor de idioma com 12 idiomas + auto-detect no popup
- Fila de transcrições com modo async e job tracking
- Suporte a múltiplas GPUs com seletor no popup
- Auto-update via GitHub Releases (verificação a cada 6h)
- Script de empacotamento para Chrome Web Store (build_extension.py)
- Ícones 16px e 48px para compatibilidade com Chrome Web Store
- Transcrição ensemble (2 modelos + merge por confiança)
- Endpoint `/gpus` e `/gpu/select` para seleção de GPU
- Endpoint `/queue` para status da fila de transcrições
- Endpoint `/transcribe/ensemble` para transcrição com múltiplos modelos
- Endpoint `/update/check` para verificação de atualizações
- Módulo `updater.py` para auto-update

### Fixed
- Janela do terminal piscando em loop (adicionado `CREATE_NO_WINDOW` no subprocess do nvidia-smi)

## [1.1.3] - 2026-03-22

### Added
- CLAUDE.md com instruções de build
- Versão incluída no nome do instalador

## [1.1.2] - 2026-03-21

### Added
- Otimização de precisão para PT-BR
- Monitor VRAM no tray
- Detecção de modelos no instalador
- Funcionalidade de re-transcrição

## [1.1.0] - 2026-03-20

### Added
- Slider de precisão (Rápido/Balanceado/Máxima)
- Desinstalador completo

## [1.0.1] - 2026-03-20

### Fixed
- Correções iniciais pós-lançamento

## [1.0.0] - 2026-03-20

### Added
- Lançamento inicial
- Transcrição local de áudios do WhatsApp Web via GPU NVIDIA
- Extensão Chrome + companion app
- Gerenciamento de modelos Whisper
- System tray com status
- Instalador Inno Setup
