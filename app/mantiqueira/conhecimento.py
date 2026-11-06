"""Base de conhecimento: guias embutidos + documentos do usuário (PDF, TXT, MD, DOCX).
O texto é dividido em trechos e indexado (busca de texto completo, sem acento). Antes de responder,
o cérebro procura os trechos mais parecidos com a pergunta e entrega para a IA."""
import hashlib
import re
import sqlite3
import threading
import logging
from pathlib import Path
from . import paths, textutil
from .db import agora, s as fmt

log = logging.getLogger("conhecimento")
GUIAS = paths.APP / "conhecimento"
DOCS = paths.DADOS / "documentos"
DOCS.mkdir(parents=True, exist_ok=True)
TIPOS = (".pdf", ".txt", ".md", ".docx")

VAZIAS = set(textutil.sem_acento(w) for w in """a o as os um uma uns umas de do da dos das no na nos nas em por para pra pro
com sem que qual quais quando onde como eu me mim meu minha voce ele ela isso esse essa este esta aquele ser estar
fazer faz faco fiz tem ter ha e ou se nao sim mais muito pouco tudo nada algum alguma senhor doutor mantiqueira
favor pode poderia queria quero sobre ainda ja la aqui ai entao tambem so agora hoje porque pois vou vai
comando comandos atalho atalhos programa usar uso ferramenta""".split())

PROGRAMAS = {
    "solidworks": "SolidWorks", "solid": "SolidWorks", "sw": "SolidWorks",
    "autocad": "AutoCAD", "cad": "AutoCAD", "acad": "AutoCAD",
    "sketchup": "SketchUp", "sketch": "SketchUp",
    "3ds": "3ds Max", "max": "3ds Max", "3dsmax": "3ds Max",
    "aspire": "Aspire", "vectric": "Aspire",
    "cypcut": "CypCut", "laser": "CypCut",
    "excel": "Excel", "planilha": "Excel", "word": "Word", "powerpoint": "PowerPoint", "outlook": "Outlook",
}


def termos(pergunta):
    ws = re.findall(r"[0-9a-z]+", textutil.sem_acento(pergunta.lower()))
    out = []
    for w in ws:
        if len(w) >= 2 and w not in VAZIAS and w not in out:
            out.append(w)
    return out[:12]


class Conhecimento:
    def __init__(self):
        self.con = sqlite3.connect(str(paths.DADOS / "conhecimento.db"), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.status = ""
        self._ocr = None
        with self.lock:
            self.con.executescript("""
            CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, nome TEXT, origem TEXT, caminho TEXT,
              hash TEXT, paginas INTEGER, trechos INTEGER, criado TEXT);
            CREATE TABLE IF NOT EXISTS trechos_txt(id INTEGER PRIMARY KEY, doc_id INTEGER, titulo TEXT, texto TEXT);
            CREATE TABLE IF NOT EXISTS paginas(doc_id INTEGER, num INTEGER, texto TEXT, PRIMARY KEY(doc_id, num));
            """)
            try:
                self.con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(titulo, texto, doc_id UNINDEXED, "
                                 "tokenize='unicode61 remove_diacritics 2')")
                self.fts = True
            except sqlite3.OperationalError:
                log.warning("FTS5 indisponível; usando busca simples")
                self.fts = False
            self.con.commit()

    # ------------------------------------------------------------------ indexação
    def _apagar_doc(self, doc_id):
        with self.lock:
            if self.fts:
                self.con.execute("DELETE FROM busca WHERE doc_id=?", (doc_id,))
            self.con.execute("DELETE FROM trechos_txt WHERE doc_id=?", (doc_id,))
            self.con.execute("DELETE FROM paginas WHERE doc_id=?", (doc_id,))
            self.con.execute("DELETE FROM docs WHERE id=?", (doc_id,))
            self.con.commit()

    def _gravar(self, nome, origem, caminho, h, paginas, trechos, textos_pag=None, doc_id=None):
        with self.lock:
            if doc_id is None:
                cur = self.con.execute("INSERT INTO docs(nome,origem,caminho,hash,paginas,trechos,criado) VALUES(?,?,?,?,?,?,?)",
                                       (nome, origem, str(caminho), h, paginas, len(trechos), fmt(agora())))
                did = cur.lastrowid
            else:
                did = doc_id
                self.con.execute("UPDATE docs SET paginas=?, trechos=? WHERE id=?", (paginas, len(trechos), did))
            for num, texto in textos_pag or []:
                self.con.execute("INSERT OR REPLACE INTO paginas(doc_id,num,texto) VALUES(?,?,?)", (did, num, texto))
            self._cache_secoes = None
            for titulo, texto in trechos:
                self.con.execute("INSERT INTO trechos_txt(doc_id,titulo,texto) VALUES(?,?,?)", (did, titulo, texto))
                if self.fts:
                    self.con.execute("INSERT INTO busca(titulo,texto,doc_id) VALUES(?,?,?)", (titulo, texto, did))
            self.con.commit()
        return did

    def importar_guias(self):
        """Indexa os guias que vêm com o programa (reindexa se o arquivo mudou)."""
        if not GUIAS.exists():
            return
        for f in sorted(GUIAS.glob("*.md")):
            h = hashlib.sha1(f.read_bytes()).hexdigest()
            atual = self.q("SELECT id, hash FROM docs WHERE origem='guia' AND nome=?", (f.stem,))
            if atual and atual[0]["hash"] == h:
                continue
            for a in atual:
                self._apagar_doc(a["id"])
            trechos = dividir_markdown(f.read_text(encoding="utf-8"))
            self._gravar(f.stem, "guia", f, h, 0, trechos)
            log.info("guia indexado: %s (%d trechos)", f.stem, len(trechos))

    def adicionar(self, caminho):
        """Lê um arquivo do usuário, guarda uma cópia e indexa. Devolve (nome, paginas, trechos)."""
        origem = Path(caminho)
        if origem.suffix.lower() not in TIPOS:
            raise ValueError(f"Tipo de arquivo não suportado: {origem.suffix}")
        dados = origem.read_bytes()
        h = hashlib.sha1(dados).hexdigest()
        if self.q("SELECT id FROM docs WHERE hash=?", (h,)):
            return origem.name, 0, -1     # já estava na base
        copia = DOCS / origem.name
        n = 2
        while copia.exists():
            copia = DOCS / f"{origem.stem} ({n}){origem.suffix}"
            n += 1
        copia.write_bytes(dados)
        ext = origem.suffix.lower()
        paginas = []
        if ext == ".pdf":
            paginas = self._ler_pdf(copia)
            trechos = trechos_das_paginas(paginas)
            npag = len(paginas)
        elif ext == ".docx":
            txt = ler_docx(copia)
            trechos = [(f"parte {i + 1}", p) for i, p in enumerate(dividir_texto(txt))]
            npag = 0
        elif ext == ".md":
            trechos = dividir_markdown(copia.read_text(encoding="utf-8", errors="replace"))
            npag = 0
        else:
            txt = copia.read_text(encoding="utf-8", errors="replace")
            trechos = [(f"parte {i + 1}", p) for i, p in enumerate(dividir_texto(txt))]
            npag = 0
        if not trechos:
            copia.unlink(missing_ok=True)
            raise ValueError("Não encontrei texto nesse arquivo.")
        self._gravar(origem.name, "usuario", copia, h, npag, trechos, paginas)
        return origem.name, npag, len(trechos)

    def reler_antigos(self):
        """PDFs adicionados antes da versão 1.4.23: lê de novo (sem o cabeçalho repetido e guardando as páginas)."""
        for d in self.q("SELECT id, nome, caminho FROM docs WHERE origem='usuario' AND lower(caminho) LIKE '%.pdf' AND "
                        "id NOT IN (SELECT DISTINCT doc_id FROM paginas)"):
            try:
                caminho = Path(d["caminho"])
                if not caminho.exists():
                    continue
                paginas = self._ler_pdf(caminho)
                trechos = trechos_das_paginas(paginas)
                if not trechos:
                    continue
                with self.lock:
                    if self.fts:
                        self.con.execute("DELETE FROM busca WHERE doc_id=?", (d["id"],))
                    self.con.execute("DELETE FROM trechos_txt WHERE doc_id=?", (d["id"],))
                self._gravar(d["nome"], "usuario", caminho, None, len(paginas), trechos, paginas, doc_id=d["id"])
                log.info("documento lido de novo: %s (%d páginas, %d trechos)", d["nome"], len(paginas), len(trechos))
            except Exception:
                log.exception("reler %s", d["nome"])
        self.status = ""

    def _ler_pdf(self, caminho):
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        total = len(leitor.pages)
        paginas = []
        for i, pg in enumerate(leitor.pages, 1):
            self.status = f"Lendo {caminho.name}: página {i} de {total}"
            try:
                txt = pg.extract_text() or ""
            except Exception:
                txt = ""
            if len(txt.strip()) < 40:
                ocr = self._ocr_pagina(caminho, i - 1)
                if len(ocr.strip()) > len(txt.strip()):
                    txt = ocr
            txt = limpar(txt)
            if txt:
                paginas.append((i, txt))
        return sem_cabecalho(paginas)

    def _ocr_pagina(self, caminho, indice):
        """PDF escaneado: desenha a página como imagem e lê o texto (OCR)."""
        try:
            import numpy as np
            import pypdfium2 as pdfium
            if self._ocr is None:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            pdf = pdfium.PdfDocument(str(caminho))
            img = pdf[indice].render(scale=2.2).to_pil().convert("RGB")
            res, _ = self._ocr(np.array(img))
            pdf.close()
            return "\n".join(r[1] for r in (res or []))
        except Exception:
            log.exception("OCR da página %s falhou", indice + 1)
            return ""

    def remover(self, doc_id):
        d = self.q("SELECT * FROM docs WHERE id=?", (doc_id,))
        if d and d[0]["origem"] == "usuario":
            try:
                Path(d[0]["caminho"]).unlink(missing_ok=True)
            except Exception:
                pass
            self._apagar_doc(doc_id)
            return True
        return False

    # ------------------------------------------------------------------ documentos com um dia por página (liturgia, agendas…)
    def dia(self, data, secao=None):
        """Texto do dia 'dd/mm/aaaa': a página que COMEÇA com essa data (+ a continuação na página seguinte)."""
        linhas = self.q("SELECT p.doc_id, p.num, p.texto, d.nome FROM paginas p JOIN docs d ON d.id=p.doc_id "
                        "WHERE d.origem='usuario' AND p.texto LIKE ? ORDER BY p.doc_id, p.num", (f"%{data}%",))
        melhor = None
        for r in linhas:
            topo = [l for l in r["texto"].splitlines() if l.strip()][:5]
            if not any(re.match(r"\s*" + re.escape(data) + r"\b", l) for l in topo):
                continue
            secs = secoes(r["texto"], 4)
            if len(secs) < 2:
                continue
            nota = len(secs) + (10 if secao and any(chave_secao(t) == secao for t, _ in secs) else 0)
            if not melhor or nota > melhor[0]:
                melhor = (nota, r)
        if not melhor:
            return None
        r = melhor[1]
        texto = r["texto"]
        for prox in self.q("SELECT texto FROM paginas WHERE doc_id=? AND num>? ORDER BY num LIMIT 3", (r["doc_id"], r["num"])):
            if re.search(r"(?m)^\s*\d{2}/\d{2}/\d{4}\b", prox["texto"]) or re.search(r"(?m)^\s*DIA \d+\s*$", prox["texto"]):
                break                                   # começou outro dia
            texto += "\n" + prox["texto"]
        return {"doc": r["nome"], "pagina": r["num"], "texto": texto, "secoes": secoes(texto, 4)}

    def dia_por_nome(self, palavras):
        """'natal', 'imaculada conceição' → a data do dia cujo cabeçalho tem essas palavras (a que aparece mais no começo)."""
        if not palavras:
            return None
        melhor = None
        for r in self.q("SELECT p.texto FROM paginas p JOIN docs d ON d.id=p.doc_id WHERE d.origem='usuario'"):
            topo = [l for l in r["texto"].splitlines() if l.strip()][:5]
            data = next((m.group(0) for l in topo for m in [re.match(r"\s*\d{2}/\d{2}/\d{4}", l)] if m), None)
            if not data:
                continue
            cab = textutil.sem_acento(" ".join(l for l in topo if not re.match(r"\s*(DIA \d+|\d{2}/\d{2}/\d{4})", l)).lower())
            if all(re.search(r"\b" + re.escape(w), cab) for w in palavras):
                pos = min(cab.find(w) for w in palavras)
                if not melhor or pos < melhor[0]:
                    melhor = (pos, data.strip())
        return melhor[1] if melhor else None

    def periodo_dias(self):
        """(primeira, última) data com página própria nos documentos do usuário."""
        datas = []
        for r in self.q("SELECT p.texto FROM paginas p JOIN docs d ON d.id=p.doc_id WHERE d.origem='usuario'"):
            topo = [l for l in r["texto"].splitlines() if l.strip()][:5]
            for l in topo:
                m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})\b", l)
                if m:
                    datas.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
        if not datas:
            return None
        a, b = min(datas), max(datas)
        return f"{a[2]:02d}/{a[1]:02d}/{a[0]}", f"{b[2]:02d}/{b[1]:02d}/{b[0]}"

    def chaves_secoes(self):
        """{'dia': {chaves das seções dos dias}, 'soltas': {chave: (título, texto)}} — 'evangelho', 'salmo responsorial',
        e textos com título próprio fora dos dias (orações: 'pai nosso', 'ave maria'…)."""
        if getattr(self, "_cache_secoes", None) is not None:
            return self._cache_secoes
        from collections import Counter
        dia_cont, soltas = Counter(), {}
        for r in self.q("SELECT p.texto FROM paginas p JOIN docs d ON d.id=p.doc_id WHERE d.origem='usuario' ORDER BY p.doc_id, p.num"):
            topo = [l for l in r["texto"].splitlines() if l.strip()][:5]
            eh_dia = any(re.match(r"\s*\d{2}/\d{2}/\d{4}\b", l) for l in topo)
            for t, corpo in secoes(r["texto"], 4 if eh_dia else 0):
                if not t:
                    continue
                if eh_dia:
                    dia_cont[chave_secao(t)] += 1
                elif len(corpo) > 20 and chave_secao(t) not in soltas:
                    soltas[chave_secao(t)] = (t, corpo)
        dia = set(dia_cont)                                   # títulos das seções dos dias (EVANGELHO, SALMO…)
        self._cache_secoes = {"dia": dia, "soltas": soltas, "frequentes": {c for c, v in dia_cont.items() if v >= 3}}
        return self._cache_secoes

    # ------------------------------------------------------------------ consulta
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def listar(self):
        return self.q("SELECT id, nome, origem, paginas, trechos, criado FROM docs ORDER BY origem DESC, criado DESC")

    def buscar(self, pergunta, k=4):
        dia = []
        ts0 = [t for t in termos(pergunta) if not t.isdigit() and t not in ("dia", "data", "amanha", "ontem", "domingo",
                                                                          "segunda", "terca", "quarta", "quinta", "sexta", "sabado")]
        for data in datas_da_pergunta(pergunta) if ts0 else []:
            d = self.dia(data)
            # só quando a pergunta tem a ver com o documento do dia: nome do documento, títulos ou cabeçalho do dia
            alvo = ""
            if d:
                topo = [l for l in d["texto"].splitlines() if l.strip()][:5]
                alvo = textutil.sem_acento(" ".join([d["doc"]] + topo + [t for t, _ in d["secoes"]]).lower())
                alvo = re.sub(r"[^a-z0-9]+", " ", alvo)
            if d and any(re.search(r"\b" + re.escape(t[:5]), alvo) or re.match(r"(sant[oa]s?|celebra\w*|festa|memoria|"
                                                                                 r"solenidade|missa|liturgi\w*|cor)$", t)
                         for t in ts0 if len(t) >= 3):
                dia.append({"titulo": f"página {d['pagina']}", "texto": d["texto"], "nome": d["doc"], "origem": "usuario",
                            "nota": 0, "peso": 99, "max": 3500})
        if dia:
            return dia[:2]                              # a página daquela data, inteira: é o que importa
        ts = termos(pergunta)
        if not ts:
            return []
        progs = {PROGRAMAS[t] for t in ts if t in PROGRAMAS}
        with self.lock:
            if self.fts:
                consulta = " OR ".join(f'"{t}"*' if len(t) >= 4 else f'"{t}"' for t in ts)
                try:
                    linhas = self.con.execute(
                        "SELECT b.titulo, b.texto, d.nome, d.origem, bm25(busca, 4.0, 1.0) AS nota "
                        "FROM busca b JOIN docs d ON d.id = b.doc_id WHERE busca MATCH ? ORDER BY nota LIMIT 30",
                        (consulta,)).fetchall()
                except sqlite3.OperationalError:
                    log.exception("busca")
                    linhas = []
            else:
                linhas = self.con.execute(
                    "SELECT t.titulo, t.texto, d.nome, d.origem, 0 AS nota FROM trechos_txt t JOIN docs d ON d.id=t.doc_id "
                    "WHERE " + " OR ".join("t.texto LIKE ?" for _ in ts) + " LIMIT 30",
                    [f"%{t}%" for t in ts]).fetchall()
        res = []
        for r in linhas:
            r = dict(r)
            alvo = textutil.sem_acento((r["titulo"] + " " + r["texto"]).lower())
            acertos = sum(1 for t in ts if t in alvo)
            if acertos == 0:
                continue
            bonus = 0
            if progs:
                guia_prog = any(p.lower() in textutil.sem_acento(r["nome"].lower()) for p in progs)
                bonus = 3 if guia_prog else (-2 if r["origem"] == "guia" else 0)
            r["peso"] = acertos * 2 + bonus - (r["nota"] or 0) * 0.1
            res.append(r)
        res.sort(key=lambda r: -r["peso"])
        minimo = 2 if len(ts) == 1 else 4
        return [r for r in res if r["peso"] >= minimo][:k]


# ---------------------------------------------------------------------- utilidades
def sem_cabecalho(paginas):
    """Tira o cabeçalho/rodapé que se repete em quase todas as páginas ('Documento X · pág. 7'): ele tem datas e
    números que confundiam a busca (todas as páginas pareciam ser do dia 06/11)."""
    if len(paginas) < 4:
        return paginas
    from collections import Counter

    def forma(l):
        return re.sub(r"\d+", "#", l.strip())
    cont = Counter()
    for _, t in paginas:
        ls = [l for l in t.splitlines() if l.strip()]
        cont.update({forma(l) for l in ls[:2] + ls[-2:]})
    repetidas = {k for k, v in cont.items() if v >= max(3, len(paginas) * 0.4) and len(k) >= 15}
    if not repetidas:
        return paginas
    out = []
    for n, t in paginas:
        ls = t.splitlines()
        nz = [i for i, l in enumerate(ls) if l.strip()]
        bordas = set(nz[:2] + nz[-2:])
        t2 = "\n".join(l for i, l in enumerate(ls) if not (i in bordas and forma(l) in repetidas)).strip()
        if t2:
            out.append((n, t2))
    return out


def trechos_das_paginas(paginas):
    trechos = []
    for num, txt in paginas:
        for k, pedaco in enumerate(dividir_texto(txt)):
            trechos.append((f"página {num}" + (f" ({k + 1})" if k else ""), pedaco))
    return trechos


RX_TITULO = re.compile(r"^\s*[0-9ªº°]{0,3}\s*[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9ªº°,.'’\- –—]{2,70}?(\s*\([^)]{0,60}\))?\s*$")


def eh_titulo(linha):
    """Linha de título em MAIÚSCULAS ('EVANGELHO', '1ª LEITURA (referência)', 'PAI NOSSO')."""
    if not RX_TITULO.match(linha):
        return False
    base = re.sub(r"\(.*\)", "", linha)
    letras = [c for c in base if c.isalpha() and c not in "ªº"]
    return len(letras) >= 4 and all(c.isupper() for c in letras) and not re.match(r"\s*(DIA|PARTE|PÁG)\b", base.strip())


def chave_secao(titulo):
    t = textutil.sem_acento(re.sub(r"\(.*\)", "", titulo).lower())
    t = t.replace("ª", "a").replace("º", "o")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def secoes(texto, pular=0):
    """[(título, corpo)] — o primeiro é ('', cabeçalho) com o que vem antes do primeiro título.
    pular: nas primeiras N linhas (cabeçalho do dia: 'DIA 52', data, celebração em maiúsculas) não procura título."""
    out, titulo, corpo = [], "", []
    vistas = 0
    for l in texto.splitlines():
        if l.strip():
            vistas += 1
        if vistas > pular and eh_titulo(l):
            if titulo or "".join(corpo).strip():
                out.append((titulo, "\n".join(corpo).strip()))
            titulo, corpo = l.strip(), []
        else:
            corpo.append(l)
    if titulo or "".join(corpo).strip():
        out.append((titulo, "\n".join(corpo).strip()))
    return out


DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def datas_da_pergunta(pergunta, hoje=None):
    """'hoje', 'amanhã', 'ontem', 'domingo', '08/11', '8 de novembro' → ['dd/mm/aaaa']."""
    import datetime as dt
    hoje = hoje or dt.date.today()
    p = textutil.sem_acento(pergunta.lower())
    out = []
    if re.search(r"\bdepois de amanha\b", p):
        out.append(hoje + dt.timedelta(days=2))
    elif re.search(r"\bamanha\b", p):
        out.append(hoje + dt.timedelta(days=1))
    if re.search(r"\banteontem\b", p):
        out.append(hoje - dt.timedelta(days=2))
    elif re.search(r"\bontem\b", p):
        out.append(hoje - dt.timedelta(days=1))
    if re.search(r"\b(hoje|do dia|de agora)\b", p) and not out and not re.search(r"\d{1,2}[/\-.]\d{1,2}|\d+ de [a-z]+", p):
        out.append(hoje)
    p = re.sub(r"\b(primeira|segunda|1a|2a)\s+leitura", " leitura", p)
    m = re.search(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", p)
    if m and not out:
        dias = (DIAS_SEMANA[m.group(1)] - hoje.weekday()) % 7
        if re.search(r"\b(passad[oa]|ultim[oa])\b", p):
            dias = dias - 7 if dias else -7
        out.append(hoje + dt.timedelta(days=dias))
    from .leitor import _datas_da_pergunta
    for d in _datas_da_pergunta(p):
        dd, mm, aa = d.split("/")
        ano = int(aa) if aa else hoje.year
        try:
            x = dt.date(ano, int(mm), int(dd))
        except ValueError:
            continue
        if not aa and (hoje - x).days > 180:
            x = dt.date(ano + 1, int(mm), int(dd))     # "05/01" em novembro = janeiro do ano que vem
        out.append(x)
    vistos, res = set(), []
    for x in out:
        s_ = x.strftime("%d/%m/%Y")
        if s_ not in vistos:
            vistos.add(s_)
            res.append(s_)
    return res


def limpar(t):
    t = t.replace("\x00", " ").replace("­", "")
    t = re.sub(r"-\n(?=[a-zà-ú])", "", t)          # palavra quebrada no fim da linha
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def dividir_texto(t, tamanho=900):
    """Divide em trechos de até ~900 caracteres, sem cortar frases; repete a última frase no trecho seguinte."""
    t = limpar(t)
    if not t:
        return []
    unidades = []
    for p in re.split(r"\n\s*\n|\n(?=[A-ZÀ-Ú0-9•\-])", t):
        p = p.strip()
        if not p:
            continue
        if len(p) <= tamanho:
            unidades.append(p)
            continue
        for f in re.split(r"(?<=[.!?;])\s+", p):
            while len(f) > tamanho:
                unidades.append(f[:tamanho])
                f = f[tamanho:]
            if f.strip():
                unidades.append(f.strip())
    pedacos, atual = [], []
    for u in unidades:
        if atual and sum(len(x) + 1 for x in atual) + len(u) > tamanho:
            pedacos.append("\n".join(atual))
            atual = [atual[-1]] if len(atual[-1]) < 250 else []
        atual.append(u)
    if atual:
        pedacos.append("\n".join(atual))
    return pedacos


def dividir_markdown(md):
    """Um trecho por seção (## / ###), levando o caminho dos títulos junto."""
    trechos, h1, h2, h3, corpo = [], "", "", "", []

    def fechar():
        if corpo and "".join(corpo).strip():
            titulo = " › ".join(x for x in (h1, h2, h3) if x)
            for k, p in enumerate(dividir_texto("\n".join(corpo), tamanho=1100)):
                trechos.append((titulo + (f" ({k + 1})" if k else ""), p))

    for linha in md.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", linha)
        if m:
            fechar()
            corpo = []
            nivel, txt = len(m.group(1)), m.group(2).strip()
            if nivel == 1:
                h1, h2, h3 = txt, "", ""
            elif nivel == 2:
                h2, h3 = txt, ""
            else:
                h3 = txt
        else:
            corpo.append(linha)
    fechar()
    return trechos


def ler_docx(caminho):
    import zipfile
    with zipfile.ZipFile(caminho) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    import html
    return html.unescape(txt)
