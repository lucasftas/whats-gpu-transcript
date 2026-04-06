# Implementations

## v1.1.4 (2026-04-06)

### Fase 1 — Qualidade de Transcrição
- **Noise reduction**: pipeline `denoise -> normalize` usando `noisereduce` com spectral gating antes da transcrição
- **Word-level confidence**: `word_timestamps=True` no Whisper, palavras com baixa confiança exibidas em amarelo/vermelho com tooltip de %
- **Prompt dinâmico**: extensão captura texto das últimas 5 mensagens da conversa e envia como contexto para o `initial_prompt` do Whisper

### Fase 2 — Modelos e Idiomas
- **Modelo PT-BR fine-tuned**: `large-v3-pt-br` (jlondonobo/whisper-large-v3-pt-cv17-ct2) adicionado ao catálogo com badge "PT-BR"
- **Multi-idioma**: seletor com 12 idiomas + auto-detect no popup, prompts nativos por idioma

### Fase 3 — Performance
- **Fila de transcrições**: modo `async` no `/transcribe` com job tracking, endpoint `/queue`
- **Multi-GPU**: detecção de todas as GPUs, seletor no popup, endpoints `/gpus` e `/gpu/select`

### Fase 4 — Distribuição
- **Auto-update**: `updater.py` verifica GitHub Releases a cada 6h, notifica via tray icon + banner no popup
- **Chrome Web Store**: manifest atualizado, ícones 16/48px, `build_extension.py` para empacotamento

### Fase 5 — Precisão Avançada
- **Transcrição ensemble**: endpoint `/transcribe/ensemble` transcreve com 2 modelos e mescla por confiança por palavra

### Correções
- Fix: `CREATE_NO_WINDOW` no subprocess do nvidia-smi (eliminava janela do terminal piscando em loop)

## v1.1.3 (2026-03-22)
- Build instructions e CLAUDE.md
- Bump de versão + nome do instalador com versão

## v1.1.2 (2026-03-21)
- Otimização de precisão para PT-BR
- Documentação de análise de precisão
- Monitor VRAM no tray, detecção no instalador, re-transcrição
