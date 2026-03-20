# WhatsGPU macOS (Beta)

Versão macOS do WhatsGPU usando **SFSpeechRecognizer** — o motor de transcrição nativo da Apple.

## Diferenças da versão Windows

| Característica | Windows | macOS |
|----------------|---------|-------|
| Motor de transcrição | faster-whisper (Whisper) | SFSpeechRecognizer (nativo Apple) |
| Aceleração | GPU NVIDIA (CUDA) | Neural Engine (Apple Silicon) |
| Download de modelos | Sim (75 MB - 3.1 GB) | Não necessário (built-in) |
| Tamanho do app | ~1.2 GB | ~5 MB |
| Menu do sistema | Bandeja (system tray) | Menu bar |

## Requisitos

- macOS 13+ (Ventura) — necessário para transcrição offline
- Apple Silicon (M1/M2/M3) ou Intel
- Google Chrome
- Python 3.10+
- Xcode Command Line Tools (`xcode-select --install`)

## Instalação

### 1. Compilar

```bash
cd "macOS (Beta)"

# Compilar Swift helper
swiftc transcribe.swift -o transcribe -framework Speech -framework AVFoundation

# Instalar dependências Python
pip3 install -r requirements.txt

# Rodar
python3 app.py
```

Ou use o script completo:

```bash
chmod +x build.sh
./build.sh
```

### 2. Extensão Chrome

1. Abra `chrome://extensions/`
2. Ative **Modo do desenvolvedor**
3. Clique **Carregar sem compactação**
4. Selecione a pasta `macOS (Beta)/extension/`

### 3. Permissão

Na primeira transcrição, o macOS pedirá permissão para **Reconhecimento de Fala**.
Aceite para que funcione corretamente.

## Como funciona

```
WhatsApp Web ──> Extensão Chrome ──> Flask (localhost:8765) ──> Swift (SFSpeechRecognizer) ──> Texto
```

1. A extensão captura o áudio da mensagem no WhatsApp Web
2. Envia para o servidor Flask local (porta 8765)
3. O servidor salva o áudio como arquivo temporário
4. Chama o binário Swift que usa SFSpeechRecognizer
5. O texto transcrito retorna para a extensão

## Limitações (Beta)

- Transcrição offline requer macOS 13+ (Ventura)
- Qualidade pode ser inferior ao Whisper large-v3 em alguns casos
- Não há seleção de modelos (usa o modelo built-in do macOS)
- Suporte a formatos de áudio depende do AVFoundation

## Estrutura

```
macOS (Beta)/
├── app.py              # Servidor Flask + menu bar (rumps)
├── transcriber.py      # Wrapper Python → Swift binary
├── transcribe.swift    # SFSpeechRecognizer CLI tool
├── requirements.txt    # Dependências Python
├── build.sh            # Script de build
├── extension/          # Extensão Chrome (simplificada)
└── README.md
```
