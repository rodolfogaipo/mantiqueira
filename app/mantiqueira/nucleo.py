"""Núcleo: liga ouvido, voz, cérebro, olhos e rotinas, e entrega o estado para as telas."""
import os
import time
import wave
import shutil
import logging
import threading
import datetime as dt
from pathlib import Path
from . import paths, textutil, sistema
from .config import Config
from .db import Banco, agora, d as parse_dt

log = logging.getLogger("nucleo")


def montar_partes():
    """Junta arquivos grandes que vieram divididos (arquivo.parte001, .parte002…), caso o instalador não tenha juntado."""
    grupos = {}
    for p in paths.RAIZ.rglob("*.parte001"):
        base = str(p)[: -len(".parte001")]
        grupos[base] = sorted(Path(p.parent).glob(Path(base).name + ".parte*"))
    for base, partes in grupos.items():
        log.info("juntando %s (%d partes)", base, len(partes))
        tmp = base + ".juntando"
        with open(tmp, "wb") as out:
            for pt in partes:
                with open(pt, "rb") as f:
                    shutil.copyfileobj(f, out, 16 * 2**20)
        os.replace(tmp, base)
        for pt in partes:
            pt.unlink()


class Nucleo:
    def __init__(self):
        self.cfg = Config()
        self.db = Banco(paths.DADOS / "mantiqueira.db")
        self.estado = "carregando"   # carregando|ocioso|gravando|transcrevendo|pensando|falando
        self.boot_msg = "Iniciando sistemas…"
        self.pronto = False
        self.erros = []
        self.ia = self.voz = self.ouvido = self.transcritor = self.olhos = self.cerebro = self.rotinas = None
        self.conhecimento = None
        self.holo = None
        self.saindo = False
        self.indice = self.memoria = self.frases = self.sistemas = self.intencoes = None
        self.detalhe_texto = ""          # lista de caminhos etc. mostrada na tela junto da resposta
        self.contexto_extra = ""
        self.latencia = None
        self.alerta = None
        self.janelas = {"main": None, "mini": None, "barra": None}
        self.mini_visivel = False
        self._mini_motivo = None
        self._esconder_em = 0
        self._reouvir = False
        self._por_voz = False
        self.aviso_gravacao = ""
        self.ultima = {"usuario": "", "assistente": "", "detalhe": ""}
        for r in self.db.conversa_ultimas(2):
            self.ultima["usuario" if r["papel"] == "usuario" else "assistente"] = r["texto"]

    # ================================================================== inicialização
    def iniciar(self):
        threading.Thread(target=self._boot, daemon=True, name="boot").start()
        threading.Thread(target=self._vigia_mini, daemon=True, name="mini").start()

    def _passo(self, msg, fn):
        self.boot_msg = msg
        try:
            fn()
            return True
        except Exception as e:
            log.exception("falha em: %s", msg)
            self.erros.append(f"{msg} {e}")
            return False

    def _boot(self):
        from .olhos import Olhos
        from .rotinas import Rotinas
        from .voz import Voz
        from .ia import IA
        from .cerebro import Cerebro
        from .ouvido import Ouvido, Transcritor

        self._passo("Preparando arquivos (primeira vez pode demorar)…", montar_partes)

        def olhos():
            self.olhos = Olhos(self)
            self.olhos.iniciar()
        self._passo("Abrindo os olhos…", olhos)

        def holo():
            from .holo import Holo
            self.holo = Holo(self)
        self._passo("Preparando o holograma…", holo)
        self.rotinas = Rotinas(self)

        def voz():
            self.voz = Voz(self, self._voz_inicio, self._voz_fim)
            self.voz.carregar()
        self._passo("Carregando a voz…", voz)

        def conhecimento():
            from .conhecimento import Conhecimento
            self.conhecimento = Conhecimento()
            self.conhecimento.importar_guias()
        self._passo("Carregando a base de conhecimento…", conhecimento)

        def extras():
            from .indice import Indice
            from .memoria import Memoria
            from .frases import Frases
            from .sistemas_web import SistemasWeb
            from .intencoes import Intencoes
            self.memoria = Memoria(self)
            self.frases = Frases(self.db)
            self.sistemas = SistemasWeb(self)
            self.intencoes = Intencoes(self)
            self.indice = Indice(self)
            self.indice.iniciar()
        self._passo("Preparando memória e mapa de arquivos…", extras)

        self.cerebro = Cerebro(self)

        def ia():
            self.ia = IA(self)
            self.ia.iniciar()
            threading.Thread(target=self.ia.vigiar_modo, daemon=True, name="ia-modo").start()
        self._passo("Carregando a inteligência…", ia)

        def ouvido():
            self.transcritor = Transcritor()
            self.transcritor.carregar()
            self.ouvido = Ouvido(self, self._acordou, self._comando, self._cancelou)
            self.ouvido.iniciar()
        self._passo("Carregando o ouvido…", ouvido)

        def atalho():
            import keyboard
            keyboard.add_hotkey(self.cfg["atalho"], self.ouvir_agora, suppress=False)
            keyboard.add_hotkey(self.cfg["atalho_barra"], self.alternar_barra, suppress=False)
        self._passo("Registrando os atalhos…", atalho)

        threading.Thread(target=self.rotinas.loop_lembretes, daemon=True, name="lembretes").start()
        threading.Thread(target=self.rotinas.loop_pendencias, daemon=True, name="pendencias").start()
        if self.cfg["iniciar_com_windows"]:
            threading.Thread(target=sistema.iniciar_com_windows, args=(True,), daemon=True).start()

        self.pronto = True
        self.estado = "ocioso"
        self.boot_msg = ""
        log.info("Mantiqueira pronta. Erros: %s", self.erros)
        time.sleep(1.0)
        try:
            self.falar_aviso(self.rotinas.boas_vindas())
        except Exception:
            log.exception("boas-vindas falhou")

    # ================================================================== conversa
    def ouvir_agora(self):
        if self.ouvido and self.pronto and self.estado == "ocioso":
            return self.ouvido.ouvir_agora()
        return False

    def _acordou(self, por_voz):
        from .ouvido import bipe
        self._por_voz = por_voz
        self.estado = "gravando"
        bipe("inicio")
        self.mostrar_mini_seguro(True, "conversa")

    def _cancelou(self):
        self.estado = "ocioso"
        self._esconder_em = time.time() + 1.5

    def _comando(self, audio):
        self.estado = "transcrevendo"
        try:
            texto = self.transcritor.transcrever(audio)
        except Exception:
            log.exception("transcrição falhou")
            texto = ""
        texto = textutil.remover_ativacao(texto, self.cfg["palavras_ativacao"])
        log.info("ouvi: %r", texto)
        if len(texto.strip(" .,!?")) < 2:
            if self._por_voz:
                self._reouvir = True
                self.voz.falar(f"Pois não, {self.cfg['tratamento']}?") if self.voz else None
                if not self.voz:
                    self._liberar()
            else:
                self._liberar()
            return
        self._processar(texto, "voz")

    def processar_texto_async(self, texto, origem="texto"):
        texto = (texto or "").strip()
        if not texto:
            return
        if self.ouvido:
            self.ouvido.ocupar()
        threading.Thread(target=self._processar, args=(texto, origem), daemon=True).start()

    def _processar(self, texto, origem):
        self.estado = "pensando"
        self.ultima = {"usuario": texto, "assistente": "", "detalhe": ""}
        self.detalhe_texto = ""
        self.db.conversa_add("usuario", texto)
        try:
            resposta = self.cerebro.processar(texto) if self.cerebro else "Ainda estou iniciando."
        except Exception:
            log.exception("processar")
            resposta = "Desculpe, tive um problema agora. Pode repetir?"
        self.db.conversa_add("assistente", resposta + (("\n" + self.detalhe_texto) if self.detalhe_texto else ""))
        detalhe = self.detalhe_texto
        if self.voz and (self.cfg["responder_falando"] or origem in ("voz", "barra")):
            self._mostrar_junto_da_voz(resposta, detalhe)
        else:
            self.ultima.update(assistente=resposta, detalhe=detalhe)
            self._liberar()

    def _mostrar_junto_da_voz(self, texto, detalhe=""):
        """O texto aparece na tela frase por frase, conforme a voz vai falando."""
        import re as _re
        frases = [f for f in _re.split(r"(?<=[.!?…])\s+", texto) if f.strip()] or [texto]

        def ao_frase(k, total):
            n = max(1, min(len(frases), round(k / max(1, total) * len(frases))))
            self.ultima["assistente"] = " ".join(frases[:n])
            if k >= total:
                self.ultima["assistente"] = texto
                self.ultima["detalhe"] = detalhe
        self.voz.falar(texto, ao_frase=ao_frase)

    def parar_fala(self):
        if self.voz:
            self.voz.parar()
        if self.ultima.get("assistente") is not None and self.cerebro and self.cerebro.historico:
            ult = self.cerebro.historico[-1]
            if ult["role"] == "assistant":
                self.ultima["assistente"] = ult["content"]
                self.ultima["detalhe"] = self.detalhe_texto

    def _liberar(self):
        self.estado = "ocioso"
        if self.ouvido:
            self.ouvido.liberar()
        self._esconder_em = time.time() + 8

    def _voz_inicio(self):
        self.estado = "falando"
        if self.ouvido:
            self.ouvido.ocupar()

    def _voz_fim(self):
        time.sleep(0.25)
        self._liberar()
        if self._reouvir:
            self._reouvir = False
            self.ouvir_agora()

    def falar_aviso(self, texto):
        self.ultima = {"usuario": "", "assistente": "", "detalhe": ""}
        self.db.conversa_add("assistente", texto)
        if self.voz:
            self._mostrar_junto_da_voz(texto)
        else:
            self.ultima["assistente"] = texto

    # ================================================================== barra rápida
    def alternar_barra(self):
        w = self.janelas.get("barra")
        if not w:
            return
        try:
            if getattr(self, "_barra_visivel", False):
                w.hide()
                self._barra_visivel = False
                return
            w.show()
            self._barra_visivel = True
            threading.Thread(target=self._focar_barra, daemon=True).start()
        except Exception:
            log.exception("barra")

    def _focar_barra(self):
        import ctypes
        time.sleep(0.15)
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, "Mantiqueira — barra")
        if hwnd:
            u.keybd_event(0x12, 0, 0, 0)          # ALT: libera o Windows a trazer a janela para frente
            u.keybd_event(0x12, 0, 2, 0)
            u.SetForegroundWindow(hwnd)
        try:
            self.janelas["barra"].evaluate_js("document.getElementById('q').focus()")
        except Exception:
            pass

    def esconder_barra(self):
        w = self.janelas.get("barra")
        if w:
            try:
                w.hide()
            except Exception:
                pass
        self._barra_visivel = False

    def alertar_lembrete(self, l, repeticao=0):
        """Avisa um lembrete: toque + voz primeiro; a janelinha abre em paralelo (uma coisa não trava a outra)."""
        log.info("LEMBRETE disparado (id %s, repetição %s): %s", l["id"], repeticao, l["texto"])
        self.alerta = {"id": l["id"], "texto": l["texto"], "hora": parse_dt(l["quando"]).strftime("%H:%M")}
        trat = self.cfg["tratamento"]
        if repeticao:
            frase = f"{trat[:1].upper() + trat[1:]}, lembrando de novo: {l['texto']}."
        else:
            frase = f"{trat[:1].upper() + trat[1:]}, está na hora: {l['texto']}."
        try:
            from .ouvido import toque_lembrete
            toque_lembrete()
        except Exception:
            log.exception("toque do lembrete")
        try:
            self.falar_aviso(frase)
        except Exception:
            log.exception("voz do lembrete")
        threading.Thread(target=self.mostrar_mini_seguro, args=(True, "alerta"), daemon=True).start()

    # ================================================================== janela flutuante
    def _principal_em_foco(self):
        try:
            from .olhos import janela_ativa
            j = janela_ativa()
            return bool(j and j[0] == os.getpid() and self.janelas["main"] and not self.mini_visivel)
        except Exception:
            return False

    def mostrar_mini_seguro(self, mostrar=True, motivo="conversa"):
        w = self.janelas.get("mini")
        if not w:
            return
        try:
            if mostrar:
                if motivo == "conversa" and self._principal_em_foco():
                    return
                self._mini_motivo = motivo
                self._esconder_em = time.time() + (120 if motivo == "alerta" else 25)
                if not self.mini_visivel:
                    w.show()
                    self.mini_visivel = True
            else:
                if self.mini_visivel:
                    w.hide()
                    self.mini_visivel = False
        except Exception:
            log.exception("janela flutuante")

    def _vigia_mini(self):
        while True:
            time.sleep(1)
            if not self.mini_visivel:
                continue
            if self._mini_motivo == "alerta" and self.alerta:
                if time.time() > self._esconder_em:
                    self.alerta = None
                    self.mostrar_mini_seguro(False)
                continue
            if self.estado == "ocioso" and time.time() > self._esconder_em:
                self.mostrar_mini_seguro(False)

    # ================================================================== base de conhecimento
    def adicionar_documentos(self, caminhos):
        base = self.conhecimento
        if not base:
            return
        feitos, erros = [], []
        for c in caminhos:
            base.status = f"Lendo {os.path.basename(c)}…"
            try:
                nome, pag, tre = base.adicionar(c)
                feitos.append(nome if tre >= 0 else nome + " (já estava na base)")
            except Exception as e:
                log.exception("documento %s", c)
                erros.append(f"{os.path.basename(c)}: {e}")
        msg = ""
        if feitos:
            msg += "Aprendido: " + ", ".join(feitos) + ". "
        if erros:
            msg += "Não consegui ler: " + "; ".join(erros)
        base.status = msg.strip()

    # ================================================================== voz personalizada
    def gravar_voz_personalizada(self):
        from .ouvido import bipe, TAXA
        from .voz import VOZ_PERSONALIZADA_WAV
        if not self.ouvido or not self.ouvido.ok:
            self.aviso_gravacao = "Microfone não encontrado."
            return
        for i in (3, 2, 1):
            self.aviso_gravacao = f"Prepare-se… começa em {i}"
            time.sleep(1)
        bipe("inicio")
        self.aviso_gravacao = "Gravando: fale naturalmente por 20 segundos (leia qualquer texto em voz alta)…"
        audio = self.ouvido.gravar_fixo(20)
        bipe("fim")
        if audio is None:
            self.aviso_gravacao = "Não consegui gravar. Tente de novo."
            return
        with wave.open(str(VOZ_PERSONALIZADA_WAV), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(TAXA)
            w.writeframes(audio.tobytes())
        if self.voz:
            self.voz.voz_personalizada_atualizada()
        self.cfg.atualizar({"voz": "xtts:personalizada"})
        self.aviso_gravacao = "Voz gravada. Ela já está escolhida — clique em Testar para ouvir."

    def _holo_ui(self):
        try:
            if not self.holo:
                return {"tipo": "logo", "chave": "logo"}
            foco = self.olhos.foco if self.olhos else None
            inativo = bool(self.olhos and self.olhos.inativo)
            h = self.holo.estado(foco, inativo)
            return {k: h.get(k) for k in ("tipo", "chave", "url")}
        except Exception:
            log.exception("holo")
            return {"tipo": "logo", "chave": "logo"}

    # ================================================================== estado para a tela
    def estado_ui(self):
        cfg = self.cfg
        cpu, ram_u, ram_t, ram_p = sistema.cpu_ram()
        g = sistema.gpu()
        foco = None
        if self.olhos and self.olhos.foco:
            f = self.olhos.foco
            nome = f["arquivo"] or textutil.curto(f["titulo"], 40)
            foco = {"app": f["app"], "arquivo": nome, "nao_salvo": bool(f.get("nao_salvo")),
                    "tempo": textutil.duracao_texto(self.olhos.tempo_hoje(f["app"], nome)),
                    "cad": f["app"] in textutil.CAD}
        agenda = []
        hoje = dt.date.today()
        for l in self.db.lembretes_proximos(5):
            q = parse_dt(l["quando"])
            if q.date() == hoje:
                dia = "HOJE"
            elif q.date() == hoje + dt.timedelta(days=1):
                dia = "AMANHÃ"
            else:
                dia = f"{textutil.DIAS_SEMANA[q.weekday()][:3].upper()} {q:%d/%m}"
            agenda.append({"id": l["id"], "quando": q.isoformat(), "hora": f"{q:%H:%M}", "dia": dia,
                           "texto": l["texto"], "repetir": l["repetir"]})
        pend = [{"id": p["id"], "texto": p["texto"], "arquivo": p["arquivo"] or ""}
                for p in self.db.pendencias_abertas()[:3]]

        ia_ok = bool(self.ia and self.ia.pronta)
        disp = self.ia.dispositivo if self.ia else "—"
        sub = [
            {"nome": "OUVIDO", "pct": 1.0 if (self.ouvido and self.ouvido.ok) else 0.05,
             "val": "ATIVO" if (self.ouvido and self.ouvido.ok) else ("SEM MIC" if self.ouvido else "—"),
             "alerta": not (self.ouvido and self.ouvido.ok)},
            {"nome": "NÚCLEO IA", "pct": {"GPU": 1.0, "GPU+CPU": 0.7, "CPU": 0.4}.get(disp, 0.05) if ia_ok else 0.05,
             "val": (self.ia.modelo or "").upper() if ia_ok else "—", "alerta": not ia_ok},
            {"nome": "VOZ", "pct": 1.0 if (self.voz and self.voz.xtts) else (0.6 if self.voz else 0.05),
             "val": "NATURAL" if (self.voz and self.voz.xtts) else ("RÁPIDA" if self.voz else "—"), "alerta": False},
            {"nome": "VISÃO", "pct": 0.0 if not cfg["olhos_ativos"] else (0.35 if (self.olhos and self.olhos.inativo) else 1.0),
             "val": "DESL" if not cfg["olhos_ativos"] else ("PAUSA" if (self.olhos and self.olhos.inativo) else "REC"),
             "alerta": True},
            {"nome": "RAM", "pct": ram_p / 100, "val": f"{ram_u:.1f}G", "alerta": ram_p > 90},
        ]
        if g:
            sub.append({"nome": "VRAM", "pct": g["usada"] / max(1, g["total"]), "val": f"{g['usada'] / 1024:.1f}G",
                        "alerta": g["usada"] / max(1, g["total"]) > 0.92})
        return {
            "pronto": self.pronto, "boot": self.boot_msg, "erros": self.erros[-3:],
            "estado": self.estado, "tema": cfg["tema"], "nome": cfg["nome"],
            "cpu": round(cpu), "ram": f"{ram_u:.1f}/{ram_t:.0f}G",
            "gpu": (f"{g['usada'] / 1024:.1f}/{g['total'] / 1024:.0f}G" if g else "—"),
            "modo_ia": (self.ia.modelo or "—").upper() if self.ia else "—", "dispositivo": disp,
            "latencia": round(self.latencia, 1) if self.latencia else None,
            "sub": sub, "agenda": agenda, "foco": foco, "pendencias": pend,
            "registro": self.olhos.registro_recente(4) if self.olhos else [],
            "holo": self._holo_ui(),
            "ultima": self.ultima, "alerta": self.alerta,
            "indice": (self.indice.resumo() if self.indice else []), "aviso_gravacao": self.aviso_gravacao,
            "palavra": "MANTIQUEIRA", "atalho": cfg["atalho"].upper().replace("SPACE", "ESPAÇO"),
            "ativacao": bool(cfg["ativacao_por_voz"]),
        }
