"""Cérebro local: controla o llama-server (llama.cpp) e conversa com ele por HTTP em 127.0.0.1."""
import json
import os
import re
import subprocess
import threading
import time
import logging
import urllib.request
import urllib.error
from . import paths, sistema

log = logging.getLogger("ia")
PORTA = 18765

# camadas aproximadas de cada modelo (para dividir entre placa de vídeo e processador)
CAMADAS = {"normal": 36, "turbo": 28}


class IA:
    def __init__(self, nucleo):
        self.n = nucleo
        self.proc = None
        self.modelo = None          # "normal" | "turbo"
        self.dispositivo = "—"      # "GPU", "GPU+CPU", "CPU"
        self.ocupada = threading.Lock()
        self.ultimo_uso = time.time()
        self.pronta = False
        self._log = None

    # ------------------------------------------------------------------ servidor
    def turbo_disponivel(self):
        return paths.LLM_TURBO.exists()

    def modelo_desejado(self):
        modo = self.n.cfg["modo_ia"]
        if not self.turbo_disponivel():
            return "normal"
        if modo == "turbo":
            return "turbo"
        if modo == "auto":
            return "normal" if sistema.solidworks_aberto() else "turbo"
        return "normal"

    def _camadas_gpu(self, arquivo, qual):
        g = sistema.gpu(max_idade=0)
        if not g or not paths.LLAMA_CUDA.exists():
            return 0
        tam = arquivo.stat().st_size / 2**20
        n = CAMADAS.get(qual, 32)
        livre = g["livre"] - 900                 # folga para o Windows, a voz e o SolidWorks
        precisa = tam + 650                      # modelo + contexto
        if livre >= precisa:
            return 99
        por_camada = tam / (n + 2)
        return max(0, min(n, int((livre - 550) / por_camada)))

    def iniciar(self, qual=None):
        qual = qual or self.modelo_desejado()
        arquivo = paths.LLM_TURBO if qual == "turbo" else paths.LLM_NORMAL
        if not arquivo.exists():
            raise FileNotFoundError(f"Modelo de IA não encontrado: {arquivo}")
        self.parar()
        ngl = self._camadas_gpu(arquivo, qual)
        tentativas = []
        if paths.LLAMA_CUDA.exists() and ngl > 0:
            tentativas.append((paths.LLAMA_CUDA, ngl))
        if paths.LLAMA_CPU.exists():
            tentativas.append((paths.LLAMA_CPU, 0))
        if paths.LLAMA_CUDA.exists():
            tentativas.append((paths.LLAMA_CUDA, 0))
        threads = max(4, (os.cpu_count() or 8) // 2)
        for exe, camadas in tentativas:
            cmd = [str(exe), "-m", str(arquivo), "--host", "127.0.0.1", "--port", str(PORTA),
                   "-c", "8192", "-ngl", str(camadas), "-t", str(threads), "--parallel", "1"]
            log.info("iniciando IA: %s", " ".join(cmd))
            self._log = open(paths.DADOS / "ia.log", "ab")
            self.proc = subprocess.Popen(cmd, stdout=self._log, stderr=subprocess.STDOUT,
                                         creationflags=sistema.SEM_JANELA, cwd=str(exe.parent))
            if self._esperar(180):
                self.modelo = qual
                self.dispositivo = "GPU" if camadas >= 99 else ("GPU+CPU" if camadas > 0 else "CPU")
                self.pronta = True
                log.info("IA pronta (%s, %s)", qual, self.dispositivo)
                return True
            log.warning("IA não subiu com %s (camadas=%s)", exe.name, camadas)
            self.parar()
        raise RuntimeError("Não foi possível iniciar a IA local. Veja dados/ia.log.")

    def _esperar(self, segundos):
        fim = time.time() + segundos
        while time.time() < fim:
            if self.proc.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/health", timeout=2) as r:
                    if r.status == 200 and b"ok" in r.read():
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def parar(self):
        self.pronta = False
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(8)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        if self._log:
            try:
                self._log.close()
            except Exception:
                pass
            self._log = None

    def vigiar_modo(self):
        """Troca entre normal e turbo quando estiver parada (modo auto ou mudança nas configurações)."""
        while True:
            time.sleep(20)
            try:
                if not self.pronta or self.n.estado in ("gravando", "transcrevendo", "pensando", "falando"):
                    continue
                if time.time() - self.ultimo_uso < 30:
                    continue
                desejado = self.modelo_desejado()
                if desejado != self.modelo:
                    with self.ocupada:
                        log.info("trocando IA para %s", desejado)
                        self.n.boot_msg = "Trocando modo da IA…"
                        self.iniciar(desejado)
                        self.n.boot_msg = ""
            except Exception:
                log.exception("falha ao trocar modo da IA")

    # ------------------------------------------------------------------ conversa
    def conversar(self, mensagens, esquema=None, max_tokens=350, temperatura=0.4):
        corpo = {"messages": mensagens, "temperature": temperatura, "max_tokens": max_tokens,
                 "cache_prompt": True}
        if esquema:
            corpo["response_format"] = {"type": "json_object", "schema": esquema}
        with self.ocupada:
            self.ultimo_uso = time.time()
            try:
                txt = self._post(corpo)
            except urllib.error.HTTPError as e:
                if esquema and e.code == 400:
                    corpo.pop("response_format", None)
                    txt = self._post(corpo)
                else:
                    raise
            self.ultimo_uso = time.time()
        if not esquema:
            return txt
        return extrair_json(txt)

    def _post(self, corpo):
        req = urllib.request.Request(f"http://127.0.0.1:{PORTA}/v1/chat/completions",
                                     data=json.dumps(corpo).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return resp["choices"][0]["message"]["content"] or ""


def extrair_json(txt: str) -> dict:
    try:
        return json.loads(txt)
    except Exception:
        pass
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {"resposta": txt.strip(), "acao": "nenhuma"}
