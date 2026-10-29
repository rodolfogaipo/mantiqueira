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


def _txt(v, pct=False):
    import datetime as _dt
    if v is None:
        return ""
    if isinstance(v, _dt.datetime):
        return v.strftime("%d/%m/%Y") if (v.hour, v.minute) == (0, 0) else v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, _dt.date):
        return v.strftime("%d/%m/%Y")
    if pct and isinstance(v, (int, float)):
        x = v * 100
        return (f"{x:.1f}".replace(".", ",")) + "%"
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
            ativo_wb = ativo_ws = ""
            try:
                ativo_wb, ativo_ws = str(xl.ActiveWorkbook.Name), str(xl.ActiveSheet.Name)
            except Exception:
                pass
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
                        # colunas em porcentagem: olha o formato de algumas células de cada coluna
                        pct = set()
                        amostra = [r0 + min(nl - 1, k) for k in (2, 5, 10, nl - 1)]
                        for k in range(nc):
                            try:
                                if any("%" in str(ws.Cells(rr, c0 + k).NumberFormat) for rr in set(amostra)):
                                    pct.add(k)
                            except Exception:
                                pass
                        linhas = [[_txt(x, k in pct) for k, x in enumerate(row if isinstance(row, (tuple, list)) else (row,))]
                                  for row in v]
                        dados[(str(wb.Name), str(ws.Name))] = {"linhas": linhas, "lin0": r0, "col0": c0,
                                                               "ativa": (str(wb.Name), str(ws.Name)) == (ativo_wb, ativo_ws)}
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


ULTIMAS_LINHAS = []          # linhas exatas usadas na última resposta (mostradas na tela como fonte)


def _cabecalho(linhas):
    """Índice da linha de cabeçalho: entre as 15 primeiras, a que tem mais textos (não números) preenchidos."""
    melhor, idx = -1, 0
    for i, row in enumerate(linhas[:15]):
        n = sum(1 for c in row if c and not re.fullmatch(r"[-+]?[\d.,%]+|\d{2}/\d{2}/\d{4}.*", c))
        if n > melhor:
            melhor, idx = n, i
    return idx


def _datas_da_pergunta(p):
    """Datas citadas ('23-08-2026', '23/08', '23 de agosto') no formato dd/mm/aaaa ou dd/mm."""
    import datetime as _dt
    meses = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
             "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
    out = []
    for m in re.finditer(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", p):
        d, mm, a = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= d <= 31 and 1 <= mm <= 12:
            if a:
                a = int(a) + (2000 if int(a) < 100 else 0)
                out.append(f"{d:02d}/{mm:02d}/{a}")
            else:
                out.append(f"{d:02d}/{mm:02d}/")
    for m in re.finditer(r"\b(\d{1,2}) de (" + "|".join(meses) + r")(?: de (\d{4}))?", p):
        d, mm = int(m.group(1)), meses[m.group(2)]
        out.append(f"{d:02d}/{mm:02d}/{m.group(3)}" if m.group(3) else f"{d:02d}/{mm:02d}/")
    return out


def trechos_planilhas(pergunta, maximo=40):
    """Linhas das planilhas abertas que têm a ver com a pergunta (com o cabeçalho certo junto).
    Se a pergunta cita uma data, manda SÓ a(s) linha(s) dessa data, para não haver confusão de semana."""
    dados = planilhas_abertas()
    ULTIMAS_LINHAS.clear()
    if not dados:
        return []
    p = textutil.sem_acento(pergunta.lower())
    datas = _datas_da_pergunta(p)
    p_sem_datas = re.sub(r"\b\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?\b", " ", p)
    termos = [t for t in re.findall(r"[0-9a-z,.]+", p_sem_datas) if len(t) >= 2]
    termos = [t for t in termos if t not in {"qual", "quanto", "quantos", "quantas", "que", "na", "no", "da", "do", "de",
                                              "planilha", "excel", "aba", "linha", "coluna", "valor", "preco", "me", "fala",
                                              "diz", "tem", "esta", "aberta", "aberto", "um", "uma", "os", "as", "o", "a", "e",
                                              "semana", "dia", "fez", "feito", "feitos", "teve", "em", "foi", "foram", "mantiqueira"}]
    # abas citadas pelo nome ("a Máyra", "plano de corte") ganham prioridade; depois, a aba que está na tela
    citadas = [k for k in dados if any(len(w) >= 3 and re.search(r"\b" + re.escape(w) + r"\b", p)
                                       for w in re.findall(r"[a-z0-9]+", textutil.sem_acento(k[1].lower())))]
    ordem = citadas or sorted(dados, key=lambda k: not dados[k].get("ativa"))
    saida = []
    for (wb, aba) in ordem:
        d = dados[(wb, aba)]
        linhas = d["linhas"]
        if not linhas:
            continue
        h = _cabecalho(linhas)
        cab = linhas[h]
        corpo = list(enumerate(linhas[h + 1:], start=h + 1))
        achadas = []
        if datas:
            for i, row in corpo:
                if any(c.startswith(dt_) or c == dt_.rstrip("/") for c in row for dt_ in datas):
                    achadas.append((9, i, row))
        if not achadas:
            for i, row in corpo:
                alvo = textutil.sem_acento(" ".join(row).lower())
                pontos = sum(1 for t in termos if t in alvo)
                if pontos and not datas:
                    achadas.append((pontos, i, row))
        cab_alvo = textutil.sem_acento(" ".join(cab).lower())
        cab_bate = any(t in cab_alvo for t in termos) or (wb, aba) in citadas or d.get("ativa") or \
            textutil.sem_acento(wb.lower()).split(".")[0] in p
        if not achadas and not cab_bate:
            continue
        achadas.sort(key=lambda x: (-x[0], x[1]))

        def fmt(i, row):
            return f"Linha {d['lin0'] + i}: " + " | ".join(
                f"{cab[k] if k < len(cab) and cab[k] else _col(d['col0'] + k)}={c}" for k, c in enumerate(row) if c)
        bloco = [f"[Planilha aberta: {wb} — aba {aba}{' (a que está na tela)' if d.get('ativa') else ''} — "
                 f"{len(corpo)} linhas de dados]",
                 "Cabeçalho (linha " + str(d["lin0"] + h) + "): " +
                 " | ".join(f"{_col(d['col0'] + k)}={c}" for k, c in enumerate(cab) if c)]
        if datas and achadas:
            bloco.append(f"LINHA EXATA DA DATA PEDIDA ({', '.join(datas)}) — responda usando SOMENTE esta linha:")
            for _, i, row in achadas[:3]:
                bloco.append(fmt(i, row))
                ULTIMAS_LINHAS.append(f"{aba} · " + fmt(i, row))
        else:
            if datas:
                bloco.append(f"ATENÇÃO: nenhuma linha desta aba tem a data {', '.join(datas)}. Diga que não encontrou essa data.")
            mostrar = achadas[:15] if achadas else ([] if datas else [(0, i, row) for i, row in corpo[:15]])
            for _, i, row in sorted(mostrar, key=lambda x: x[1]):
                bloco.append(fmt(i, row))
            totais = []
            for k, nome in enumerate(cab):
                nums = []
                for _, row in corpo:
                    if k < len(row):
                        x = row[k].rstrip("%")
                        s_ = x.replace(".", "").replace(",", ".") if re.fullmatch(r"-?[\d.]+,\d+|-?\d+", x or "") else ""
                        try:
                            nums.append(float(s_)) if s_ else None
                        except ValueError:
                            pass
                if len(nums) >= 3 and nome:
                    totais.append(f"{nome}: soma {_txt(sum(nums))}, média {_txt(sum(nums) / len(nums))}")
            if totais and not datas:
                bloco.append("Totais das colunas: " + "; ".join(totais[:10]))
        saida.append("\n".join(bloco))
        if sum(len(b) for b in saida) > 7000 or len(saida) >= 3 or (citadas and len(saida) >= len(citadas)):
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
