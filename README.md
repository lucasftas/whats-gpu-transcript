# WhatsGPU - Transcreva audios do WhatsApp com GPU local

Extensao Chrome + app companion que transcreve audios do WhatsApp Web localmente usando sua GPU NVIDIA. Nenhum dado sai do seu computador.

## Como funciona

```
WhatsApp Web (Chrome) ──> Extensao captura audio ──> Companion App (GPU) ──> Texto no chat
```

1. **Extensao Chrome** injeta botao "Transcrever" ao lado de cada audio no WhatsApp Web
2. **Companion App** roda como bandeja do sistema, recebe o audio via HTTP local e transcreve usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) com aceleracao CUDA
3. O texto transcrito aparece diretamente no chat

## Requisitos

- Windows 10/11
- GPU NVIDIA com drivers atualizados (GTX 1060+ / RTX serie)
- Google Chrome
- ~3 GB de espaco em disco (modelo large-v3)

## Instalacao

### 1. Companion App

- Baixe o `WhatsGPU-Setup.exe` da [pagina de releases](../../releases)
- Execute o instalador e selecione os modelos desejados
- O app inicia automaticamente na bandeja do sistema

### 2. Extensao Chrome

1. Abra `chrome://extensions/`
2. Ative **Modo do desenvolvedor** (canto superior direito)
3. Clique **Carregar sem compactacao**
4. Selecione a pasta `extension/`

### 3. Usar

1. Abra o [WhatsApp Web](https://web.whatsapp.com)
2. Clique no botao **Transcrever** ao lado de qualquer audio
3. Aguarde a transcricao aparecer

## Modelos disponiveis

| Modelo | Tamanho | VRAM minima | Precisao | Velocidade |
|--------|---------|-------------|----------|------------|
| large-v3 | 3.1 GB | 10 GB | Excelente | Normal |
| medium | 1.5 GB | 5 GB | Muito boa | Rapida |
| small | 466 MB | 2 GB | Boa | Muito rapida |
| base | 142 MB | 1 GB | Razoavel | Ultra rapida |
| tiny | 75 MB | 1 GB | Baixa | Instantanea |

Os modelos sao baixados para `Documentos/WhatsGPU/Modelos/` e podem ser trocados a qualquer momento pelo popup da extensao.

## Funcionalidades

- **Gerenciamento de modelos**: baixe, troque e remova modelos pelo popup
- **Progresso em tempo real**: acompanhe o download e a transcricao
- **Controle de GPU**: suba/descarregue modelos da GPU manualmente
- **Icone na bandeja**: cinza (sem modelo), amarelo (processando), verde (pronto)
- **Auto-start**: opcao para iniciar com o Windows
- **VAD (Voice Activity Detection)**: filtra silencio automaticamente
- **Privacidade total**: tudo roda local, nenhum audio e enviado para servidores

## Build from source

### Companion App

```bash
cd companion-app
pip install -r requirements.txt
pip install nvidia-cublas-cu12 pyinstaller

# Build
build.bat
```

O executavel sera gerado em `companion-app/dist/Whats GPU/`.

### Extensao

A extensao nao precisa de build - carregue a pasta `extension/` diretamente no Chrome.

## Tecnologias

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - Whisper otimizado com CTranslate2
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) - Inferencia otimizada para GPU
- CUDA 12 + cuBLAS - Aceleracao NVIDIA
- Flask + Waitress - Servidor HTTP local
- Chrome Extension Manifest V3

## Estrutura do projeto

```
whats-gpu-transcript/
├── companion-app/          # Backend Python (servidor + transcricao)
│   ├── app.py              # Servidor Flask + bandeja do sistema
│   ├── transcriber.py      # Transcricao com faster-whisper
│   ├── model_manager.py    # Download e gerenciamento de modelos
│   ├── build.bat           # Script de compilacao PyInstaller
│   └── requirements.txt
├── extension/              # Extensao Chrome (Manifest V3)
│   ├── manifest.json
│   ├── popup.html/js       # Interface do popup
│   ├── content.js          # Injeta botoes no WhatsApp Web
│   ├── page.js             # Captura audio das mensagens
│   └── service_worker.js   # Background service worker
├── README.md
└── LICENSE (MIT)
```

## Licenca

MIT
