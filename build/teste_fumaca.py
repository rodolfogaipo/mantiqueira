"""Teste rápido feito na máquina de montagem (sem placa de vídeo, sem microfone):
confere se as bibliotecas carregam, se a IA responde em JSON, se as vozes geram áudio e se o Whisper carrega.
Uso: <dist>\\python\\python.exe teste_fumaca.py <dist>"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DIST = Path(sys.argv[1]).resolve()
os.environ["MANTIQUEIRA_RAIZ"] = str(DIST)
os.environ["COQUI_TOS_AGREED"] = "1"
sys.path.insert(0, str(DIST / "app"))
falhas = []


def etapa(nome):
    def dec(fn):
        t = time.time()
        try:
            fn()
            print(f"[OK]   {nome} ({time.time() - t:.0f}s)", flush=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[ERRO] {nome}: {e}", flush=True)
            falhas.append(nome)
        return fn
    return dec


@etapa("bibliotecas")
def _():
    import torch, numpy, psutil, sounddevice, keyboard, webview, mss, vosk, faster_whisper  # noqa
    from TTS.tts.models.xtts import Xtts  # noqa
    import winsdk.windows.media.ocr  # noqa
    print("   torch", torch.__version__, "cuda compilado:", torch.version.cuda)


@etapa("módulos da Mantiqueira")
def _():
    from mantiqueira import config, db, textutil, sistema, ia, ouvido, voz, olhos, tela, cerebro, rotinas, nucleo, api  # noqa


@etapa("IA local responde em JSON")
def _():
    from mantiqueira import paths
    from mantiqueira.cerebro import ESQUEMA
    from mantiqueira.ia import PORTA, extrair_json
    p = subprocess.Popen([str(paths.LLAMA_CPU), "-m", str(paths.LLM_NORMAL), "--host", "127.0.0.1",
                          "--port", str(PORTA), "-c", "4096", "-ngl", "0"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(240):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/health", timeout=2) as r:
                    if b"ok" in r.read():
                        break
            except Exception:
                time.sleep(1)
        corpo = {"messages": [{"role": "system", "content": "Você é a Mantiqueira. AGORA: quarta-feira, 28 de outubro de 2026, 10:00. Responda em JSON com resposta, acao (nenhuma|criar_lembrete), quando (AAAA-MM-DD HH:MM) e texto."},
                              {"role": "user", "content": "me lembra amanhã às 9 de ligar pro fornecedor"}],
                 "max_tokens": 150, "temperature": 0.2,
                 "response_format": {"type": "json_object", "schema": ESQUEMA}}
        req = urllib.request.Request(f"http://127.0.0.1:{PORTA}/v1/chat/completions",
                                     data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
        print("   resposta:", txt)
        dados = extrair_json(txt)
        assert dados.get("acao") == "criar_lembrete", dados
    finally:
        p.kill()


@etapa("voz rápida (Piper)")
def _():
    from mantiqueira import paths
    r = subprocess.run([str(paths.PIPER_EXE), "--model", str(paths.PIPER_VOZ), "--output_raw"],
                       input="Olá, senhor. Teste de voz.".encode("utf-8"), capture_output=True, timeout=120,
                       cwd=str(paths.PIPER_EXE.parent))
    assert len(r.stdout) > 10000, r.stderr.decode("utf-8", "replace")[-500:]


@etapa("voz natural (XTTS) gera áudio")
def _():
    import torch
    from mantiqueira import paths
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    cfg = XttsConfig()
    cfg.load_json(str(paths.XTTS / "config.json"))
    m = Xtts.init_from_config(cfg)
    m.load_checkpoint(cfg, checkpoint_dir=str(paths.XTTS), use_deepspeed=False, eval=True)
    nomes = list(m.speaker_manager.speakers.keys())
    print("   vozes:", len(nomes), nomes[:6])
    sp = m.speaker_manager.speakers["Damien Black" if "Damien Black" in nomes else nomes[0]]
    with torch.inference_mode():
        out = m.inference("Olá, senhor.", "pt", sp["gpt_cond_latent"], sp["speaker_embedding"])
    assert len(out["wav"]) > 5000


@etapa("ouvido (Whisper + Vosk)")
def _():
    import numpy as np
    from mantiqueira.ouvido import Transcritor
    from mantiqueira import paths
    from vosk import Model
    Model(str(paths.VOSK))
    t = Transcritor()
    t.carregar()
    t.transcrever(np.zeros(16000, dtype=np.float32))


if falhas:
    print("FALHAS:", falhas)
    sys.exit(1)
print("TUDO OK")
