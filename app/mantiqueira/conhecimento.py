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
            self.con.execute("DELETE FROM docs WHERE id=?", (doc_id,))
            self.con.commit()

    def _gravar(self, nome, origem, caminho, h, paginas, trechos):
        with self.lock:
            cur = self.con.execute("INSERT INTO docs(nome,origem,caminho,hash,paginas,trechos,criado) VALUES(?,?,?,?,?,?,?)",
                                   (nome, origem, str(caminho), h, paginas, len(trechos), fmt(agora())))
            did = cur.lastrowid
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
        if ext == ".pdf":
            paginas = self._ler_pdf(copia)
            trechos = []
            for num, txt in paginas:
                for k, pedaco in enumerate(dividir_texto(txt)):
                    trechos.append((f"página {num}" + (f" ({k + 1})" if k else ""), pedaco))
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
        self._gravar(origem.name, "usuario", copia, h, npag, trechos)
        return origem.name, npag, len(trechos)

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
        return paginas

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

    # ------------------------------------------------------------------ consulta
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def listar(self):
        return self.q("SELECT id, nome, origem, paginas, trechos, criado FROM docs ORDER BY origem DESC, criado DESC")

    def buscar(self, pergunta, k=4):
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
