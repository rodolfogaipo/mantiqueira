"""Leitura dos programas abertos: planilhas do Excel, documentos do Word, dados do SolidWorks e o texto
de qualquer outra janela (por imagem + OCR). Tudo local; só lê, nunca altera nada."""
import re
import time
import ctypes
import ctypes.wintypes as wt
import logging
import threading
import psutil
from . import textutil

log = logging.getLogger("leitor")
_cache = {}
_lock = threading.Lock()
MAX_LINHAS, MAX_COLS = 3000, 40


def _com(progid):
    import comtypes
    import comtypes.client as cc
    comtypes.CoInitialize()
    return cc.GetActiveObject(progid, dynamic=True)


def _cacheado(chave, ttl, fn):
    with _lock:
        c = _cache.get(chave)
        if c and time.time() - c[0] < ttl:
            return c[1]
    v = fn()
    with _lock:
        _cache[chave] = (time.time(), v)
    return v


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else f"{v:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    return str(v).strip()


# ---------------------------------------------------------------------- janelas abertas
def janelas_abertas():
    """[(hwnd, processo, titulo)] das janelas visíveis com título."""
    u = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd) and u.GetWindowTextLengthW(hwnd) > 0 and not u.GetWindow(hwnd, 4):  # sem dono
            n = u.GetWindowTextLengthW(hwnd)
            b = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, b, n + 1)
            pid = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                proc = psutil.Process(pid.value).name()
            except Exception:
                proc = "?"
            t = b.value.strip()
            if t and t not in ("Program Manager", "Mantiqueira", "Mantiqueira — ouvindo", "Mantiqueira — barra"):
                out.append((hwnd, proc, t))
        return True
    u.EnumWindows(cb, 0)
    return out


def lista_programas():
    linhas = []
    for _, proc, titulo in janelas_abertas():
        linhas.append(f"- {textutil.nome_app(proc)}: {textutil.curto(titulo, 90)}")
    return linhas[:25]


# ---------------------------------------------------------------------- Excel
def planilhas_abertas():
    """{(pasta_de_trabalho, aba): [[células...], ...]} das planilhas abertas no Excel."""
    def ler():
        dados = {}
        try:
            xl = _com("Excel.Application")
        except Exception:
            return dados
        try:
            for i in range(1, xl.Workbooks.Count + 1):
                wb = xl.Workbooks.Item(i)
                for j in range(1, wb.Worksheets.Count + 1):
                    ws = wb.Worksheets.Item(j)
                    try:
                        ur = ws.UsedRange
                        nl, nc = min(ur.Rows.Count, MAX_LINHAS), min(ur.Columns.Count, MAX_COLS)
                        if nl == 0 or nc == 0:
                            continue
                        r0, c0 = ur.Row, ur.Column
                        faixa = ws.Range(ws.Cells(r0, c0), ws.Cells(r0 + nl - 1, c0 + nc - 1))
                        v = faixa.Value
                        if callable(v):
                            v = v()
                        if not isinstance(v, (tuple, list)):
                            v = ((v,),)
                        linhas = [[_txt(x) for x in (row if isinstance(row, (tuple, list)) else (row,))] for row in v]
                        dados[(str(wb.Name), str(ws.Name))] = {"linhas": linhas, "lin0": r0, "col0": c0}
                    except Exception:
                        log.debug("aba ilegível", exc_info=True)
        except Exception:
            log.exception("Excel")
        return dados
    return _cacheado("excel", 20, ler)


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def trechos_planilhas(pergunta, maximo=40):
    """Linhas das planilhas abertas que têm a ver com a pergunta (com o cabeçalho junto)."""
    dados = planilhas_abertas()
    if not dados:
        return []
    termos = [t for t in re.findall(r"[0-9a-z,.]+", textutil.sem_acento(pergunta.lower())) if len(t) >= 2]
    termos = [t for t in termos if t not in {"qual", "quanto", "quantos", "quantas", "que", "na", "no", "da", "do", "de",
                                              "planilha", "excel", "aba", "linha", "coluna", "valor", "preco", "me", "fala",
                                              "diz", "tem", "esta", "aberta", "aberto", "um", "uma", "os", "as", "o", "a", "e"}]
    saida = []
    for (wb, aba), d in dados.items():
        linhas = d["linhas"]
        if not linhas:
            continue
        cab = linhas[0]
        achadas = []
        for i, row in enumerate(linhas[1:], start=1):
            alvo = textutil.sem_acento(" ".join(row).lower())
            pontos = sum(1 for t in termos if t in alvo)
            if pontos:
                achadas.append((pontos, i, row))
        cab_alvo = textutil.sem_acento(" ".join(cab).lower())
        cab_bate = any(t in cab_alvo for t in termos) or textutil.sem_acento(wb.lower()).split(".")[0] in \
            textutil.sem_acento(pergunta.lower())
        if not achadas and not cab_bate:
            continue
        achadas.sort(key=lambda x: (-x[0], x[1]))
        bloco = [f"[Planilha aberta: {wb} — aba {aba} — {len(linhas) - 1} linhas]",
                 "Cabeçalho: " + " | ".join(f"{_col(d['col0'] + k)}={c}" for k, c in enumerate(cab) if c)]
        mostrar = achadas[:15] if achadas else [(0, i, linhas[i]) for i in range(1, min(len(linhas), 16))]
        for _, i, row in sorted(mostrar, key=lambda x: x[1]):
            bloco.append(f"Linha {d['lin0'] + i}: " + " | ".join(
                f"{cab[k] if k < len(cab) and cab[k] else _col(d['col0'] + k)}={c}" for k, c in enumerate(row) if c))
        # totais numéricos de cada coluna (o Mantiqueira não precisa somar de cabeça)
        totais = []
        for k, nome in enumerate(cab):
            nums = []
            for row in linhas[1:]:
                if k < len(row):
                    s = row[k].replace(".", "").replace(",", ".") if re.fullmatch(r"-?[\d.]+,\d+|-?\d+", row[k] or "") else ""
                    try:
                        nums.append(float(s)) if s else None
                    except ValueError:
                        pass
            if len(nums) >= 3 and nome:
                totais.append(f"{nome}: soma {_txt(sum(nums))}, média {_txt(sum(nums) / len(nums))}")
        if totais:
            bloco.append("Totais das colunas: " + "; ".join(totais[:10]))
        saida.append("\n".join(bloco))
        if sum(len(b) for b in saida) > 7000 or len(saida) >= 4:
            break
    return saida


# ---------------------------------------------------------------------- Word
def documentos_word():
    def ler():
        docs = {}
        try:
            w = _com("Word.Application")
            for i in range(1, w.Documents.Count + 1):
                d = w.Documents.Item(i)
                docs[str(d.Name)] = str(d.Content.Text)[:60000]
        except Exception:
            pass
        return docs
    return _cacheado("word", 30, ler)


def trechos_word(pergunta):
    docs = documentos_word()
    if not docs:
        return []
    termos = [t for t in re.findall(r"[a-z0-9]{3,}", textutil.sem_acento(pergunta.lower()))]
    out = []
    for nome, txt in docs.items():
        paragrafos = [p.strip() for p in txt.split("\r") if p.strip()]
        pts = []
        for i, p in enumerate(paragrafos):
            alvo = textutil.sem_acento(p.lower())
            s = sum(1 for t in termos if t in alvo)
            if s:
                pts.append((s, i, p))
        pts.sort(key=lambda x: (-x[0], x[1]))
        if pts or textutil.sem_acento(nome.lower()).split(".")[0] in textutil.sem_acento(pergunta.lower()):
            escolhidos = sorted(pts[:8], key=lambda x: x[1]) if pts else [(0, i, p) for i, p in enumerate(paragrafos[:8])]
            out.append(f"[Documento aberto no Word: {nome}]\n" + "\n".join(p[:600] for _, _, p in escolhidos))
    return out


# ---------------------------------------------------------------------- SolidWorks
def solidworks_info():
    def ler():
        try:
            sw = _com("SldWorks.Application")
            doc = sw.ActiveDoc
            if doc is None:
                return None
            tipos = {1: "peça", 2: "montagem", 3: "desenho"}
            info = {"titulo": str(doc.GetTitle() or ""), "caminho": str(doc.GetPathName() or ""),
                    "tipo": tipos.get(doc.GetType(), "?")}
            try:
                info["configuracao"] = str(doc.ConfigurationManager.ActiveConfiguration.Name)
                nomes = doc.GetConfigurationNames()
                info["configuracoes"] = [str(x) for x in (nomes or [])][:20]
            except Exception:
                pass
            props = {}
            try:
                for nome in (doc.GetCustomInfoNames2("") or []):
                    props[str(nome)] = str(doc.GetCustomInfoValue("", nome))
            except Exception:
                pass
            info["propriedades"] = props
            try:
                mp = doc.Extension.CreateMassProperty()
                if mp is not None:
                    info["massa_kg"] = round(float(mp.Mass), 3)
                    info["volume_m3"] = float(mp.Volume)
            except Exception:
                pass
            if info["tipo"] == "montagem":
                try:
                    info["componentes"] = int(doc.GetComponentCount(False))
                except Exception:
                    pass
            return info
        except Exception:
            return None
    return _cacheado("sw", 15, ler)


def texto_solidworks():
    i = solidworks_info()
    if not i:
        return ""
    l = [f"[SolidWorks — documento ativo: {i['titulo']} ({i['tipo']})]", f"Caminho: {i['caminho'] or '(ainda não salvo)'}"]
    if i.get("configuracao"):
        l.append(f"Configuração ativa: {i['configuracao']}" +
                 (f" (todas: {', '.join(i.get('configuracoes', []))})" if i.get("configuracoes") else ""))
    if i.get("massa_kg") is not None:
        l.append(f"Massa: {str(i['massa_kg']).replace('.', ',')} kg")
    if i.get("componentes"):
        l.append(f"Componentes na montagem: {i['componentes']}")
    if i.get("propriedades"):
        l.append("Propriedades: " + "; ".join(f"{k} = {v}" for k, v in list(i["propriedades"].items())[:25]))
    return "\n".join(l)


# ---------------------------------------------------------------------- qualquer janela (OCR)
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def capturar_janela(hwnd):
    """Imagem (PIL) da janela, mesmo que esteja atrás de outras (não funciona se estiver minimizada)."""
    from PIL import Image
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    hdc = u.GetWindowDC(hwnd)
    mdc = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mdc, bmp)
    ok = u.PrintWindow(hwnd, mdc, 2)          # PW_RENDERFULLCONTENT
    bi = BITMAPINFOHEADER()
    bi.biSize, bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = ctypes.sizeof(bi), w, -h, 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mdc)
    u.ReleaseDC(hwnd, hdc)
    if not ok:
        return None
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def ler_janela(nome_programa):
    """Texto de uma janela aberta cujo programa/título combina com o nome pedido."""
    from . import tela, paths
    alvo = textutil.sem_acento(nome_programa.lower())
    melhor = None
    for hwnd, proc, titulo in janelas_abertas():
        t = textutil.sem_acento((textutil.nome_app(proc) + " " + titulo + " " + proc).lower())
        if alvo and alvo in t:
            melhor = (hwnd, proc, titulo)
            break
    if not melhor:
        return None, ""
    hwnd, proc, titulo = melhor
    if ctypes.windll.user32.IsIconic(hwnd):
        return titulo, ""
    img = capturar_janela(hwnd)
    if img is None:
        return titulo, ""
    arq = paths.DADOS / "janela.png"
    img.save(arq)
    return titulo, tela.ocr_arquivo(arq)


def contexto(pergunta):
    """Tudo dos programas abertos que pode ajudar a responder a pergunta."""
    partes = []
    try:
        progs = lista_programas()
        if progs:
            partes.append("PROGRAMAS ABERTOS AGORA:\n" + "\n".join(progs))
    except Exception:
        log.exception("janelas")
    p = textutil.sem_acento(pergunta.lower())
    try:
        pl = trechos_planilhas(pergunta)
        if pl:
            partes.append("DADOS DAS PLANILHAS ABERTAS NO EXCEL (use estes valores, não invente):\n" + "\n\n".join(pl))
    except Exception:
        log.exception("planilhas")
    try:
        wd = trechos_word(pergunta)
        if wd:
            partes.append("TRECHOS DE DOCUMENTOS ABERTOS NO WORD:\n" + "\n\n".join(wd))
    except Exception:
        log.exception("word")
    if re.search(r"solid|peca|montagem|massa|peso|material|configurac|propriedade|codigo|desenho|cota", p):
        try:
            sw = texto_solidworks()
            if sw:
                partes.append(sw)
        except Exception:
            log.exception("solidworks")
    return partes
