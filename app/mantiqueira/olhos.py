"""Olhos: registra qual programa e arquivo está em uso, monta a linha do tempo e acha arquivos recentes."""
import os
import re
import time
import ctypes
import ctypes.wintypes as wt
import difflib
import threading
import logging
import datetime as dt
import psutil
from . import textutil, sistema
from .db import agora, d as parse_dt, s as fmt_dt

log = logging.getLogger("olhos")

INATIVO_SEG = 300        # 5 min sem mexer = pausa
INTERVALO = 2.0


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


def segundos_inativo():
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0
        return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 0


def janela_ativa():
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    n = u.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, buf, n + 1)
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proc = psutil.Process(pid.value).name()
    except Exception:
        proc = "?"
    return pid.value, proc, buf.value


class Olhos:
    def __init__(self, nucleo):
        self.n = nucleo
        self.db = nucleo.db
        self.sessao = None          # dict com id, processo, titulo, arquivo, app, nao_salvo
        self.foco = None            # o que está em uso agora (para a tela)
        self.inativo = False
        self.recentes = ArquivosRecentes()

    def iniciar(self):
        threading.Thread(target=self._loop, daemon=True, name="olhos").start()
        threading.Thread(target=self.recentes.loop, daemon=True, name="recentes").start()

    def _privado(self, proc, titulo):
        t = (titulo + " " + proc).lower()
        return any(p.strip().lower() in t for p in self.n.cfg["ignorar"] if p.strip())

    def _fechar(self):
        self.sessao = None

    def _loop(self):
        meu_pid = os.getpid()
        while True:
            time.sleep(INTERVALO)
            try:
                if not self.n.cfg["olhos_ativos"]:
                    self._fechar(); self.foco = None
                    continue
                if segundos_inativo() > INATIVO_SEG:
                    self.inativo = True
                    self._fechar()
                    continue
                self.inativo = False
                j = janela_ativa()
                if not j:
                    continue
                pid, proc, titulo = j
                if pid == meu_pid or not titulo.strip():
                    continue
                if self._privado(proc, titulo):
                    app, titulo, arquivo, nao_salvo = "Privado", "", "", False
                else:
                    app = textutil.nome_app(proc)
                    arquivo, nao_salvo = textutil.extrair_arquivo(proc, titulo)
                self.foco = {"app": app, "arquivo": arquivo or "", "titulo": titulo, "nao_salvo": nao_salvo,
                             "processo": proc}
                s = self.sessao
                if s and s["processo"] == proc and s["titulo"] == titulo:
                    self.db.sessao_tocar(s["id"], nao_salvo)
                elif s and s["processo"] == proc and arquivo and s["arquivo"] == arquivo:
                    # mesmo arquivo, título mudou (ex.: apareceu o * de não salvo)
                    s["titulo"] = titulo
                    self.db.sessao_tocar(s["id"], nao_salvo)
                else:
                    sid = self.db.sessao_abrir(proc, app, titulo, arquivo, nao_salvo)
                    self.sessao = {"id": sid, "processo": proc, "titulo": titulo, "arquivo": arquivo, "app": app}
            except Exception:
                log.exception("erro nos olhos")

    # ------------------------------------------------------------------ resumos
    def blocos(self, ini: dt.datetime, fim: dt.datetime, juntar_min=5):
        """Junta sessões seguidas do mesmo arquivo/programa em blocos de trabalho."""
        out = []
        for r in self.db.sessoes_periodo(ini, fim):
            if r["app"] == "Privado":
                nome = "(programa privado)"
            else:
                nome = r["arquivo"] or textutil.curto(r["titulo"], 60)
            a, b = parse_dt(r["inicio"]), parse_dt(r["fim"])
            if out and out[-1]["nome"] == nome and out[-1]["app"] == r["app"] and \
                    (a - out[-1]["fim"]).total_seconds() <= juntar_min * 60:
                out[-1]["fim"] = max(out[-1]["fim"], b)
                out[-1]["seg"] += (b - a).total_seconds()
                out[-1]["nao_salvo"] = r["nao_salvo"]
            else:
                out.append({"app": r["app"], "nome": nome, "arquivo": r["arquivo"], "inicio": a, "fim": b,
                            "seg": (b - a).total_seconds(), "nao_salvo": r["nao_salvo"]})
        return out

    def totais(self, dia: dt.date):
        ini = dt.datetime.combine(dia, dt.time())
        tot = {}
        for b in self.blocos(ini, ini + dt.timedelta(days=1)):
            if b["app"] == "Privado":
                continue
            chave = (b["app"], b["nome"])
            tot[chave] = tot.get(chave, 0) + b["seg"]
        return sorted(((app, nome, seg) for (app, nome), seg in tot.items()), key=lambda x: -x[2])

    def texto_dia(self, dia: dt.date, maximo=25):
        ini = dt.datetime.combine(dia, dt.time())
        linhas = []
        for b in self.blocos(ini, ini + dt.timedelta(days=1)):
            if b["seg"] < 60:
                continue
            ns = " [não salvo]" if b["nao_salvo"] else ""
            linhas.append(f"{b['inicio']:%H:%M}–{b['fim']:%H:%M} {b['app']} · {b['nome']}"
                          f" ({textutil.duracao_texto(b['seg'])}){ns}")
        if len(linhas) > maximo:
            linhas = linhas[:5] + ["…"] + linhas[-(maximo - 6):]
        return linhas

    def buscar(self, termos, dias=30):
        desde = agora() - dt.timedelta(days=dias)
        achados = {}
        for t in termos:
            for r in self.db.sessoes_busca(t, desde):
                if r["app"] == "Privado":
                    continue
                dia = r["inicio"][:10]
                nome = r["arquivo"] or textutil.curto(r["titulo"], 60)
                k = (dia, r["app"], nome)
                a, b = parse_dt(r["inicio"]), parse_dt(r["fim"])
                if k not in achados:
                    achados[k] = [a, b, 0.0]
                achados[k][0] = min(achados[k][0], a)
                achados[k][1] = max(achados[k][1], b)
                achados[k][2] += (b - a).total_seconds()
        linhas = []
        for (dia, app, nome), (a, b, seg) in sorted(achados.items(), reverse=True)[:20]:
            if seg < 30:
                continue
            linhas.append(f"{a:%d/%m} ({textutil.DIAS_SEMANA[a.weekday()]}) {a:%H:%M}–{b:%H:%M} {app} · {nome}"
                          f" ({textutil.duracao_texto(seg)})")
        return linhas

    def registro_recente(self, n=4):
        ini = dt.datetime.combine(dt.date.today(), dt.time())
        bl = [b for b in self.blocos(ini, agora() + dt.timedelta(minutes=1)) if b["seg"] >= 20]
        return [{"hora": f"{b['inicio']:%H:%M}", "app": b["app"], "nome": b["nome"]} for b in bl[-n:]][::-1]

    def tempo_hoje(self, app, nome):
        for a, nm, seg in self.totais(dt.date.today()):
            if a == app and nm == nome:
                return seg
        return 0


class ArquivosRecentes:
    """Índice nome→caminho dos arquivos usados recentemente (SolidWorks, Office e Windows)."""

    def __init__(self):
        self.indice = {}
        self.lock = threading.Lock()

    def loop(self):
        while True:
            try:
                self.atualizar()
            except Exception:
                log.exception("falha ao indexar recentes")
            time.sleep(600)

    def atualizar(self):
        caminhos = set()
        caminhos.update(self._registro_solidworks())
        caminhos.update(self._registro_office())
        caminhos.update(self._recentes_windows())
        novo = {}
        for c in caminhos:
            c = c.strip().strip('"')
            if c and os.path.exists(c):
                novo.setdefault(os.path.basename(c).lower(), c)
        with self.lock:
            self.indice.update(novo)
        log.info("arquivos recentes indexados: %d", len(self.indice))

    def _registro_solidworks(self):
        import winreg
        out = []
        try:
            raiz = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SolidWorks")
        except OSError:
            return out
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(raiz, i)
            except OSError:
                break
            i += 1
            if not sub.upper().startswith("SOLIDWORKS 20"):
                continue
            try:
                k = winreg.OpenKey(raiz, sub + r"\Recent File List")
            except OSError:
                continue
            j = 0
            while True:
                try:
                    _, valor, _ = winreg.EnumValue(k, j)
                except OSError:
                    break
                j += 1
                if isinstance(valor, str):
                    out.append(valor)
        return out

    def _registro_office(self):
        import winreg
        out = []
        for app in ("Excel", "Word", "PowerPoint"):
            base = rf"Software\Microsoft\Office\16.0\{app}\User MRU"
            try:
                k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    fm = winreg.OpenKey(k, sub + r"\File MRU")
                except OSError:
                    continue
                j = 0
                while True:
                    try:
                        _, valor, _ = winreg.EnumValue(fm, j)
                    except OSError:
                        break
                    j += 1
                    if isinstance(valor, str) and "*" in valor:
                        out.append(valor.split("*", 1)[1])
        return out

    def _recentes_windows(self):
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                  "$sh=New-Object -ComObject WScript.Shell;"
                  "Get-ChildItem \"$env:APPDATA\\Microsoft\\Windows\\Recent\" -Filter *.lnk | "
                  "Sort-Object LastWriteTime -Descending | Select-Object -First 400 | "
                  "ForEach-Object { try { $t=$sh.CreateShortcut($_.FullName).TargetPath; if($t){$t} } catch {} }")
        return [l for l in sistema.powershell(script, timeout=60).splitlines() if l.strip()]

    def achar(self, nome: str):
        if not nome:
            return None
        alvo = nome.strip().strip('"').lower()
        with self.lock:
            idx = dict(self.indice)
        if alvo in idx:
            return idx[alvo]
        alvo_stem = os.path.splitext(alvo)[0].replace("_", " ")
        stems = {os.path.splitext(k)[0].replace("_", " "): v for k, v in idx.items()}
        if alvo_stem in stems:
            return stems[alvo_stem]
        for k, v in stems.items():
            if alvo_stem and alvo_stem in k:
                return v
        perto = difflib.get_close_matches(alvo_stem, list(stems.keys()), n=1, cutoff=0.6)
        return stems[perto[0]] if perto else None

    def lembrar(self, caminho):
        with self.lock:
            self.indice[os.path.basename(caminho).lower()] = caminho
