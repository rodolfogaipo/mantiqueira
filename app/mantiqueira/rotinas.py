"""Rotinas em segundo plano: disparo de lembretes, pendências percebidas e o "bom dia"."""
import time
import logging
import datetime as dt
from . import textutil
from .db import agora, d as parse_dt
from .olhos import segundos_inativo

log = logging.getLogger("rotinas")

DOCS = (".sldprt", ".sldasm", ".slddrw", ".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".pptx", ".dxf", ".dwg")


class Rotinas:
    def __init__(self, nucleo):
        self.n = nucleo
        self.db = nucleo.db

    # ------------------------------------------------------------------ lembretes
    def loop_lembretes(self):
        while True:
            time.sleep(5)
            try:
                for l in self.db.lembretes_vencidos():
                    self.db.lembrete_status(l["id"], "avisado")
                    if l["repetir"]:
                        prox = textutil.proxima_repeticao(parse_dt(l["quando"]), l["repetir"])
                        while prox and prox <= agora():
                            prox = textutil.proxima_repeticao(prox, l["repetir"])
                        if prox:
                            self.db.lembrete_novo(prox, l["texto"], l["origem"], l["repetir"])
                    self.n.alertar_lembrete(l)
            except Exception:
                log.exception("erro nos lembretes")

    # ------------------------------------------------------------------ pendências
    def loop_pendencias(self):
        while True:
            time.sleep(60)
            try:
                if self.n.olhos and self.n.cfg["olhos_ativos"]:
                    self._nao_salvos()
                    self._reaberturas()
                    self._resolver()
                self._bom_dia_se_preciso()
            except Exception:
                log.exception("erro nas pendências")

    def _nao_salvos(self):
        limite = agora() - dt.timedelta(minutes=45)
        ini = agora() - dt.timedelta(hours=20)
        ultimos = {}
        for r in self.db.sessoes_periodo(ini, agora()):
            if r["arquivo"]:
                ultimos[r["arquivo"]] = r
        foco = (self.n.olhos.foco or {}).get("arquivo")
        for arq, r in ultimos.items():
            if r["nao_salvo"] and parse_dt(r["fim"]) < limite and arq != foco:
                self.db.pendencia_abrir(f"nao_salvo:{arq}:{r['fim'][:10]}", "nao_salvo",
                                        f"{arq} ficou com alterações não salvas desde as {r['fim'][11:16]}.", arq)

    def _reaberturas(self):
        ini = agora() - dt.timedelta(hours=48)
        visitas = {}
        for b in self.n.olhos.blocos(ini, agora(), juntar_min=10):
            arq = b["arquivo"] or ""
            if arq.lower().endswith(DOCS):
                visitas.setdefault(arq, []).append(b)
        for arq, bl in visitas.items():
            if len(bl) >= 3 and any(x["nao_salvo"] for x in bl[-1:]):
                self.db.pendencia_abrir(f"reaberto:{arq}:{dt.date.today()}", "reaberto",
                                        f"{arq} foi aberto {len(bl)} vezes desde ontem e continua sem salvar.", arq)

    def _resolver(self):
        for p in self.db.pendencias_abertas():
            if p["tipo"] in ("nao_salvo", "reaberto") and p["arquivo"]:
                u = self.db.ultima_sessao_arquivo(p["arquivo"])
                if u and not u["nao_salvo"] and u["fim"] > p["criado"]:
                    self.db.pendencia_status(p["id"], "resolvida")

    # ------------------------------------------------------------------ bom dia
    def _bom_dia_se_preciso(self):
        hoje = str(dt.date.today())
        if not self.n.pronto or self.db.kv_get("bom_dia") == hoje:
            return
        if agora().hour < 5 or segundos_inativo() > 60:
            return
        self.db.kv_set("bom_dia", hoje)
        self.n.falar_aviso(self.bom_dia())

    def bom_dia(self):
        cfg = self.n.cfg
        h = agora().hour
        saud = "Bom dia" if h < 12 else ("Boa tarde" if h < 18 else "Boa noite")
        frases = [f"{saud}, {cfg['tratamento']}."]
        if self.n.olhos:
            ontem = dt.date.today() - dt.timedelta(days=1)
            top = [t for t in self.n.olhos.totais(ontem) if t[2] >= 600][:2]
            if top:
                a = top[0]
                t = cfg["tratamento"].strip().lower()
                sujeito = "o senhor" if t == "senhor" else ("a senhora" if t == "senhora" else "você")
                txt = f"Ontem {sujeito} trabalhou principalmente em {a[1]}, por cerca de {textutil.duracao_texto(a[2])}"
                if len(top) > 1:
                    txt += f", e também em {top[1][1]}"
                frases.append(txt + ".")
        lem = [l for l in self.db.lembretes_dia(dt.date.today()) if l["status"] == "pendente"]
        if lem:
            p = lem[0]
            q = parse_dt(p["quando"])
            if len(lem) == 1:
                frases.append(f"Hoje há um lembrete, às {q:%H:%M}: {p['texto']}.")
            else:
                frases.append(f"Hoje há {len(lem)} lembretes. O primeiro é às {q:%H:%M}: {p['texto']}.")
        else:
            frases.append("Não há lembretes para hoje.")
        pend = self.db.pendencias_abertas()
        if pend:
            frases.append(f"E uma pendência: {pend[0]['texto']}" if len(pend) == 1 else
                          f"Há {len(pend)} pendências; a principal: {pend[0]['texto']}")
        return " ".join(frases)
