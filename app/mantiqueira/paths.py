"""Caminhos do programa. A pasta raiz é a que contém python/, app/, modelos/ e bin/."""
import os
from pathlib import Path

APP = Path(__file__).resolve().parent.parent          # .../app
RAIZ = Path(os.environ.get("MANTIQUEIRA_RAIZ", APP.parent))
MODELOS = RAIZ / "modelos"
BIN = RAIZ / "bin"
DADOS = RAIZ / "dados"
UI = APP / "ui"

DADOS.mkdir(parents=True, exist_ok=True)

# Modelos
LLM_NORMAL = MODELOS / "ia" / "normal.gguf"
LLM_TURBO = MODELOS / "ia" / "turbo.gguf"
WHISPER = MODELOS / "whisper-small"
VOSK = MODELOS / "vosk-pt"
XTTS = MODELOS / "xtts"
PIPER_VOZ = MODELOS / "piper" / "pt_BR-faber-medium.onnx"

# Programas auxiliares
LLAMA_CUDA = BIN / "llama-cuda" / "llama-server.exe"
LLAMA_CPU = BIN / "llama-cpu" / "llama-server.exe"
PIPER_EXE = BIN / "piper" / "piper.exe"
LAUNCHER = RAIZ / "Mantiqueira.exe"
