"""Memória de longo prazo: fatos que aparecem nas conversas (pessoas, apelidos, onde ficam as coisas,
preferências), guardados no computador e lembrados quando têm a ver com a pergunta.
Também calcula hábitos a partir do registro de atividade."""
import re
import time
import difflib
import logging
import datetime as dt
from . import textutil
from .db import agora, s as fmt, d as parse_dt

log = logging.getLogger("memoria")

ESQUEMA = {"type": "object", "properties": {"fatos": {"type": "array", "items": {"type": "string"}, "maxItems": 4}},
           "required": ["fatos"]}

INSTRUCAO = """Você extrai FATOS DURADOUROS que o usuário contou sobre si, sua vida, seu trabalho, pessoas, apelidos,
lugares de arquivos, preferências e costumes. Escreva cada fato numa frase curta em terceira pessoa,
começando por "O usuário" ou pelo nome da coisa (ex.: "Leandrinho é ajudante do usuário na marcenaria.",
"A linha Brisa é de poltronas de balanço.", "O usuário prefere respostas detalhadas sobre SolidWorks.").
NÃO extraia: perguntas, pedidos de lembrete, coisas passageiras (horário de hoje, o que vai fazer agora),
nem nada que o usuário não tenha afirmado. Se não houver fato duradouro, devolva lista vazia.
Responda só JSON: {"fatos": [...]}"""


class Memoria:
    def __init__(self, nucleo):
        self.n = nucleo
        self.db = nucleo.db
        self.db.x("CREATE TABLE IF NOT EXISTS fatos(id INTEGER PRIMARY KEY, texto TEXT, criado TEXT, usos INTEGER DEFAULT 0, "
                  "ultimo TEXT)")
        self.db.x("CREATE TABLE IF NOT EXISTS habitos(chave TEXT PRIMARY KEY, texto TEXT, calculado TEXT)")

    # ------------------------------------------------------------------ fatos
    def todos(self):
        return self.db.q("SELECT * FROM fatos ORDER BY id")

    def adicionar(self, texto):
        texto = texto.strip().rstrip(".") + "."
        if len(texto) < 8 or len(texto) > 240:
            return False
        tn = textutil.sem_acento(texto.lower())
        for f in self.todos():
            if difflib.SequenceMatcher(None, tn, textutil.sem_acento(f["texto"].lower())).ratio() > 0.82:
                self.db.x("UPDATE fatos SET texto=?, ultimo=? WHERE id=?", (texto, fmt(agora()), f["id"]))
                return False
        self.db.x("INSERT INTO fatos(texto, criado, ultimo) VALUES(?,?,?)", (texto, fmt(agora()), fmt(agora())))
        log.info("novo fato: %s", texto)
        return True

    def esquecer(self, pedido):
        """Apaga os fatos mais parecidos com o pedido. Devolve os textos apagados."""
        alvo = textutil.sem_acento(pedido.lower())
        alvo = re.sub(r"\b(esquece|esqueca|esquecer|apaga|apague|tira|remove|da memoria|que|isso|sobre|o|a)\b", " ", alvo)
        termos = [t for t in alvo.split() if len(t) >= 3]
        if not termos:
            return []
        apagados = []
        for f in self.todos():
            tn = textutil.sem_acento(f["texto"].lower())
            if sum(1 for t in termos if t in tn) >= max(1, (len(termos) + 1) // 2):
                self.db.x("DELETE FROM fatos WHERE id=?", (f["id"],))
                apagados.append(f["texto"])
        return apagados

    def relevantes(self, pergunta, k=8):
        fatos = self.todos()
        if not fatos:
            return []
        termos = [t for t in re.findall(r"[a-z0-9]{3,}", textutil.sem_acento(pergunta.lower()))]
        pont = []
        for f in fatos:
            tn = textutil.sem_acento(f["texto"].lower())
            s = sum(1 for t in termos if t in tn)
            pont.append((s, f["usos"], f["id"], f))
        pont.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        escolhidos = [p[3] for p in pont if p[0] > 0][:k]
        # sempre alguns dos mais recentes (dão contexto geral)
        for f in sorted(fatos, key=lambda f: -f["id"])[:4]:
            if f not in escolhidos:
                escolhidos.append(f)
        for f in escolhidos:
            self.db.x("UPDATE fatos SET usos=usos+1 WHERE id=?", (f["id"],))
        return [f["texto"] for f in escolhidos[:k + 4]]

    def extrair(self, frase_usuario):
        """Roda em segundo plano depois da resposta: guarda fatos duradouros que o usuário contou."""
        f = frase_usuario.strip()
        if len(f.split()) < 4 or f.endswith("?"):
            return
        if not re.search(r"\b(e|é|sou|meu|minha|chama|fica|trabalha|gosto|prefiro|sempre|nunca|tenho|temos|nosso|nossa|"
                         r"significa|quer dizer|costumo|uso|usamos)\b", textutil.sem_acento(f.lower())):
            return
        try:
            r = self.n.ia.conversar([{"role": "system", "content": INSTRUCAO}, {"role": "user", "content": f}],
                                    ESQUEMA, max_tokens=200, temperatura=0.1)
            for fato in (r.get("fatos") or [])[:4]:
                if isinstance(fato, str):
                    self.adicionar(fato)
        except Exception:
            log.exception("extrair fatos")

    # ------------------------------------------------------------------ hábitos
    def habitos(self):
        hoje = str(dt.date.today())
        h = self.db.q("SELECT texto, calculado FROM habitos WHERE chave='geral'")
        if h and h[0]["calculado"] == hoje:
            return h[0]["texto"]
        texto = self._calcular_habitos()
        self.db.x("INSERT INTO habitos(chave,texto,calculado) VALUES('geral',?,?) ON CONFLICT(chave) DO UPDATE SET "
                  "texto=excluded.texto, calculado=excluded.calculado", (texto, hoje))
        return texto

    def _calcular_habitos(self):
        ini = agora() - dt.timedelta(days=21)
        sess = self.db.q("SELECT inicio, fim, app, arquivo FROM atividade WHERE inicio>=? AND app!='Privado'", (fmt(ini),))
        if len(sess) < 20:
            return ""
        primeiros, ultimos, apps, arqs = {}, {}, {}, {}
        for s in sess:
            a, b = parse_dt(s["inicio"]), parse_dt(s["fim"])
            dia = a.date()
            primeiros[dia] = min(primeiros.get(dia, a), a)
            ultimos[dia] = max(ultimos.get(dia, b), b)
            seg = (b - a).total_seconds()
            apps[s["app"]] = apps.get(s["app"], 0) + seg
            if s["arquivo"]:
                arqs[s["arquivo"]] = arqs.get(s["arquivo"], 0) + seg
        def media_hora(ds):
            mins = sorted(d.hour * 60 + d.minute for d in ds.values())
            m = mins[len(mins) // 2]
            return f"{m // 60}h{m % 60:02d}"
        top_apps = sorted(apps.items(), key=lambda x: -x[1])[:5]
        top_arqs = sorted(arqs.items(), key=lambda x: -x[1])[:6]
        partes = [f"Costuma começar a usar o computador por volta de {media_hora(primeiros)} e parar por volta de {media_hora(ultimos)}.",
                  "Programas mais usados nas últimas semanas: " + ", ".join(f"{a} ({textutil.duracao_texto(s)})" for a, s in top_apps) + "."]
        if top_arqs:
            partes.append("Arquivos em que mais trabalhou: " + ", ".join(a for a, _ in top_arqs) + ".")
        return " ".join(partes)
