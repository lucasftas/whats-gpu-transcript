# Otimização de Precisão — WhatsGPU

## Contexto do problema

Áudios do WhatsApp têm características específicas que impactam a transcrição:

- **Microfones de celular**: qualidade variável, ruído ambiente, distância do mic
- **Compressão OGG/Opus**: bitrate baixo (~32kbps), perda de frequências altas
- **Fala informal**: gírias, abreviações, palavras cortadas, sotaques regionais
- **Idioma PT-BR**: Whisper foi treinado majoritariamente em inglês

---

## Análise: Persua vs WhatsGPU

Técnicas do app Persua e sua aplicabilidade ao contexto de áudios do WhatsApp:

| Técnica Persua | Aplicável? | Motivo |
|---|---|---|
| Filtro RMS no silêncio | Baixo impacto | WhatsApp = fala direta, silêncio é raro |
| Regex anti-repetição | Baixo impacto | Pessoas não repetem frases em loops |
| Committed Prefix (dedup streaming) | Não se aplica | WhatsGPU não faz streaming, processa áudio completo |
| Seleção de modelo por idioma | Alto impacto | PT-BR precisa de modelo não-quantizado |
| Módulo nativo por SO | Médio impacto | Futuro para macOS (Apple Speech) |

### O que realmente importa para WhatsApp + PT-BR:
1. **Pré-processamento de áudio** (normalização, denoise)
2. **Parâmetros otimizados para PT-BR**
3. **Filtragem por confiança de segmento**
4. **Modelo adequado** (large-v3 float16, sem quantização)

---

## Por que large-v3 float16 é a melhor escolha para PT-BR

### Modelos Whisper disponíveis

| Modelo | Tamanho | Velocidade | Precisão PT-BR |
|---|---|---|---|
| large-v3 float16 | 3.1 GB | Base | Máxima |
| large-v3-turbo | ~800 MB | ~4x mais rápido | Perda em não-inglês |
| large-v3-turbo Q5 | ~500 MB | ~6x mais rápido | Dupla perda (destilação + quantização) |
| medium | 1.5 GB | ~2x mais rápido | Boa, mas inferior |
| small | 466 MB | ~4x mais rápido | Aceitável |

### Por que evitar turbo/quantizado para PT-BR

- **Destilação** (turbo): comprime camadas do modelo, priorizando inglês no processo
- **Quantização** (Q5/Q8): reduz precisão numérica dos pesos, afetando mais idiomas com menos dados de treino
- **PT-BR já tem menos dados** no treino original do Whisper — cada compressão amplifica a perda

**Recomendação**: manter `large-v3 float16` como modelo principal. Velocidade não é prioridade — o usuário já esperou gravar e enviar o áudio.

---

## Melhorias implementadas (v1.1.2+)

### 1. Normalização de áudio

O áudio do WhatsApp chega com volume variável. Normalizar o volume antes de transcrever ajuda o modelo a "ouvir" melhor.

**Implementação**: Peak normalization do waveform antes de salvar o arquivo temporário.

### 2. Parâmetros otimizados para PT-BR

Ajustes nos parâmetros do `faster_whisper`:

| Parâmetro | Antes | Depois | Motivo |
|---|---|---|---|
| `log_prob_threshold` | -1.0 | -0.8 | Menos permissivo, filtra segmentos de baixa confiança |
| `initial_prompt` | Genérico | Contextualizado | Vocabulário informal PT-BR ajuda o decoder |
| `no_speech_threshold` | 0.5 | 0.5 | Já adequado para fala direta |
| `compression_ratio_threshold` | 2.4 | 2.4 | Mantido — bom para detectar repetições |

### 3. Filtragem por confiança de segmento

O `faster_whisper` retorna métricas por segmento que antes eram ignoradas:

- `no_speech_prob`: probabilidade de não ser fala (0.0 a 1.0)
- `avg_logprob`: log-probabilidade média do segmento

Segmentos com `no_speech_prob > 0.7` agora são descartados — provavelmente são ruído ou respiração.

### 4. Limpeza de texto

Remoção de artefatos comuns que o Whisper gera:
- `[BLANK_AUDIO]`, `(silêncio)`, etc.
- Espaços duplos e whitespace desnecessário

---

## Melhorias futuras (roadmap)

### Prioridade alta
- **Noise reduction**: usar filtro de redução de ruído (ex: `noisereduce` ou spectral gating) antes da transcrição
- **Modelo fine-tuned PT-BR**: treinar/usar modelo ajustado especificamente para português brasileiro informal

### Prioridade média
- **Word-level confidence**: usar `word_timestamps=True` para marcar palavras incertas na UI
- **Prompt dinâmico**: adaptar `initial_prompt` baseado no contexto da conversa

### Prioridade baixa
- **Apple Speech (macOS)**: módulo nativo Swift usando SFSpeechRecognizer para Macs sem GPU NVIDIA
- **Ensemble**: transcrever com 2 modelos e comparar resultados
