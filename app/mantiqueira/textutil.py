"""Utilidades de texto em português: datas/horários falados, nomes de arquivo, preparo para a voz."""
import re
import unicodedata
import difflib
import datetime as dt

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
_DIAS_RX = [("segunda", 0), ("terca", 1), ("quarta", 2), ("quinta", 3), ("sexta", 4), ("sabado", 5), ("domingo", 6)]
_NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
        "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "quinze": 15, "vinte": 20, "trinta": 30,
        "quarenta": 40, "meia": 30}


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def data_extenso(d: dt.datetime) -> str:
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}, {d:%H:%M}"


def _num(tok):
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    return _NUM.get(tok)


def parse_quando(campo: str, agora: dt.datetime, texto_usuario: str = ""):
    """Interpreta o horário do lembrete. Tenta primeiro o campo da IA, depois a frase do usuário."""
    for cand in (campo or "", texto_usuario or ""):
        r = _parse(sem_acento(cand.lower()).strip(), agora)
        if r:
            return r
    return None


def _parse(t: str, agora: dt.datetime):
    if not t:
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})[ t]+(\d{1,2}):(\d{2})", t)
    if m:
        try:
            return dt.datetime(*map(int, m.groups()))
        except ValueError:
            return None
    if re.search(r"(?:daqui a|daqui|em|dentro de)\s+meia hora", t):
        return (agora + dt.timedelta(minutes=30)).replace(second=0, microsecond=0)
    m = re.search(r"(?:daqui a|daqui|em|dentro de)\s+(\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|oito|nove|dez|"
                  r"quinze|vinte|trinta|quarenta)\s*(minutos?|min|horas?|h|dias?)\b", t)
    if m:
        n = _num(m.group(1))
        if n:
            u = m.group(2)
            if u.startswith("d"):
                alvo = agora + dt.timedelta(days=n)
                hm = re.search(r"\b(\d{1,2})\s*(?::|h)\s*(\d{2})?\b", t)
                if hm:
                    alvo = alvo.replace(hour=int(hm.group(1)), minute=int(hm.group(2) or 0))
                return alvo.replace(second=0, microsecond=0)
            mult = 60 if u.startswith("h") else 1
            return (agora + dt.timedelta(minutes=n * mult)).replace(second=0, microsecond=0)

    base = agora.date()
    tem_dia = semana = False
    if "depois de amanha" in t:
        base += dt.timedelta(days=2); tem_dia = True
    elif "amanha" in t:
        base += dt.timedelta(days=1); tem_dia = True
    elif "hoje" in t:
        tem_dia = True
    else:
        for nome, idx in _DIAS_RX:
            if re.search(r"\b" + nome, t):
                dias = (idx - agora.weekday()) % 7
                base += dt.timedelta(days=dias); tem_dia = True
                semana = True
                break
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        ano = int(m.group(3)) if m.group(3) else agora.year
        if ano < 100:
            ano += 2000
        try:
            base = dt.date(ano, int(m.group(2)), int(m.group(1))); tem_dia = True
        except ValueError:
            pass

    hora = minuto = None
    if "meio-dia" in t or "meio dia" in t:
        hora, minuto = 12, 0
    elif "meia-noite" in t or "meia noite" in t:
        hora, minuto = 0, 0
    m = re.search(r"\b(\d{1,2})\s*(?::|h|horas?)\s*(?:e\s*)?(\d{2})?\b", t)
    if m and hora is None:
        hora, minuto = int(m.group(1)), int(m.group(2) or 0)
    if hora is None:
        m = re.search(r"\b(?:as|a|pelas|lá pelas)\s+(\d{1,2})\b(?:\s*e\s*(\d{1,2}|meia))?", t)
        if m:
            hora = int(m.group(1))
            mm = m.group(2)
            minuto = 30 if mm == "meia" else int(mm or 0)
    if hora is None:
        if tem_dia:
            hora, minuto = 9, 0   # "amanhã" sem hora → 9h
        else:
            return None
    if ("da tarde" in t or "da noite" in t) and hora < 12:
        hora += 12
    if hora > 23 or minuto > 59:
        return None
    alvo = dt.datetime.combine(base, dt.time(hora, minuto))
    if semana and alvo <= agora:
        alvo += dt.timedelta(days=7)
    if not tem_dia and alvo <= agora:
        # "às 9" quando já passou das 9 → próximo horário possível
        if hora < 12 and not ("da manha" in t) and alvo + dt.timedelta(hours=12) > agora:
            alvo += dt.timedelta(hours=12)
        else:
            alvo += dt.timedelta(days=1)
    return alvo


def proxima_repeticao(quando: dt.datetime, repetir: str):
    if repetir == "diario":
        return quando + dt.timedelta(days=1)
    if repetir == "semanal":
        return quando + dt.timedelta(days=7)
    if repetir == "dias_uteis":
        n = quando + dt.timedelta(days=1)
        while n.weekday() >= 5:
            n += dt.timedelta(days=1)
        return n
    return None


# ---------------- arquivos em títulos de janela ----------------
EXTS = ("sldprt|sldasm|slddrw|xlsx|xlsm|xls|csv|docx|doc|pdf|dxf|dwg|dwf|pptx|ppt|txt|step|stp|igs|iges|"
        "stl|x_t|png|jpg|jpeg|zip|nc|cnc|eprt|easm|edrw|3mf|obj")
_RX_ARQ = re.compile(r"([^\\/:*?\"<>|\[\]]+?\.(?:%s))(?![\w])" % EXTS, re.I)
_OFFICE = {"excel.exe": "Excel", "winword.exe": "Word", "powerpnt.exe": "PowerPoint"}

APPS = {
    "sldworks.exe": "SolidWorks", "excel.exe": "Excel", "winword.exe": "Word", "powerpnt.exe": "PowerPoint",
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "explorer.exe": "Explorador",
    "acrord32.exe": "Acrobat", "acrobat.exe": "Acrobat", "notepad.exe": "Bloco de notas",
    "acad.exe": "AutoCAD", "outlook.exe": "Outlook", "olk.exe": "Outlook", "ms-teams.exe": "Teams",
    "teams.exe": "Teams", "whatsapp.exe": "WhatsApp", "code.exe": "VS Code", "edrawings.exe": "eDrawings",
    "inventor.exe": "Inventor", "rhino.exe": "Rhino", "photoshop.exe": "Photoshop", "illustrator.exe": "Illustrator",
    "coreldrw.exe": "CorelDRAW", "sketchup.exe": "SketchUp", "applicationframehost.exe": "Aplicativo",
}

CAD = {"SolidWorks", "AutoCAD", "Inventor", "Rhino", "SketchUp", "eDrawings"}


def nome_app(processo: str) -> str:
    p = (processo or "").lower()
    if p in APPS:
        return APPS[p]
    base = p[:-4] if p.endswith(".exe") else p
    return base[:1].upper() + base[1:] if base else "?"


def extrair_arquivo(processo: str, titulo: str):
    """Devolve (nome_do_arquivo_ou_pasta, nao_salvo) a partir do título da janela."""
    t = titulo or ""
    proc = (processo or "").lower()
    nao_salvo = t.lstrip().startswith("*")
    nome = None
    m = _RX_ARQ.search(t)
    if m:
        nome = m.group(1).split(" - ")[-1].strip(" -*[]•")
        if re.search(re.escape(nome) + r"\s*\*", t):
            nao_salvo = True
    if not nome and proc in _OFFICE:
        partes = [p.strip(" *") for p in t.split(" - ")]
        if len(partes) >= 2 and partes[0]:
            nome = partes[0]
    if not nome and proc == "explorer.exe" and t:
        nome = t.strip()
    return nome, nao_salvo


def curto(nome: str, n=34) -> str:
    if not nome:
        return ""
    return nome if len(nome) <= n else nome[: n - 1] + "…"


def duracao_texto(seg: float) -> str:
    m = int(round(seg / 60))
    if m < 1:
        return "menos de um minuto"
    if m < 60:
        return f"{m} minuto" + ("s" if m != 1 else "")
    h, mm = divmod(m, 60)
    txt = f"{h} hora" + ("s" if h != 1 else "")
    if mm >= 5:
        txt += f" e {mm} minutos"
    return txt


# ---------------- palavra de ativação ----------------
def parece_ativacao(texto: str, alvos) -> bool:
    w = re.sub(r"[^a-z ]", " ", sem_acento(texto.lower())).split()
    alvos_n = [re.sub(r"[^a-z]", "", sem_acento(a.lower())) for a in alvos if a]
    for i in range(len(w)):
        for n in (1, 2, 3):
            seg = "".join(w[i:i + n])
            if len(seg) < 6:
                continue
            for a in alvos_n:
                if abs(len(seg) - len(a)) <= 4 and difflib.SequenceMatcher(None, seg, a).ratio() >= 0.78:
                    return True
    return False


def _bate(seg: str, alvos) -> bool:
    seg = re.sub(r"[^a-z]", "", sem_acento(seg.lower()))
    for a in alvos:
        a = re.sub(r"[^a-z]", "", sem_acento((a or "").lower()))
        if a and len(seg) >= 6 and abs(len(seg) - len(a)) <= 3 and \
                difflib.SequenceMatcher(None, seg, a).ratio() >= 0.78:
            return True
    return False


def remover_ativacao(texto: str, alvos) -> str:
    """Tira a palavra de ativação (e o que vier antes dela) do começo da frase transcrita."""
    palavras = texto.strip().split()
    for i in range(min(3, len(palavras))):
        for n in (1, 2, 3):
            if i + n <= len(palavras) and _bate(" ".join(palavras[i:i + n]), alvos):
                return " ".join(palavras[i + n:]).lstrip(" ,.!?;:-").strip()
    return texto.strip()


# ---------------- preparo do texto para a voz ----------------
def para_fala(t: str) -> str:
    t = re.sub(r"[*_#`>|]", " ", t)
    t = re.sub(r"\.(sldprt|sldasm|slddrw|xlsx|xlsm|xls|docx|doc|pdf|dxf|dwg|pptx|txt|csv|step|stp)\b", "", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})h(\d{2})\b", r"\1 e \2", t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: m.group(1) if m.group(2) == "00" else f"{m.group(1)} e {m.group(2)}", t)
    t = re.sub(r"\b(\d{1,2})h\b", r"\1 horas", t)
    t = re.sub(r"(?<=[a-zA-Z])_(?=[a-zA-Z0-9])", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ---------------- intenção de lembrete ----------------
_RX_LEMBRETE = re.compile(
    r"\b(me lembr|lembr[ae] (me|de|que)|me avis|avis[ae] (me|de|que|quando)|nao (me )?deix[ae] esquecer|"
    r"agend(e|ar)\b|agenda (pra|para|um|uma|isso|ai|a reuniao|o)\b|marc[ae]r? (um |uma )?(lembrete|compromisso|reuniao|horario)|"
    r"cri[ae]r? (um )?lembrete|poe (um )?lembrete|coloc[ae] (um )?lembrete)")
_RX_TEMPO = re.compile(
    r"\b(\d{1,2}\s*(h|:|horas?)|as \d|a \d{1,2}\b|daqui|em \d+|em (um|uma|dois|duas|meia)|dentro de|amanha|hoje|"
    r"depois de amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo|\d{1,2}/\d{1,2}|meio[- ]dia|"
    r"meia[- ]noite|semana que vem|toda|todo dia|todos os dias|diariamente|dias uteis|de manha|a tarde|a noite)\b")


def pede_lembrete(t: str) -> bool:
    return bool(_RX_LEMBRETE.search(sem_acento((t or "").lower())))


def tem_tempo(t: str) -> bool:
    return bool(_RX_TEMPO.search(sem_acento((t or "").lower())))


def repeticao(t: str) -> str:
    t = sem_acento((t or "").lower())
    if re.search(r"dias? ute(is|l)|segunda a sexta", t):
        return "dias_uteis"
    if re.search(r"todo (santo )?dia|todos os dias|diariamente|toda (manha|tarde|noite)", t):
        return "diario"
    if re.search(r"toda semana|todas as semanas|semanalmente|tod[ao]s? (as )?(segunda|terca|quarta|quinta|sexta|sabado|domingo)", t):
        return "semanal"
    return ""


def texto_do_lembrete(t: str) -> str:
    """Tira 'me lembra de', horários etc. e deixa só a tarefa."""
    x = (t or "").strip()
    x = re.sub(r"^(mantiqueira[,!]?\s*)", "", x, flags=re.I)
    x = re.sub(r"^(por favor[, ]*)?(me )?(lembr[ae]|avis[ae])( me)?( de| que| para| pra)?\s*", "", x, flags=re.I)
    x = re.sub(r"\b(daqui|em|dentro de)\s+(a\s+)?(\d+|um|uma|dois|duas|meia)\s*(minutos?|min|horas?|hora|dias?)\b", "", x, flags=re.I)
    x = re.sub(r"\b(amanh[ãa]|hoje|depois de amanh[ãa])\b", "", x, flags=re.I)
    x = re.sub(r"\b(toda|todo|todas|todos)( as| os)? (dia|dias|semana|segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)s?(-feira)?( úteis| uteis)?\b", "", x, flags=re.I)
    x = re.sub(r"\b(às|as|a|pelas)\s+\d{1,2}([:h]\d{2})?( horas?)?( da (manhã|manha|tarde|noite))?", "", x, flags=re.I)
    x = re.sub(r"^(de|da|do|para|pra)\s+", "", x.strip(), flags=re.I)
    x = re.sub(r"\s+", " ", x).strip(" ,.;")
    return (x[:1].upper() + x[1:]) if x else "Lembrete"
