"""Voz: neural natural (XTTS v2, na placa de vídeo) com reserva rápida (Piper, no processador)."""
import json
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
        import torch
        import sounddevice as sd
        lat, emb = self._lat(voz_id)
        with torch.inference_mode():
            partes = self.xtts.inference_stream(texto, "pt", lat, emb, enable_text_splitting=True,
                                                temperature=0.65, speed=1.05)
            with sd.OutputStream(samplerate=24000, channels=1, dtype="float32") as out:
                for p in partes:
                    a = p.squeeze().float().cpu().numpy().astype(np.float32)
                    out.write(a.reshape(-1, 1))

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
            sd.play(audio, taxa)
            sd.wait()
