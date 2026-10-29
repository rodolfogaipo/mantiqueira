"""Saudação de abertura "Bem-vindo de volta, senhor", como nos filmes.

A frase é gravada uma vez com a voz escolhida (dados/saudacao.wav) e, nas próximas aberturas, toca logo no
início — antes de carregar a IA e a voz — usando só o som do Windows (rápido, sem bibliotecas pesadas).
Também é usada quando o senhor desbloqueia o computador ou volta depois de um tempo parado."""
import json
import time
import wave
import logging
import datetime as dt
from . import paths

log = logging.getLogger("saudacao")
WAV = paths.DADOS / "saudacao.wav"
META = paths.DADOS / "saudacao.json"


def texto(cfg):
    return f"Bem-vindo de volta, {cfg['tratamento']}."


def silencio_ativo(cfg):
    """Horário de silêncio (Configurações) ou modo silencioso pedido."""
    try:
        if time.time() < float(cfg["silencio_ate"] or 0):
            return True
    except (TypeError, ValueError):
        pass
    agora_hm = dt.datetime.now().strftime("%H:%M")
    for faixa in cfg["silencio_horarios"] or []:
        try:
            ini, fim = [x.strip().zfill(5) for x in str(faixa).split("-")]
        except ValueError:
            continue
        if (ini <= agora_hm < fim) if ini <= fim else (agora_hm >= ini or agora_hm < fim):
            return True
    return False


def _meta():
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pronta(cfg):
    """Há uma gravação válida para o tratamento atual?"""
    return WAV.exists() and _meta().get("texto") == texto(cfg)


def tocar(cfg, esperar=False):
    """Toca a saudação gravada. Devolve True se tocou."""
    if not pronta(cfg) or silencio_ativo(cfg):
        return False
    try:
        import winsound
        flags = winsound.SND_FILENAME | winsound.SND_NODEFAULT
        if not esperar:
            flags |= winsound.SND_ASYNC
        winsound.PlaySound(str(WAV), flags)
        return True
    except Exception:
        log.exception("tocar saudação")
        return False


def precisa_gravar(cfg, voz_id):
    m = _meta()
    return not WAV.exists() or m.get("texto") != texto(cfg) or m.get("voz") != voz_id \
        or abs(float(m.get("volume", 1.0)) - float(cfg["voz_volume"] or 1.0)) > 0.01


def gravar(voz, cfg):
    """Grava a saudação com a voz escolhida (em segundo plano, depois que a voz carregou)."""
    import numpy as np
    voz_id = voz.voz_padrao()
    if not voz_id or not precisa_gravar(cfg, voz_id):
        return False
    audio, taxa = voz.gerar_audio(texto(cfg), voz_id)
    if audio is None or not len(audio):
        return False
    try:
        v = max(0.15, min(1.8, float(cfg["voz_volume"] or 1.0)))
    except (TypeError, ValueError):
        v = 1.0
    pcm = (np.clip(np.asarray(audio, dtype=np.float32) * v, -1, 1) * 32767).astype(np.int16)
    tmp = WAV.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(taxa))
        w.writeframes(pcm.tobytes())
    tmp.replace(WAV)
    META.write_text(json.dumps({"texto": texto(cfg), "voz": voz_id, "volume": v}, ensure_ascii=False), encoding="utf-8")
    log.info("saudação gravada com a voz %s", voz_id)
    return True
