"""Banco de dados local (SQLite): lembretes, atividade, notas, conversa, pendências."""
import sqlite3
import threading
import datetime as dt

FMT = "%Y-%m-%d %H:%M:%S"


def agora():
    return dt.datetime.now().replace(microsecond=0)


def s(d: dt.datetime) -> str:
    return d.strftime(FMT)


def d(txt: str) -> dt.datetime:
    return dt.datetime.strptime(txt, FMT)


ESQUEMA = """
CREATE TABLE IF NOT EXISTS lembretes(
  id INTEGER PRIMARY KEY, quando TEXT NOT NULL, texto TEXT NOT NULL, criado TEXT NOT NULL,
  origem TEXT DEFAULT 'voz', status TEXT DEFAULT 'pendente', repetir TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_lem ON lembretes(status, quando);
CREATE TABLE IF NOT EXISTS atividade(
  id INTEGER PRIMARY KEY, inicio TEXT NOT NULL, fim TEXT NOT NULL, processo TEXT, app TEXT,
  titulo TEXT, arquivo TEXT, nao_salvo INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_atv ON atividade(inicio);
CREATE TABLE IF NOT EXISTS notas(id INTEGER PRIMARY KEY, criado TEXT NOT NULL, texto TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversa(id INTEGER PRIMARY KEY, quando TEXT NOT NULL, papel TEXT NOT NULL, texto TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pendencias(
  id INTEGER PRIMARY KEY, criado TEXT NOT NULL, tipo TEXT, chave TEXT UNIQUE, texto TEXT,
  arquivo TEXT, status TEXT DEFAULT 'aberta', adiar_ate TEXT);
CREATE TABLE IF NOT EXISTS kv(chave TEXT PRIMARY KEY, valor TEXT);
"""


class Banco:
    def __init__(self, caminho):
        self.con = sqlite3.connect(str(caminho), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.executescript(ESQUEMA)
            self.con.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def x(self, sql, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur.lastrowid

    # ---------- kv ----------
    def kv_get(self, chave, padrao=None):
        r = self.q("SELECT valor FROM kv WHERE chave=?", (chave,))
        return r[0]["valor"] if r else padrao

    def kv_set(self, chave, valor):
        self.x("INSERT INTO kv(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
               (chave, str(valor)))

    # ---------- lembretes ----------
    def lembrete_novo(self, quando: dt.datetime, texto, origem="voz", repetir=""):
        return self.x("INSERT INTO lembretes(quando,texto,criado,origem,repetir) VALUES(?,?,?,?,?)",
                      (s(quando), texto, s(agora()), origem, repetir or ""))

    def lembretes_vencidos(self):
        return self.q("SELECT * FROM lembretes WHERE status='pendente' AND quando<=? ORDER BY quando", (s(agora()),))

    def lembretes_proximos(self, limite=12):
        return self.q("SELECT * FROM lembretes WHERE status='pendente' ORDER BY quando LIMIT ?", (limite,))

    def lembretes_dia(self, dia: dt.date):
        ini = dt.datetime.combine(dia, dt.time())
        fim = ini + dt.timedelta(days=1)
        return self.q("SELECT * FROM lembretes WHERE quando>=? AND quando<? AND status!='cancelado' ORDER BY quando",
                      (s(ini), s(fim)))

    def lembrete_status(self, id_, status):
        self.x("UPDATE lembretes SET status=? WHERE id=?", (status, id_))

    def lembrete_adiar(self, id_, minutos):
        self.x("UPDATE lembretes SET status='pendente', quando=? WHERE id=?",
               (s(agora() + dt.timedelta(minutes=minutos)), id_))

    def lembrete(self, id_):
        r = self.q("SELECT * FROM lembretes WHERE id=?", (id_,))
        return r[0] if r else None

    # ---------- atividade ----------
    def sessao_abrir(self, processo, app, titulo, arquivo, nao_salvo):
        t = s(agora())
        return self.x("INSERT INTO atividade(inicio,fim,processo,app,titulo,arquivo,nao_salvo) VALUES(?,?,?,?,?,?,?)",
                      (t, t, processo, app, titulo, arquivo, int(bool(nao_salvo))))

    def sessao_tocar(self, id_, nao_salvo):
        self.x("UPDATE atividade SET fim=?, nao_salvo=? WHERE id=?", (s(agora()), int(bool(nao_salvo)), id_))

    def sessoes_periodo(self, ini: dt.datetime, fim: dt.datetime):
        return self.q("SELECT * FROM atividade WHERE inicio<? AND fim>=? ORDER BY inicio", (s(fim), s(ini)))

    def sessoes_busca(self, termo, desde: dt.datetime, limite=40):
        like = f"%{termo}%"
        return self.q("SELECT * FROM atividade WHERE inicio>=? AND (titulo LIKE ? OR arquivo LIKE ? OR app LIKE ?) "
                      "ORDER BY inicio DESC LIMIT ?", (s(desde), like, like, like, limite))

    def ultima_sessao_arquivo(self, arquivo):
        r = self.q("SELECT * FROM atividade WHERE arquivo=? ORDER BY fim DESC LIMIT 1", (arquivo,))
        return r[0] if r else None

    # ---------- notas ----------
    def nota_nova(self, texto):
        return self.x("INSERT INTO notas(criado,texto) VALUES(?,?)", (s(agora()), texto))

    def notas(self, limite=10, termo=None):
        if termo:
            return self.q("SELECT * FROM notas WHERE texto LIKE ? ORDER BY id DESC LIMIT ?", (f"%{termo}%", limite))
        return self.q("SELECT * FROM notas ORDER BY id DESC LIMIT ?", (limite,))

    # ---------- conversa ----------
    def conversa_add(self, papel, texto):
        return self.x("INSERT INTO conversa(quando,papel,texto) VALUES(?,?,?)", (s(agora()), papel, texto))

    def conversa_ultimas(self, n=12):
        r = self.q("SELECT * FROM conversa ORDER BY id DESC LIMIT ?", (n,))
        return list(reversed(r))

    # ---------- pendências ----------
    def pendencia_abrir(self, chave, tipo, texto, arquivo=None):
        if self.q("SELECT id FROM pendencias WHERE chave=?", (chave,)):
            return None
        return self.x("INSERT INTO pendencias(criado,tipo,chave,texto,arquivo) VALUES(?,?,?,?,?)",
                      (s(agora()), tipo, chave, texto, arquivo))

    def pendencias_abertas(self):
        return self.q("SELECT * FROM pendencias WHERE status='aberta' OR (status='adiada' AND adiar_ate<=?) "
                      "ORDER BY id DESC", (s(agora()),))

    def pendencia_status(self, id_, status, adiar_min=None):
        if adiar_min:
            self.x("UPDATE pendencias SET status='adiada', adiar_ate=? WHERE id=?",
                   (s(agora() + dt.timedelta(minutes=adiar_min)), id_))
        else:
            self.x("UPDATE pendencias SET status=? WHERE id=?", (status, id_))

    def pendencia(self, id_):
        r = self.q("SELECT * FROM pendencias WHERE id=?", (id_,))
        return r[0] if r else None
