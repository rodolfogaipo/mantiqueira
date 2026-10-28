"""Ouvido: microfone, palavra de ativação ("Mantiqueira"), gravação do comando e transcrição."""
import json
import queue
import threading
import time
import logging
import collections
import numpy as np
from . import paths, textutil

log = logging.getLogger("ouvido")
TAXA = 16000
BLOCO = 1600   # 0,1 s


class Transcritor:
    def __init__(self):
        self.modelo = None

    def carregar(self):
        from faster_whisper import WhisperModel
        import os
        self.modelo = WhisperModel(str(paths.WHISPER), device="cpu", compute_type="int8",
                                   cpu_threads=max(4, (os.cpu_count() or 8) // 2))
        log.info("Whisper carregado")

    def transcrever(self, audio_f32: np.ndarray) -> str:
        if self.modelo is None or audio_f32.size < TAXA * 0.3:
            return ""
        segs, _ = self.modelo.transcribe(
            audio_f32, language="pt", beam_size=3, vad_filter=False, condition_on_previous_text=False,
            initial_prompt="Mantiqueira, SolidWorks, pérgola, DXF, orçamento, lembrete, Excel.")
        return " ".join(s.text.strip() for s in segs).strip()


class Ouvido:
    """Estados: ocioso (esperando a palavra), gravando, ocupado (processando/falando), fixo (gravando voz)."""

    def __init__(self, nucleo, ao_acordar, ao_comando, ao_cancelar):
        self.n = nucleo
        self.ao_acordar = ao_acordar
        self.ao_comando = ao_comando
        self.ao_cancelar = ao_cancelar
        self.q = queue.Queue(maxsize=200)
        self.modo = "ocioso"
        self.stream = None
        self.vosk = None
        self.rec = None
        self.ok = False
        self.erro = ""
        self._buf = []
        self._fixo = None
        self._fixo_evento = threading.Event()
        self._piso = 200.0
        self._anel = collections.deque(maxlen=7)
        self._ultimo_acordar = 0
        self._parar = False

    # ---------------------------------------------------------------- dispositivos
    @staticmethod
    def microfones():
        import sounddevice as sd
        lista = []
        try:
            for i, d in enumerate(sd.query_devices()):
                if d.get("max_input_channels", 0) > 0:
                    api = sd.query_hostapis(d["hostapi"])["name"]
                    if "MME" in api or "WASAPI" in api:
                        lista.append({"id": i, "nome": f"{d['name']} ({api})"})
        except Exception:
            log.exception("não foi possível listar microfones")
        return lista

    # ---------------------------------------------------------------- ciclo
    def iniciar(self):
        try:
            from vosk import Model, KaldiRecognizer, SetLogLevel
            SetLogLevel(-1)
            if paths.VOSK.exists():
                self.vosk = Model(str(paths.VOSK))
                self.rec = KaldiRecognizer(self.vosk, TAXA)
        except Exception:
            log.exception("Vosk indisponível; ativação por voz desligada")
        threading.Thread(target=self._loop, daemon=True, name="ouvido").start()

    def _abrir(self):
        import sounddevice as sd

        def cb(dados, frames, t, status):
            try:
                self.q.put_nowait(dados[:, 0].copy())
            except queue.Full:
                pass

        disp = self.n.cfg["microfone"]
        try:
            self.stream = sd.InputStream(samplerate=TAXA, channels=1, dtype="int16", blocksize=BLOCO,
                                         device=disp, callback=cb)
            self.stream.start()
        except Exception:
            if disp is not None:
                log.warning("microfone escolhido falhou; usando o padrão")
                self.stream = sd.InputStream(samplerate=TAXA, channels=1, dtype="int16", blocksize=BLOCO,
                                             callback=cb)
                self.stream.start()
            else:
                raise
        self.ok = True
        self.erro = ""
        log.info("microfone aberto")

    def reiniciar_microfone(self):
        try:
            if self.stream:
                self.stream.stop(); self.stream.close()
        except Exception:
            pass
        self.stream = None
        self.ok = False

    def _loop(self):
        while not self._parar:
            if self.stream is None:
                try:
                    self._abrir()
                except Exception as e:
                    self.ok = False
                    self.erro = "Microfone não encontrado"
                    log.warning("sem microfone: %s", e)
                    time.sleep(8)
                    continue
            try:
                bloco = self.q.get(timeout=1.0)
            except queue.Empty:
                if self.stream is not None and not self.stream.active:
                    self.reiniciar_microfone()
                continue
            try:
                self._processar(bloco)
            except Exception:
                log.exception("erro processando áudio")

    def _processar(self, bloco):
        self._anel.append(bloco)
        rms = float(np.sqrt(np.mean(bloco.astype(np.float32) ** 2)))
        if self.modo == "fixo":
            self._fixo.append(bloco)
            if sum(len(b) for b in self._fixo) >= self._fixo_alvo:
                self.modo = "ocupado"
                self._fixo_evento.set()
            return
        if self.modo == "ocupado":
            return
        if self.modo == "ocioso":
            if rms < self._piso * 3:
                self._piso = 0.97 * self._piso + 0.03 * max(rms, 40.0)
            if self.rec is not None and self.n.cfg["ativacao_por_voz"]:
                if self.rec.AcceptWaveform(bloco.tobytes()):
                    txt = json.loads(self.rec.Result()).get("text", "")
                else:
                    txt = json.loads(self.rec.PartialResult()).get("partial", "")
                if txt and time.time() - self._ultimo_acordar > 2 and \
                        textutil.parece_ativacao(txt, self.n.cfg["palavras_ativacao"]):
                    self._ultimo_acordar = time.time()
                    self.rec.Reset()
                    log.info("palavra de ativação ouvida: %r", txt)
                    self._comecar(preroll=True)
                    self.ao_acordar(True)
            return
        if self.modo == "gravando":
            self._buf.append(bloco)
            limiar = max(self._piso * 2.6, 260.0)
            if rms > limiar:
                self._fala_blocos += 1
                if self._fala_blocos >= 2:
                    self._falou = True
                self._silencio = 0
            else:
                self._silencio += 1
            dur = len(self._buf) * BLOCO / TAXA
            if self._falou and self._silencio >= 8:
                self._finalizar()
            elif not self._falou and dur > 6.0:
                self.modo = "ocioso"
                self._buf = []
                self.ao_cancelar()
            elif dur > 15.0:
                self._finalizar()

    def _comecar(self, preroll):
        self._buf = list(self._anel) if preroll else []
        self._falou = False
        self._fala_blocos = 0
        self._silencio = 0
        self.modo = "gravando"

    def _finalizar(self):
        audio = np.concatenate(self._buf).astype(np.float32) / 32768.0
        self._buf = []
        self.modo = "ocupado"
        threading.Thread(target=self.ao_comando, args=(audio,), daemon=True).start()

    # ---------------------------------------------------------------- controles
    def ouvir_agora(self):
        """Botão do microfone ou Ctrl+Espaço: começa a gravar o comando sem a palavra de ativação."""
        if self.modo in ("ocioso",):
            self._comecar(preroll=False)
            self.ao_acordar(False)
            return True
        return False

    def ocupar(self):
        self.modo = "ocupado"

    def liberar(self):
        # descarta o que foi captado enquanto o Mantiqueira falava, para ele não ouvir a si mesma
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self._anel.clear()
        if self.rec is not None:
            self.rec.Reset()
        self.modo = "ocioso"

    def gravar_fixo(self, segundos=20.0):
        """Grava um trecho de duração fixa (para criar a voz personalizada)."""
        self._fixo = []
        self._fixo_alvo = int(segundos * TAXA)
        self._fixo_evento.clear()
        self.modo = "fixo"
        if not self._fixo_evento.wait(segundos + 10):
            self.modo = "ocioso"
            return None
        audio = np.concatenate(self._fixo)
        self._fixo = None
        self.liberar()
        return audio


def bipe(tipo="inicio"):
    """Sinal curto para indicar que começou ou terminou de ouvir."""
    try:
        import sounddevice as sd
        sr = 24000
        freqs = (880, 1320) if tipo == "inicio" else (1100, 700)
        partes = []
        for f in freqs:
            t = np.arange(int(sr * 0.07)) / sr
            env = np.minimum(1, np.minimum(t, t[::-1]) * 60)
            partes.append(0.18 * np.sin(2 * np.pi * f * t) * env)
        sd.play(np.concatenate(partes).astype(np.float32), sr)
    except Exception:
        pass


def toque_lembrete():
    """Toque de três notas antes do aviso falado (bloqueia ~0,6 s)."""
    import sounddevice as sd
    sr = 24000
    partes = []
    for f in (784, 988, 1319):
        t = np.arange(int(sr * 0.16)) / sr
        env = np.exp(-t * 9) * np.minimum(1, t * 400)
        partes.append(0.22 * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env)
    sd.play(np.concatenate(partes).astype(np.float32), sr, blocking=True)
