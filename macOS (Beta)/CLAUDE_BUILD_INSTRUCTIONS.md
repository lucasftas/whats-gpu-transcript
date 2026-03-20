# WhatsGPU macOS — Instruções para Claude Code compilar

## Contexto

Você está no repositório `whats-gpu-transcript`. A pasta `macOS (Beta)/` contém o código-fonte da versão macOS do WhatsGPU — um app que transcreve áudios do WhatsApp Web localmente usando `SFSpeechRecognizer` (API nativa Apple).

O código foi escrito no Windows e **nunca foi compilado ou testado no macOS**. Seu trabalho é compilar, testar e deixar funcionando.

---

## Arquitetura

```
WhatsApp Web (Chrome) → Extensão Chrome → Flask server (localhost:8765) → Swift binary (SFSpeechRecognizer) → Texto
```

### Arquivos do projeto (`macOS (Beta)/`):

| Arquivo | O que faz |
|---------|-----------|
| `transcribe.swift` | CLI tool Swift que recebe path de áudio e retorna JSON com texto transcrito via SFSpeechRecognizer. Usa offline mode (macOS 13+). |
| `transcriber.py` | Classe Python `Transcriber` que chama o binário Swift via subprocess. Mesma interface da versão Windows. |
| `app.py` | Servidor Flask (porta 8765) + menu bar via `rumps`. Rotas: `/health`, `/status`, `/transcribe`. Auto-start via LaunchAgent. |
| `requirements.txt` | `flask`, `waitress`, `rumps`, `Pillow` |
| `build.sh` | Script de build (compilar Swift + PyInstaller) |
| `extension/` | Extensão Chrome simplificada (sem UI de modelos — SFSpeechRecognizer é built-in) |

---

## Passo a passo — O que você deve fazer

### 1. Verificar pré-requisitos

```bash
# Verificar versão do macOS (precisa ser 13+ Ventura para offline)
sw_vers

# Verificar se Xcode CLI tools está instalado
xcode-select -p
# Se não estiver: xcode-select --install

# Verificar Python 3
python3 --version

# Verificar Swift
swiftc --version
```

### 2. Compilar o binário Swift

```bash
cd "macOS (Beta)"
swiftc transcribe.swift -o transcribe -framework Speech -framework AVFoundation
chmod +x transcribe
```

**Se der erro**: pode ser que o SFSpeechRecognizer precise de entitlements ou que o formato .ogg não seja suportado nativamente pelo AVFoundation.

**Possíveis problemas e soluções:**

- **Erro de compilação Speech framework**: verifique se Xcode CLI tools está atualizado
- **Formato .ogg não suportado**: o WhatsApp envia áudio em .ogg (Opus codec). O AVFoundation do macOS pode não suportar .ogg nativamente. Se for o caso, adicione conversão com `ffmpeg` ou `afconvert` antes de transcrever:
  ```bash
  # Instalar ffmpeg se necessário
  brew install ffmpeg
  ```
  E no `transcriber.py`, antes de chamar o Swift binary, converta .ogg para .wav:
  ```python
  subprocess.run(["ffmpeg", "-i", input_ogg, "-ar", "16000", "-ac", "1", output_wav])
  ```

### 3. Testar o binário Swift isoladamente

```bash
# Baixar um áudio de teste (ou usar qualquer .wav/.m4a)
# Testar transcrição
./transcribe /path/to/audio.wav pt-BR
```

Deve retornar JSON: `{"text": "texto transcrito", "duration": 5.2, "error": null}`

**Na primeira execução**: o macOS vai pedir permissão de "Reconhecimento de Fala". Aceite.

### 4. Instalar dependências Python

```bash
pip3 install -r requirements.txt
```

### 5. Testar o servidor Flask

```bash
python3 app.py
```

Deve aparecer:
- Menu bar com "W" no topo da tela
- Log: "Servidor iniciando em 127.0.0.1:8765"

Testar endpoint:
```bash
curl http://localhost:8765/health
```

Deve retornar:
```json
{"status": "ok", "platform": "macos", "engine": "SFSpeechRecognizer", "chip": "Apple M2 Pro", "model_loaded": true}
```

### 6. Testar transcrição end-to-end

```bash
# Enviar um arquivo de áudio para transcrever
curl -X POST -F "file=@/path/to/audio.wav" http://localhost:8765/transcribe
```

### 7. Testar extensão Chrome

1. Abrir `chrome://extensions/`
2. Ativar Modo Desenvolvedor
3. Carregar sem compactação → selecionar pasta `macOS (Beta)/extension/`
4. Abrir WhatsApp Web
5. Clicar "Transcrever" em qualquer áudio

### 8. Build final com PyInstaller (opcional)

```bash
pip3 install pyinstaller
pyinstaller --onedir --windowed --name "WhatsGPU" \
    --add-binary "transcribe:." \
    app.py
```

O app bundle ficará em `dist/WhatsGPU/`.

---

## Problemas conhecidos que você pode encontrar

### 1. .ogg não suportado pelo AVFoundation
O WhatsApp envia áudios em formato Opus (.ogg). O macOS pode não decodificar nativamente.

**Solução**: instalar ffmpeg e converter antes de transcrever. Modificar `transcriber.py`:

```python
def _convert_to_wav(self, ogg_path):
    """Convert .ogg to .wav using ffmpeg."""
    wav_path = ogg_path.replace(".ogg", ".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
        capture_output=True, timeout=30,
    )
    return wav_path
```

### 2. Permissão de Speech Recognition negada
O macOS pede permissão na primeira vez. Se o usuário negar, o `transcribe.swift` retorna erro.

**Solução**: o erro já é tratado no Swift e retorna JSON com mensagem clara.

### 3. rumps não funciona sem GUI
Se rodar via SSH ou terminal sem GUI, `rumps` pode falhar.

**Solução**: já existe fallback no `app.py` — se `rumps` falhar, roda só o Flask server sem menu bar.

### 4. PyInstaller .app não encontra o binário Swift
O binário `transcribe` precisa estar no bundle.

**Solução**: o `build.sh` já usa `--add-binary "transcribe:."` que inclui o binário no bundle. O `transcriber.py` já procura o binário via `sys._MEIPASS`.

---

## Checklist final

- [ ] `swiftc transcribe.swift` compila sem erros
- [ ] `./transcribe audio.wav` retorna JSON com texto
- [ ] `python3 app.py` inicia servidor na porta 8765
- [ ] `curl localhost:8765/health` retorna status ok
- [ ] `curl -F "file=@audio.wav" localhost:8765/transcribe` retorna texto
- [ ] Extensão Chrome conecta e mostra "WhatsGPU rodando"
- [ ] Transcrição funciona via extensão no WhatsApp Web
- [ ] Se .ogg não funcionar: implementar conversão ffmpeg
- [ ] Build PyInstaller gera app bundle funcional

Quando todos os itens estiverem ✓, faça commit com as correções e me avise o que precisou mudar.
