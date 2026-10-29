"""Índice de arquivos: nomes e caminhos de tudo que há no computador, no pendrive e nas pastas de rede.
Guarda só o NOME e o CAMINHO (não o conteúdo). Varre em segundo plano, devagar, para não pesar o PC.
A busca aceita nomes escritos errado e sugere os parecidos."""
import os
import re
import time
import string
import ctypes
import difflib
import sqlite3
import logging
import threading
from pathlib import Path
from . import paths, textutil

log = logging.getLogger("indice")

DRIVE_REMOVIVEL, DRIVE_FIXO, DRIVE_REDE = 2, 3, 4
IGNORAR_PASTAS = {
    "windows", "$recycle.bin", "system volume information", "$windows.~bt", "$windows.~ws", "recovery",
    "msocache", "config.msi", "$sysreset", "perflogs", "winsxs", "node_modules", "__pycache__", ".git",
    ".svn", ".cache", "temp", "tmp", "inetcache", "webcache", "crashdumps", "cache", "code cache",
    "gpucache", "shadercache", "dxcache", "packages", "installer", "softwaredistribution", "assembly",
}
IGNORAR_CAMINHOS = (r"\appdata\local\microsoft", r"\appdata\local\temp", r"\appdata\locallow",
                    r"\appdata\local\packages", r"\appdata\local\google\chrome\user data",
                    r"\appdata\local\microsoft\edge", r"\appdata\roaming\microsoft\windows\recent",
                    r"\programdata\microsoft", r"\programdata\package cache")
ORIGEM_NOME = {"pc": "no computador", "pendrive": "no pendrive", "rede": "na rede"}
NOMES = {}                 # 'Z:\\' → 'File-Projetos' (nome curto da pasta de rede / rótulo do disco)


def apelido(raiz):
    """Nome curto da unidade para falar e para reconhecer ('File-Projetos', 'File_Aluminas')."""
    if raiz in NOMES:
        return NOMES[raiz]
    bruto = nome_unidade(raiz)
    nome = ""
    m = re.search(r"\\\\[^\\]+\\(.+)$", bruto.strip())          # \\servidor\pasta → pasta
    if m:
        nome = m.group(1)
    elif bruto.strip():
        nome = bruto.split()[0]
    NOMES[raiz] = nome
    return nome
INTERVALO_PC = 6 * 3600
INTERVALO_REDE = 12 * 3600


def norm(t):
    t = textutil.sem_acento((t or "").lower())
    t = re.sub(r"[_\-\.\(\)\[\]]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def nome_unidade(raiz):
    """Nome que o Windows mostra para a unidade: rótulo do disco e, na rede, o nome da pasta compartilhada
    (ex.: Z:\\ → 'File-Projetos \\\\192.168.1.6\\File-Projetos')."""
    partes = []
    try:
        buf = ctypes.create_unicode_buffer(261)
        if ctypes.windll.kernel32.GetVolumeInformationW(raiz, buf, 261, None, None, None, None, 0):
            partes.append(buf.value)
    except Exception:
        pass
    try:
        buf = ctypes.create_unicode_buffer(1024)
        tam = ctypes.c_ulong(1024)
        if ctypes.windll.mpr.WNetGetConnectionW(raiz[:2], buf, ctypes.byref(tam)) == 0:
            partes.append(buf.value)
    except Exception:
        pass
    return " ".join(partes)


def unidades():
    """[(letra 'C:\\', tipo, origem)] de todas as unidades conectadas."""
    out = []
    try:
        mascara = ctypes.windll.kernel32.GetLogicalDrives()
    except Exception:
        return out
    for i, letra in enumerate(string.ascii_uppercase):
        if not mascara & (1 << i):
            continue
        raiz = f"{letra}:\\"
        tipo = ctypes.windll.kernel32.GetDriveTypeW(raiz)
        if tipo == DRIVE_REDE:
            out.append((raiz, tipo, "rede"))
        elif tipo == DRIVE_REMOVIVEL:
            out.append((raiz, tipo, "pendrive"))
        elif tipo == DRIVE_FIXO:
            out.append((raiz, tipo, "pc" if letra == "C" else "pendrive"))
    return out


class Indice:
    def __init__(self, nucleo=None):
        self.n = nucleo
        self.con = sqlite3.connect(str(paths.DADOS / "indice.db"), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.status = {}          # raiz → texto
        self.varrendo = None
        self._ja = threading.Event()
        with self.lock:
            self.con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS arq(id INTEGER PRIMARY KEY, caminho TEXT UNIQUE, nome TEXT, nn TEXT, pasta TEXT,
              ext TEXT, eh_pasta INTEGER, tam INTEGER, mod REAL, origem TEXT, raiz TEXT, visto REAL);
            CREATE INDEX IF NOT EXISTS ix_arq_raiz ON arq(raiz, visto);
            CREATE TABLE IF NOT EXISTS varreduras(raiz TEXT PRIMARY KEY, fim REAL, total INTEGER);
            CREATE TABLE IF NOT EXISTS preferidos(consulta TEXT, caminho TEXT, vezes INTEGER, ultimo REAL,
              PRIMARY KEY(consulta, caminho));
            """)
            try:
                self.con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS arq_fts USING fts5(nn, content='arq', "
                                 "content_rowid='id', tokenize='trigram')")
                self.fts = True
            except sqlite3.OperationalError:
                self.fts = False
            self.con.commit()

    # ------------------------------------------------------------------ varredura
    def iniciar(self):
        threading.Thread(target=self._loop, daemon=True, name="indice").start()

    def locais(self):
        """[(raiz, origem, apelido)] das unidades conectadas agora."""
        out = []
        for raiz, _, origem in unidades():
            try:
                out.append((raiz, origem, apelido(raiz)))
            except Exception:
                out.append((raiz, origem, ""))
        return out

    def avisos(self):
        """Avisos para o painel (guardados por 1 minuto)."""
        c = getattr(self, "_avisos_cache", None)
        if c and time.time() - c[0] < 60:
            return c[1]
        out = []
        try:
            for raiz, origem, apel in self.locais():
                if origem != "rede" or raiz == self.varrendo:
                    continue
                v = self.q("SELECT fim FROM varreduras WHERE raiz=?", (raiz,))
                if not v or time.time() - (v[0]["fim"] or 0) > 26 * 3600:
                    out.append(f"Mapa da rede {raiz[:2]} {apel} desatualizado: CONHECIMENTO > ATUALIZAR AGORA.".replace("  ", " "))
        except Exception:
            pass
        self._avisos_cache = (time.time(), out)
        return out

    def atualizar_agora(self):
        """Pedido da tela: refaz o mapa de tudo no próximo ciclo (sem esperar as 6/12 horas)."""
        with self.lock:
            self.con.execute("UPDATE varreduras SET fim=0")
            self.con.commit()
        self._ja.set()

    def _loop(self):
        self._ja.wait(40)                    # deixa o resto do programa carregar primeiro
        while True:
            self._ja.clear()
            try:
                for raiz, _, origem in unidades():
                    ult = self.q("SELECT fim FROM varreduras WHERE raiz=?", (raiz,))
                    idade = time.time() - (ult[0]["fim"] if ult else 0)
                    if idade < (INTERVALO_REDE if origem == "rede" else INTERVALO_PC):
                        continue
                    if not os.path.exists(raiz):
                        continue
                    self.varrer(raiz, origem)
            except Exception:
                log.exception("varredura")
            self._ja.wait(300)

    def varrer(self, raiz, origem):
        self.varrendo = raiz
        inicio = time.time()
        total, lote = 0, []
        log.info("varrendo %s (%s)", raiz, origem)
        pilha = [raiz]
        while pilha:
            pasta = pilha.pop()
            pl = pasta.lower()
            if any(c in pl for c in IGNORAR_CAMINHOS):
                continue
            try:
                with os.scandir(pasta) as it:
                    for e in it:
                        try:
                            nome = e.name
                            if e.is_dir(follow_symlinks=False):
                                if nome.lower() in IGNORAR_PASTAS or nome.startswith("$") or nome.startswith("~$"):
                                    continue
                                if pasta == raiz and nome.lower() in ("windows",):
                                    continue
                                pilha.append(e.path)
                                lote.append((e.path, nome, norm(nome), pasta, "", 1, 0, 0, origem, raiz, inicio))
                            else:
                                if nome.startswith("~$") or nome.lower().endswith((".tmp", ".lnk", ".ini", ".dat")):
                                    continue
                                st = e.stat(follow_symlinks=False)
                                ext = os.path.splitext(nome)[1].lower()
                                lote.append((e.path, nome, norm(os.path.splitext(nome)[0]) + " " + ext.strip("."),
                                             pasta, ext, 0, st.st_size, st.st_mtime, origem, raiz, inicio))
                        except OSError:
                            continue
            except OSError:
                continue
            if len(lote) >= 2000:
                self._gravar(lote)
                total += len(lote)
                lote = []
                self.status[raiz] = f"{total:,} itens".replace(",", ".")
                time.sleep(0.05 if origem != "rede" else 0.15)    # não pesar o disco/rede
        if lote:
            self._gravar(lote)
            total += len(lote)
        with self.lock:
            # remove o que sumiu desde a varredura anterior
            velhos = [r[0] for r in self.con.execute("SELECT id FROM arq WHERE raiz=? AND visto<?", (raiz, inicio))]
            for i in range(0, len(velhos), 900):
                ids = velhos[i:i + 900]
                if self.fts:
                    for rid in ids:
                        row = self.con.execute("SELECT nn FROM arq WHERE id=?", (rid,)).fetchone()
                        if row:
                            self.con.execute("INSERT INTO arq_fts(arq_fts, rowid, nn) VALUES('delete', ?, ?)", (rid, row[0]))
                self.con.execute(f"DELETE FROM arq WHERE id IN ({','.join('?' * len(ids))})", ids)
            self.con.execute("INSERT INTO varreduras(raiz,fim,total) VALUES(?,?,?) ON CONFLICT(raiz) DO UPDATE SET "
                             "fim=excluded.fim, total=excluded.total", (raiz, time.time(), total))
            self.con.commit()
        self.status[raiz] = f"{total:,} itens".replace(",", ".")
        self.varrendo = None
        log.info("varredura de %s concluída: %d itens em %.0fs", raiz, total, time.time() - inicio)

    def _gravar(self, lote):
        with self.lock:
            for r in lote:
                cur = self.con.execute("SELECT id, nn FROM arq WHERE caminho=?", (r[0],)).fetchone()
                if cur:
                    self.con.execute("UPDATE arq SET tam=?, mod=?, visto=? WHERE id=?", (r[6], r[7], r[10], cur[0]))
                else:
                    c = self.con.execute("INSERT INTO arq(caminho,nome,nn,pasta,ext,eh_pasta,tam,mod,origem,raiz,visto) "
                                         "VALUES(?,?,?,?,?,?,?,?,?,?,?)", r)
                    if self.fts:
                        self.con.execute("INSERT INTO arq_fts(rowid, nn) VALUES(?,?)", (c.lastrowid, r[2]))
            self.con.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def resumo(self):
        linhas = []
        for v in self.q("SELECT raiz, fim, total FROM varreduras ORDER BY raiz"):
            linhas.append(f"{v['raiz']} {v['total']} itens (atualizado {time.strftime('%d/%m %H:%M', time.localtime(v['fim']))})")
        if self.varrendo:
            linhas.append(f"varrendo agora {self.varrendo}: {self.status.get(self.varrendo, '')}")
        return linhas

    # ------------------------------------------------------------------ busca
    def buscar(self, consulta, onde="tudo", limite=8, exts=None):
        """Devolve (exatos, parecidos): listas de dicts com nome, caminho, pasta, origem, eh_pasta, mod.
        onde: 'tudo' | 'pc' (só C:) | 'rede' | 'pendrive' | uma unidade como 'Z:\\'. exts: só essas extensões."""
        cn = norm(consulta)
        termos = [t for t in cn.split() if len(t) >= 2]
        if not termos:
            return [], []
        filtro, args_f = "", []
        if onde == "pc":
            filtro, args_f = " AND a.raiz=?", ["C:\\"]
        elif onde in ("rede", "pendrive"):
            filtro, args_f = " AND a.origem=?", [onde]
        elif re.fullmatch(r"[A-Za-z]:\\", onde or ""):
            filtro, args_f = " AND a.raiz=?", [onde.upper()]
        if exts:
            filtro += " AND a.ext IN (" + ",".join("?" for _ in exts) + ")"
            args_f += list(exts)
        # 1) todos os termos aparecem no nome
        where = " AND ".join("a.nn LIKE ?" for _ in termos)
        exatos = self.q(f"SELECT a.* FROM arq a WHERE {where}{filtro} LIMIT 400",
                        [f"%{t}%" for t in termos] + args_f)
        # 2) parecidos (erros de digitação): trigramas em comum, depois similaridade
        candidatos = []
        if self.fts:
            tris = set()
            for t in termos:
                for i in range(max(1, len(t) - 2)):
                    tri = t[i:i + 3]
                    if len(tri) == 3:
                        tris.add(tri)
            if tris:
                expr = " OR ".join('"' + x.replace('"', '') + '"' for x in list(tris)[:24])
                try:
                    candidatos = self.q(f"SELECT a.* FROM arq_fts f JOIN arq a ON a.id=f.rowid WHERE arq_fts MATCH ?{filtro} "
                                        "LIMIT 3000", [expr] + args_f)
                except sqlite3.OperationalError:
                    candidatos = []
        else:
            candidatos = self.q(f"SELECT a.* FROM arq a WHERE ({' OR '.join('a.nn LIKE ?' for _ in termos)}){filtro} LIMIT 3000",
                                [f"%{t[:4]}%" for t in termos] + args_f)
        pref = {r["caminho"]: r["vezes"] for r in self.q("SELECT caminho, vezes FROM preferidos WHERE consulta=?", (cn,))}

        def nota(r, exato):
            nome = r["nn"]
            s = difflib.SequenceMatcher(None, cn, nome).ratio()
            s += sum(0.15 for t in termos if t in nome)
            s += 0.4 * min(3, pref.get(r["caminho"], 0))
            s += 0.05 if not r["eh_pasta"] else 0.02
            if r["ext"] in (".sldprt", ".sldasm", ".slddrw", ".dxf", ".dwg", ".xlsx", ".xls", ".pdf", ".docx", ".skp", ".max", ".crv", ".crv3d"):
                s += 0.08
            if "\\program files" in r["caminho"].lower() or "\\appdata\\" in r["caminho"].lower():
                s -= 0.3
            idade_dias = (time.time() - (r["mod"] or 0)) / 86400
            s += 0.1 if idade_dias < 30 else 0
            return s + (1.0 if exato else 0)

        vistos = set()
        ex = sorted(exatos, key=lambda r: -nota(r, True))
        for r in ex:
            vistos.add(r["caminho"])
        par = []
        for r in candidatos:
            if r["caminho"] in vistos:
                continue
            palavras_nome = set(r["nn"].split())
            parecida = sum(1 for t in termos if difflib.get_close_matches(t, palavras_nome, n=1, cutoff=0.72))
            if parecida >= max(1, (len(termos) + 1) // 2):
                par.append(r)
        par = sorted(par, key=lambda r: -nota(r, False))
        return ex[:limite], par[:limite]

    def lembrar_escolha(self, consulta, caminho):
        with self.lock:
            self.con.execute("INSERT INTO preferidos(consulta,caminho,vezes,ultimo) VALUES(?,?,1,?) ON CONFLICT(consulta,caminho) "
                             "DO UPDATE SET vezes=vezes+1, ultimo=excluded.ultimo", (norm(consulta), caminho, time.time()))
            self.con.commit()

    def achar(self, nome):
        """Melhor caminho para um nome de arquivo (usado para abrir arquivos citados). Respeita a extensão."""
        base, ext = os.path.splitext(nome)
        ex, par = self.buscar(base, limite=1, exts=[ext.lower()] if ext else None)
        r = (ex or par or [None])[0]
        return r["caminho"] if r else None


def descrever(r):
    """Texto curto para falar: nome + pasta resumida + onde."""
    pasta = r["pasta"]
    partes = [p for p in re.split(r"[\\/]", pasta) if p]
    curta = "\\".join(partes[-2:]) if len(partes) > 2 else pasta
    onde = ORIGEM_NOME.get(r["origem"], "")
    if r["origem"] == "rede" and NOMES.get(r.get("raiz") or ""):
        onde = f"na rede, no {NOMES[r['raiz']].replace('_', ' ').replace('-', ' ')}"
    return f"{r['nome']}, na pasta {curta} {onde}".strip()
