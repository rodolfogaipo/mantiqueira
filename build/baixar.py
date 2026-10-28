"""Baixa os modelos e programas auxiliares para dentro da pasta de distribuição.
Uso: python baixar.py <pasta_dist>"""
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

DIST = Path(sys.argv[1]).resolve()
MOD = DIST / "modelos"
BIN = DIST / "bin"
TMP = DIST.parent / "tmp_downloads"
for p in (MOD, BIN, TMP):
    p.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(*a, flush=True)


def baixar(url, destino: Path):
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0:
        log("já existe:", destino.name)
        return destino
    log("baixando", url)
    req = urllib.request.Request(url, headers={"User-Agent": "mantiqueira-build"})
    tmp = destino.with_suffix(destino.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        lido, marca = 0, 0
        while True:
            b = r.read(8 * 2**20)
            if not b:
                break
            f.write(b)
            lido += len(b)
            if total and lido * 10 // total > marca:
                marca = lido * 10 // total
                log(f"  {destino.name}: {marca * 10}%")
    tmp.replace(destino)
    log(f"  ok {destino.name} ({destino.stat().st_size / 2**20:.0f} MB)")
    return destino


def hf(repo, arquivo, destino: Path):
    return baixar(f"https://huggingface.co/{repo}/resolve/main/{arquivo}", destino)


def extrair(zip_path, destino):
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(destino)


# ------------------------------------------------------------------ IA (Qwen 2.5)
hf("bartowski/Qwen2.5-3B-Instruct-GGUF", "Qwen2.5-3B-Instruct-Q4_K_M.gguf", MOD / "ia" / "normal.gguf")
if os.environ.get("SEM_TURBO") != "1":
    hf("bartowski/Qwen2.5-7B-Instruct-GGUF", "Qwen2.5-7B-Instruct-Q4_K_M.gguf", MOD / "ia" / "turbo.gguf")

# ------------------------------------------------------------------ ouvido
for f in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
    hf("Systran/faster-whisper-small", f, MOD / "whisper-small" / f)
if not (MOD / "vosk-pt").exists():
    z = baixar("https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip", TMP / "vosk.zip")
    extrair(z, TMP / "vosk")
    pasta = next(p for p in (TMP / "vosk").iterdir() if p.is_dir())
    shutil.move(str(pasta), str(MOD / "vosk-pt"))

# ------------------------------------------------------------------ voz natural (XTTS v2)
for f in ("config.json", "model.pth", "vocab.json", "speakers_xtts.pth", "mel_stats.pth"):
    hf("coqui/XTTS-v2", f, MOD / "xtts" / f)

# ------------------------------------------------------------------ voz rápida (Piper)
for f in ("pt_BR-faber-medium.onnx", "pt_BR-faber-medium.onnx.json"):
    hf("rhasspy/piper-voices", f"pt/pt_BR/faber/medium/{f}", MOD / "piper" / f)
if not (BIN / "piper" / "piper.exe").exists():
    z = baixar("https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip",
               TMP / "piper.zip")
    extrair(z, BIN)


# ------------------------------------------------------------------ llama.cpp (servidor da IA)
def gh_json(url):
    h = {"User-Agent": "mantiqueira-build", "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        return json.loads(r.read().decode())


def versao_cuda(nome):
    m = re.search(r"(?:cuda-|cu)(1[23])\.?(\d*)", nome)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def achar_llama():
    for rel in gh_json("https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15"):
        nomes = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        cuda = [n for n in nomes if re.match(r"^llama-.*bin-win-cuda-?(cu)?12[\d.]*-x64\.zip$", n)]
        cudart = [n for n in nomes if re.match(r"^cudart-llama-bin-win-(cuda-|cu)12[\d.]*-x64\.zip$", n)]
        cpu = [n for n in nomes if re.match(r"^llama-.*bin-win-(cpu|avx2)-x64\.zip$", n)]
        if cuda and cudart and cpu:
            c = max(cuda, key=versao_cuda)
            v = versao_cuda(c)
            cr = [x for x in cudart if versao_cuda(x) == v] or cudart
            log("llama.cpp", rel["tag_name"], c)
            return nomes[c], nomes[cr[0]], nomes[cpu[0]]
    raise SystemExit("Não encontrei os arquivos do llama.cpp para Windows")


def instalar_llama(urls_zip, destino: Path):
    if (destino / "llama-server.exe").exists():
        return
    work = TMP / destino.name
    for i, u in enumerate(urls_zip):
        z = baixar(u, TMP / f"{destino.name}_{i}.zip")
        extrair(z, work)
    exe = next(work.rglob("llama-server.exe"), None)
    if exe is None:
        raise SystemExit(f"llama-server.exe não encontrado em {urls_zip}")
    destino.mkdir(parents=True, exist_ok=True)
    origem = exe.parent
    for p in work.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".exe", ".dll"):
            alvo = destino / p.name
            if not alvo.exists():
                shutil.copy2(p, alvo)
    log("instalado", destino, "a partir de", origem)


url_cuda, url_cudart, url_cpu = achar_llama()
instalar_llama([url_cuda, url_cudart], BIN / "llama-cuda")
instalar_llama([url_cpu], BIN / "llama-cpu")

shutil.rmtree(TMP, ignore_errors=True)
log("downloads concluídos")
