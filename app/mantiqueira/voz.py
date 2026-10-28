"""Voz: neural natural (XTTS v2, na placa de vídeo) com reserva rápida (Piper, no processador)."""
import json
import re
import queue
import subprocess
import threading
import logging
import numpy as np
from . import paths, sistema, textutil

log = logging.getLogger("voz")

# Vozes masculinas do XTTS (as que existirem no arquivo de vozes serão oferecidas)
VOZES_XTTS = [
    "Damien Black", "Viktor Eka", "Craig Gutsy", "Aaron Dreschner", "Baldur Sanjin", "Luis Moray",
    "Marcos Rudaski", "Gilberto Mathias", "Torcull Diarmuid", "Viktor Menelaos", "Ludvig Milivoj",
]
VOZ_PERSONALIZADA_WAV = paths.DADOS / "voz_personalizada.wav"
VOZ_PERSONALIZADA_PT = paths.DADOS / "voz_personalizada.pt"


def dividir_frases(texto, limite=190):
    """Divide em frases curtas (o XTTS fica instável com trechos longos)."""
    partes = [p.strip() for p in re.split(r"(?<=[.!?…;:])\s+", texto) if p.strip()]
    out = []
    for p in partes:
        while len(p) > limite:
            corte = p.rfind(",", 0, limite)
            corte = corte if corte > 40 else p.rfind(" ", 0, limite)
            corte = corte if corte > 0 else limite
            out.append(p[:corte + 1].strip())
            p = p[corte + 1:].strip()
        if p:
            out.append(p)
    # a voz natural às vezes LÊ o ponto final ("ponto"); tirar a pontuação do fim (menos ? e !)
    limpo = []
    for f in out:
        f = re.sub(r"[.;:…,]+$", "", f.strip()).strip()
        if f:
            limpo.append(f)
    return limpo or [texto.strip(" .")]


def suavizar(wav, sr=24000):
    """Tira cliques no começo e no fim do áudio."""
    n = min(len(wav) // 4, int(sr * 0.012))
    if n > 0:
        rampa = np.linspace(0, 1, n, dtype=np.float32)
        wav[:n] *= rampa
        wav[-n:] *= rampa[::-1]
    pico = float(np.max(np.abs(wav))) if wav.size else 0
    if pico > 0.99:
        wav = wav / pico * 0.95
    return wav


class Voz:
    def __init__(self, nucleo, ao_inicio, ao_fim):
        self.n = nucleo
        self.ao_inicio = ao_inicio
        self.ao_fim = ao_fim
        self.q = queue.Queue()
        self.xtts = None
        self.xtts_dispositivo = None
        self._latentes = {}
        self.falando = False
        self.tipo_atual = "—"
        threading.Thread(target=self._loop, daemon=True, name="voz").start()

    # ---------------------------------------------------------------- carregar
    def carregar(self):
        if not (paths.XTTS / "model.pth").exists():
            log.warning("XTTS ausente; usando voz rápida")
            return
        try:
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
            cfg = XttsConfig()
            cfg.load_json(str(paths.XTTS / "config.json"))
            m = Xtts.init_from_config(cfg)
            m.load_checkpoint(cfg, checkpoint_dir=str(paths.XTTS), use_deepspeed=False, eval=True)
            g = sistema.gpu(max_idade=0)
            if torch.cuda.is_available() and (g is None or g["livre"] > 2300):
                try:
                    m.cuda()
                    self.xtts_dispositivo = "cuda"
                except RuntimeError:
                    log.warning("sem memória na placa para a voz natural", exc_info=True)
                    m.cpu()
                    torch.cuda.empty_cache()
            if self.xtts_dispositivo != "cuda":
                # no processador a voz natural fica lenta demais; usa a rápida
                log.warning("voz natural sem placa de vídeo disponível; usando voz rápida")
                del m
                return
            self.xtts = m
            log.info("voz natural carregada na placa de vídeo")
        except Exception:
            log.exception("falha ao carregar a voz natural")
            self.xtts = None

    def vozes(self):
        lista = []
        if self.xtts is not None:
            existentes = set(self._falantes())
            for i, nome in enumerate([v for v in VOZES_XTTS if v in existentes], start=1):
                lista.append({"id": f"xtts:{nome}", "nome": f"Natural {i} — {nome}"})
            if VOZ_PERSONALIZADA_WAV.exists():
                lista.append({"id": "xtts:personalizada", "nome": "Personalizada (gravação)"})
        if paths.PIPER_VOZ.exists():
            lista.append({"id": "piper:faber", "nome": "Rápida — Faber (mais robótica)"})
        return lista

    def voz_padrao(self):
        v = self.n.cfg["voz"]
        ids = [x["id"] for x in self.vozes()]
        if v in ids:
            return v
        return ids[0] if ids else ""

    def _falantes(self):
        try:
            return list(self.xtts.speaker_manager.speakers.keys())
        except Exception:
            return []

    def _lat(self, voz_id):
        if voz_id in self._latentes:
            return self._latentes[voz_id]
        import torch
        if voz_id == "xtts:personalizada":
            if VOZ_PERSONALIZADA_PT.exists():
                lat, emb = torch.load(str(VOZ_PERSONALIZADA_PT), map_location=self.xtts_dispositivo)
            else:
                lat, emb = self.xtts.get_conditioning_latents(audio_path=[str(VOZ_PERSONALIZADA_WAV)],
                                                              gpt_cond_len=30, max_ref_length=60)
                torch.save((lat, emb), str(VOZ_PERSONALIZADA_PT))
        else:
            nome = voz_id.split(":", 1)[1]
            sp = self.xtts.speaker_manager.speakers[nome]
            if isinstance(sp, dict) and "gpt_cond_latent" in sp:
                lat, emb = sp["gpt_cond_latent"], sp["speaker_embedding"]
            else:
                lat, emb = list(sp.values())[:2]
        self._latentes[voz_id] = (lat, emb)
        return lat, emb

    def voz_personalizada_atualizada(self):
        self._latentes.pop("xtts:personalizada", None)
        try:
            VOZ_PERSONALIZADA_PT.unlink()
        except FileNotFoundError:
            pass

    # ---------------------------------------------------------------- falar
    def falar(self, texto, voz_id=None):
        texto = textutil.para_fala(texto or "")
        if texto:
            self.q.put((texto, voz_id))

    def _loop(self):
        while True:
            texto, voz_id = self.q.get()
            voz_id = voz_id or self.voz_padrao()
            self.falando = True
            try:
                self.ao_inicio()
            except Exception:
                pass
            try:
                if voz_id.startswith("xtts:") and self.xtts is not None:
                    try:
                        self._falar_xtts(texto, voz_id)
                        self.tipo_atual = "NATURAL"
                    except Exception:
                        log.exception("voz natural falhou; usando a rápida")
                        self._limpar_gpu()
                        self._falar_piper(texto)
                else:
                    self._falar_piper(texto)
            except Exception:
                log.exception("não foi possível falar")
            finally:
                self.falando = False
                if self.q.empty():
                    try:
                        self.ao_fim()
                    except Exception:
                        pass

    def _limpar_gpu(self):
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    def _falar_xtts(self, texto, voz_id):
        """Gera frase por frase: enquanto uma toca, a próxima já está sendo gerada (sem engasgos)."""
        import torch
        import sounddevice as sd
        lat, emb = self._lat(voz_id)
        frases = dividir_frases(texto)
        fila = queue.Queue(maxsize=4)
        erro = []

        def gerar():
            try:
                with torch.inference_mode():
                    for f in frases:
                        out = self.xtts.inference(f, "pt", lat, emb, temperature=0.6, repetition_penalty=5.0,
                                                  top_p=0.85, speed=1.0, enable_text_splitting=False)
                        wav = np.asarray(out["wav"], dtype=np.float32)
                        fila.put(suavizar(wav))
            except Exception as e:
                erro.append(e)
            finally:
                fila.put(None)

        threading.Thread(target=gerar, daemon=True, name="voz-gerar").start()
        pausa = np.zeros(int(24000 * 0.18), dtype=np.float32)
        tocou = False
        while True:
            a = fila.get()
            if a is None:
                break
            sd.play(np.concatenate([a, pausa]), 24000, blocking=True, latency="high")
            tocou = True
        if erro and not tocou:
            raise erro[0]

    def _falar_piper(self, texto):
        import sounddevice as sd
        if not (paths.PIPER_EXE.exists() and paths.PIPER_VOZ.exists()):
            log.error("voz rápida ausente")
            return
        cfg = json.loads(paths.PIPER_VOZ.with_suffix(".onnx.json").read_text(encoding="utf-8"))
        taxa = int(cfg.get("audio", {}).get("sample_rate", 22050))
        r = subprocess.run([str(paths.PIPER_EXE), "--model", str(paths.PIPER_VOZ), "--output_raw",
                            "--length_scale", "0.95"], input=texto.encode("utf-8"), capture_output=True,
                           timeout=60, creationflags=sistema.SEM_JANELA, cwd=str(paths.PIPER_EXE.parent))
        audio = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size:
            self.tipo_atual = "RÁPIDA"
            sd.play(audio, taxa, blocking=True, latency="high")
