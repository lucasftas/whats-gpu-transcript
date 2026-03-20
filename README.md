# WhatsGPU - Transcreva áudios do WhatsApp com GPU local

Extensão Chrome + app companion que transcreve áudios do WhatsApp Web localmente usando sua GPU NVIDIA. Nenhum dado sai do seu computador.

## Como funciona

```
WhatsApp Web (Chrome) ──> Extensão captura áudio ──> Companion App (GPU) ──> Texto no chat
```

1. **Extensão Chrome** injeta botão "Transcrever" ao lado de cada áudio no WhatsApp Web
2. **Companion App** roda como bandeja do sistema, recebe o áudio via HTTP local e transcreve usando [faster-whisper](https://github.com/SYSTRAN/faster-whisper) com aceleração CUDA
3. O texto transcrito aparece diretamente no chat

## Requisitos

- Windows 10/11
- GPU NVIDIA com drivers atualizados (GTX 1060+ / RTX série)
- Google Chrome
- ~3 GB de espaço em disco (modelo large-v3)

## Instalação

### 1. Companion App

- **[Baixar WhatsGPU-Setup.exe](https://github.com/lucasftas/whats-GPU/releases/latest/download/WhatsGPU-Setup.exe)** (download direto)
- Ou acesse a [página de releases](https://github.com/lucasftas/whats-GPU/releases) para ver todas as versões
- Execute o instalador e selecione os modelos desejados
- O app inicia automaticamente na bandeja do sistema

### 2. Extensão Chrome

1. Abra

```
chrome://extensions/
```

2. Ative **Modo do desenvolvedor** (canto superior direito)
3. Clique **Carregar sem compactação**
4. Selecione a pasta `extension/`

### 3. Usar

1. Abra o [WhatsApp Web](https://web.whatsapp.com)
2. Clique no botão **Transcrever** ao lado de qualquer áudio
3. Aguarde a transcrição aparecer

## Modelos disponíveis

| Modelo   | Tamanho | VRAM mínima | Precisão  | Velocidade   |
| -------- | ------- | ----------- | --------- | ------------ |
| large-v3 | 3.1 GB  | 10 GB       | Excelente | Normal       |
| medium   | 1.5 GB  | 5 GB        | Muito boa | Rápida       |
| small    | 466 MB  | 2 GB        | Boa       | Muito rápida |
| base     | 142 MB  | 1 GB        | Razoável  | Ultra rápida |
| tiny     | 75 MB   | 1 GB        | Baixa     | Instantânea  |

Os modelos são baixados para `Documentos/WhatsGPU/Modelos/` e podem ser trocados a qualquer momento pelo popup da extensão.

## Funcionalidades

- **Gerenciamento de modelos**: baixe, troque e remova modelos pelo popup
- **Progresso em tempo real**: acompanhe o download e a transcrição
- **Controle de GPU**: suba/descarregue modelos da GPU manualmente
- **Slider de precisão**: ajuste entre Rápido, Balanceado e Máxima direto no popup
- **Ícone na bandeja**: cinza (sem modelo), amarelo (processando), verde (pronto)
- **Auto-start**: opção para iniciar com o Windows
- **VAD (Voice Activity Detection)**: filtra silêncio automaticamente
- **Desinstalador completo**: remove app, modelos, registro e guia remoção da extensão Chrome
- **Privacidade total**: tudo roda local, nenhum áudio é enviado para servidores

## Controle de precisão

O popup da extensão inclui um slider de precisão com 3 níveis:

| Nível      | Parâmetros                                    | Uso                                       |
| ---------- | --------------------------------------------- | ----------------------------------------- |
| Rápido     | beam=1, best_of=1                             | Transcrição instantânea, precisão básica   |
| Balanceado | beam=5, best_of=5                             | Padrão — bom equilíbrio velocidade/precisão |
| Máxima     | beam=10, best_of=10, patience=2, temp fallback | Precisão máxima, significativamente mais lento |

- No modo **Máxima**, se o modelo carregado for pequeno (tiny/base/small), um aviso sugere trocar para o `large-v3`
- O **temperature fallback** (modo Máxima) re-tenta segmentos com baixa confiança usando temperaturas progressivas — ajuda com pronúncia difícil e áudio ruidoso

## Desinstalação

### Companion App

- **[Baixar WhatsGPU-Uninstall.exe](https://github.com/lucasftas/whats-GPU/releases/latest/download/WhatsGPU-Uninstall.exe)** (download direto)
- Ou execute pelo menu Iniciar → WhatsGPU → Desinstalar, ou pelo Painel de Controle

O desinstalador irá:

1. Fechar o WhatsGPU automaticamente
2. Remover registro de auto-start do Windows
3. Perguntar se deseja remover os modelos baixados (libera espaço em disco)
4. Exibir instruções de remoção da extensão Chrome

### Extensão Chrome

1. Abra `chrome://extensions/` no Chrome
2. Encontre **"Whats GPU"** na lista
3. Clique em **Remover** e confirme

Ou: clique com botão direito no ícone da extensão → **Remover do Chrome**

## Build from source

### Companion App

```bash
cd companion-app
pip install -r requirements.txt
pip install nvidia-cublas-cu12 pyinstaller

# Build
build.bat
```

O executável será gerado em `companion-app/dist/`.

### Extensão

A extensão não precisa de build - carregue a pasta `extension/` diretamente no Chrome.

## Tecnologias

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - Whisper otimizado com CTranslate2
- [CTranslate2](https://github.com/OpenNMT/CTranslate2) - Inferência otimizada para GPU
- CUDA 12 + cuBLAS - Aceleração NVIDIA
- Flask + Waitress - Servidor HTTP local
- Chrome Extension Manifest V3

## Estrutura do projeto

```
whats-gpu-transcript/
├── companion-app/          # Backend Python (servidor + transcrição)
│   ├── app.py              # Servidor Flask + bandeja do sistema
│   ├── transcriber.py      # Transcrição com faster-whisper
│   ├── model_manager.py    # Download e gerenciamento de modelos
│   ├── build.bat           # Script de compilação PyInstaller
│   ├── installer.iss       # Script do instalador Inno Setup
│   └── requirements.txt
├── extension/              # Extensão Chrome (Manifest V3)
│   ├── manifest.json
│   ├── popup.html/js       # Interface do popup
│   ├── content.js          # Injeta botões no WhatsApp Web
│   ├── page.js             # Captura áudio das mensagens
│   └── service_worker.js   # Background service worker
├── README.md
└── LICENSE (MIT)
```

## Licença

MIT
