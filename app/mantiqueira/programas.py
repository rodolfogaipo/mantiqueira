"""Programas e comandos do computador: abrir, trazer para frente, minimizar e fechar programas, digitar,
apertar teclas, volume do Windows, bloquear, desligar/reiniciar (sempre com confirmação) e print da tela.

Segurança: nunca "mata" um programa — fechar é o mesmo que clicar no X (o programa pergunta se quer salvar);
nunca apaga nada; desligar e reiniciar só depois do "sim" e com 30 segundos para cancelar."""
import os
import re
import time
import ctypes
import logging
import subprocess
import threading
from . import textutil

log = logging.getLogger("programas")
SEM_JANELA = 0x08000000

# nome falado → (nome bonito, executável conhecido ou None, processos que contam como "aberto", palavras do atalho)
CONHECIDOS = {
    "solidworks": ("SolidWorks", None, ["sldworks.exe"], ["solidworks"]),
    "solid": ("SolidWorks", None, ["sldworks.exe"], ["solidworks"]),
    "autocad": ("AutoCAD", None, ["acad.exe"], ["autocad"]),
    "sketchup": ("SketchUp", None, ["sketchup.exe"], ["sketchup"]),
    "sketch up": ("SketchUp", None, ["sketchup.exe"], ["sketchup"]),
    "3ds max": ("3ds Max", None, ["3dsmax.exe"], ["3ds", "max"]),
    "3d max": ("3ds Max", None, ["3dsmax.exe"], ["3ds", "max"]),
    "aspire": ("Aspire", None, ["aspire.exe"], ["aspire"]),
    "vectric": ("Aspire", None, ["aspire.exe"], ["aspire"]),
    "cypcut": ("CypCut", None, ["cypcut.exe"], ["cypcut"]),
    "cyp cut": ("CypCut", None, ["cypcut.exe"], ["cypcut"]),
    "audaces": ("Audaces", None, [], ["audaces"]),
    "gaipo nest": ("Gaipo Nest", None, [], ["gaipo"]),
    "gaipo": ("Gaipo Nest", None, [], ["gaipo"]),
    "nest": ("Gaipo Nest", None, [], ["gaipo"]),
    "excel": ("Excel", "excel.exe", ["excel.exe"], ["excel"]),
    "word": ("Word", "winword.exe", ["winword.exe"], ["word"]),
    "powerpoint": ("PowerPoint", "powerpnt.exe", ["powerpnt.exe"], ["powerpoint"]),
    "power point": ("PowerPoint", "powerpnt.exe", ["powerpnt.exe"], ["powerpoint"]),
    "outlook": ("Outlook", "outlook.exe", ["outlook.exe", "olk.exe"], ["outlook"]),
    "teams": ("Teams", None, ["ms-teams.exe", "teams.exe"], ["teams"]),
    "whatsapp": ("WhatsApp", None, ["whatsapp.exe", "whatsapp.root.exe"], ["whatsapp"]),
    "chrome": ("Chrome", "chrome.exe", ["chrome.exe"], ["chrome"]),
    "google chrome": ("Chrome", "chrome.exe", ["chrome.exe"], ["chrome"]),
    "edge": ("Edge", "msedge.exe", ["msedge.exe"], ["edge"]),
    "navegador": ("navegador", "chrome.exe|msedge.exe", ["chrome.exe", "msedge.exe"], []),
    "internet": ("navegador", "chrome.exe|msedge.exe", ["chrome.exe", "msedge.exe"], []),
    "calculadora": ("Calculadora", "calc.exe", ["calculatorapp.exe", "calc.exe", "win32calc.exe"], []),
    "bloco de notas": ("Bloco de Notas", "notepad.exe", ["notepad.exe"], []),
    "notepad": ("Bloco de Notas", "notepad.exe", ["notepad.exe"], []),
    "paint": ("Paint", "mspaint.exe", ["mspaint.exe"], []),
    "explorador de arquivos": ("Explorador de Arquivos", "explorer.exe", [], []),
    "explorador": ("Explorador de Arquivos", "explorer.exe", [], []),
    "windows explorer": ("Explorador de Arquivos", "explorer.exe", [], []),
    "gerenciador de tarefas": ("Gerenciador de Tarefas", "taskmgr.exe", ["taskmgr.exe"], []),
    "painel de controle": ("Painel de Controle", "control.exe", [], []),
    "configuracoes": ("Configurações", "ms-settings:", ["systemsettings.exe"], []),
    "configuracoes do windows": ("Configurações", "ms-settings:", ["systemsettings.exe"], []),
    "prompt de comando": ("Prompt de Comando", "cmd.exe", ["cmd.exe"], []),
    "cmd": ("Prompt de Comando", "cmd.exe", ["cmd.exe"], []),
    "acrobat": ("Acrobat", None, ["acrobat.exe", "acrord32.exe"], ["acrobat"]),
    "adobe": ("Acrobat", None, ["acrobat.exe", "acrord32.exe"], ["acrobat"]),
}
# atalhos do menu Iniciar que não são o programa em si
RUIDO = re.compile(r"\b(desinstal\w*|uninstall\w*|remover|leia ?me|readme|help|ajuda|manual|documenta\w*|site|website|"
                   r"release|notas|licen\w*|license|reparar|repair|configura\w* de|settings|administrator|administrador|"
                   r"update|atualiza\w*|edrawings|composer|visualize|electrical|pdm|toolbox|task scheduler|rx|inspection|"
                   r"plastics|cam|manage|copy|sldim|explorer|utilit\w*|batch|migra\w*|viewer|launcher|reset|"
                   r"recover\w*|monitor|uninst)\b")
NUNCA_FECHAR = ("mantiqueira", "explorer.exe", "python.exe", "pythonw.exe", "llama-server.exe")

_cache = {"t": 0, "atalhos": {}}
_lock = threading.Lock()
_ultimo_alvo = {"hwnd": None}


def _norm(t):
    t = textutil.sem_acento((t or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _base(nome):
    """'SOLIDWORKS 2025 SP1.2 (x64)' → 'solidworks'."""
    t = _norm(nome)
    t = re.sub(r"\b(x64|x86|64 bit|32 bit|64bits|32bits|sp\d*|\d+(\s\d+)*|v\d+\w*|edition|premium|professional|"
               r"standard|pro|microsoft|office|classic|desktop|app)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _pastas_menu():
    pd = os.environ.get("ProgramData", r"C:\ProgramData")
    ad = os.environ.get("APPDATA", "")
    up = os.environ.get("USERPROFILE", "")
    pub = os.environ.get("PUBLIC", r"C:\Users\Public")
    return [os.path.join(pd, r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(ad, r"Microsoft\Windows\Start Menu\Programs") if ad else "",
            os.path.join(up, "Desktop") if up else "", os.path.join(up, "OneDrive", "Desktop") if up else "",
            os.path.join(up, "Área de Trabalho") if up else "", os.path.join(pub, "Desktop")]


def atalhos(forcar=False):
    """{nome do atalho: caminho} do menu Iniciar e da área de trabalho (atualiza a cada 10 minutos)."""
    with _lock:
        if not forcar and time.time() - _cache["t"] < 600 and _cache["atalhos"]:
            return _cache["atalhos"]
    out = {}
    for pasta in _pastas_menu():
        if not pasta or not os.path.isdir(pasta):
            continue
        for raiz, _dirs, arqs in os.walk(pasta):
            if raiz.count(os.sep) - pasta.count(os.sep) > 3:
                continue
            for a in arqs:
                nome, ext = os.path.splitext(a)
                if ext.lower() in (".lnk", ".url", ".appref-ms") and nome not in out:
                    out[nome] = os.path.join(raiz, a)
    with _lock:
        _cache.update(t=time.time(), atalhos=out)
    return out


def _achar_atalho(palavras, falado):
    """Melhor atalho para o programa: nome-base igual ao falado; senão contém as palavras e não é ruído."""
    cands = []
    for nome, caminho in atalhos().items():
        n, b = _norm(nome), _base(nome)
        if not b:
            continue
        if b == falado or (palavras and all(re.search(r"\b" + re.escape(p) + r"\b", n) for p in palavras)):
            if RUIDO.search(n) and b != falado:
                continue
            nota = (0 if b == falado else 1, len(n), nome)
            cands.append((nota, caminho, nome))
    if not cands:
        return None, None
    cands.sort()
    # várias versões instaladas (SolidWorks 2024 e 2025): a mais nova
    melhor = cands[0]
    mesmos = [c for c in cands if c[0][0] == melhor[0][0] and _base(c[2]) == _base(melhor[2])]
    if len(mesmos) > 1:
        def ano(c):
            m = re.findall(r"\b(20\d\d)\b", c[2])
            return int(m[-1]) if m else 0
        melhor = max(mesmos, key=ano)
    return melhor[1], melhor[2]


def resolver(texto, aceitar_qualquer=False):
    """Do que ele falou ('o solidworks', 'a calculadora') devolve {nome, abrir, procs, palavras} ou None."""
    t = _norm(texto)
    t = re.sub(r"^(o|a|os|as|um|uma|no|na|pro|pra|para o|para a|ao)\s+", "", t)
    t = re.sub(r"\b(programa|aplicativo|app|software|por favor|pra mim|para mim|mantiqueira|agora|ai|aberto|aberta)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^(o|a|do|da|de)\s+", "", t)
    if not t or len(t) < 2:
        return None
    if t in CONHECIDOS:
        nome, exe, procs, palavras = CONHECIDOS[t]
        lnk, nome_lnk = _achar_atalho(palavras, t) if palavras else (None, None)
        return {"nome": nome, "falado": t, "abrir": lnk or exe, "procs": procs, "palavras": palavras or t.split()}
    # qualquer programa instalado cujo atalho tenha exatamente esse nome (ou, dizendo "programa", que contenha)
    lnk, nome_lnk = _achar_atalho(t.split() if aceitar_qualquer else [], t)
    if lnk:
        return {"nome": nome_lnk, "falado": t, "abrir": lnk, "procs": [], "palavras": t.split()}
    return None


# ---------------------------------------------------------------------- janelas
def _janelas():
    from . import leitor
    return [(h, p, t) for h, p, t in leitor.janelas_abertas() if not t.startswith("Mantiqueira")]


def janelas_do(prog):
    """Janelas abertas do programa (pelo processo ou pelo título)."""
    procs = [x.lower() for x in prog.get("procs") or []]
    out = []
    for hwnd, proc, titulo in _janelas():
        pl = (proc or "").lower()
        if procs and pl in procs:
            out.append((hwnd, proc, titulo))
        elif not procs:
            alvo = " ".join(prog.get("palavras") or [])
            if alvo and (alvo in _norm(titulo) or alvo.replace(" ", "") in pl.replace(".exe", "")):
                out.append((hwnd, proc, titulo))
    return out


def _frente(hwnd):
    u = ctypes.windll.user32
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)                 # SW_RESTORE
    u.keybd_event(0x12, 0, 0, 0)              # ALT: libera o Windows a trocar a janela da frente
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(hwnd)
    u.BringWindowToTop(hwnd)
    _ultimo_alvo["hwnd"] = hwnd


def _abrir_alvo(alvo):
    if "|" in alvo:                           # navegador: o primeiro que existir
        for a in alvo.split("|"):
            if _shell(a):
                return True
        return False
    return _shell(alvo)


def _shell(alvo):
    r = ctypes.windll.shell32.ShellExecuteW(None, "open", alvo, None, None, 1)
    return r > 32


def abrir(prog):
    """Traz para frente se já estiver aberto; senão abre. Devolve 'frente', 'aberto' ou None."""
    if prog.get("abrir") != "explorer.exe":
        js = janelas_do(prog)
        if js:
            _frente(js[0][0])
            return "frente"
    if not prog.get("abrir"):
        return None
    return "aberto" if _abrir_alvo(prog["abrir"]) else None


def focar(prog):
    js = janelas_do(prog)
    if not js:
        return False
    _frente(js[0][0])
    return True


def minimizar(prog):
    js = janelas_do(prog)
    for hwnd, _, _ in js:
        ctypes.windll.user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE
    return len(js)


def fechar(prog):
    """Igual a clicar no X: o programa pergunta se quer salvar. Nunca força."""
    js = janelas_do(prog)
    n = 0
    for hwnd, proc, titulo in js:
        if (proc or "").lower() in NUNCA_FECHAR:
            continue
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
        n += 1
    return n


def janela_alvo():
    """A janela em que ele está trabalhando (se a da frente for o próprio Mantiqueira, a de trás dela)."""
    u = ctypes.windll.user32
    fg = u.GetForegroundWindow()
    n = u.GetWindowTextLengthW(fg)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(fg, b, n + 1)
    if fg and not b.value.startswith("Mantiqueira") and b.value not in ("", "Program Manager"):
        return fg
    js = _janelas()
    return js[0][0] if js else None


def _preparar_alvo():
    h = janela_alvo()
    if h and h != ctypes.windll.user32.GetForegroundWindow():
        _frente(h)
        time.sleep(0.35)
    return h


def titulo_de(hwnd):
    u = ctypes.windll.user32
    n = u.GetWindowTextLengthW(hwnd)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(hwnd, b, n + 1)
    return b.value


def fechar_janela_atual():
    h = janela_alvo()
    if not h:
        return None
    t = titulo_de(h)
    ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)
    return t


def minimizar_tudo():
    import keyboard
    keyboard.send("windows+d")


def digitar(texto):
    import keyboard
    h = _preparar_alvo()
    keyboard.write(texto, delay=0.01)
    return titulo_de(h) if h else ""


TECLAS = {"control": "ctrl", "contra": "ctrl", "controle": "ctrl", "ctrl": "ctrl", "shift": "shift", "alt": "alt",
          "windows": "windows", "win": "windows", "enter": "enter", "entra": "enter", "esc": "esc", "escape": "esc",
          "tab": "tab", "espaco": "space", "barra de espaco": "space", "apagar": "backspace", "backspace": "backspace",
          "delete": "delete", "del": "delete", "home": "home", "end": "end", "page up": "page up",
          "page down": "page down", "seta para cima": "up", "seta pra cima": "up", "seta cima": "up",
          "seta para baixo": "down", "seta pra baixo": "down", "seta baixo": "down",
          "seta para esquerda": "left", "seta pra esquerda": "left", "seta esquerda": "left",
          "seta para direita": "right", "seta pra direita": "right", "seta direita": "right",
          "print screen": "print screen", "mais": None, "e": None}


def combinacao(texto):
    """'control s' / 'ctrl + shift + s' / 'alt f4' → 'ctrl+s' etc. None se não entender."""
    t = _norm(texto.replace("+", " "))
    t = re.sub(r"\b(a tecla|as teclas|tecla|teclas|o|a|botao)\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    partes = []
    while t:
        for k in sorted(TECLAS, key=len, reverse=True):
            if t == k or t.startswith(k + " "):
                if TECLAS[k]:
                    partes.append(TECLAS[k])
                t = t[len(k):].strip()
                break
        else:
            m = re.match(r"(f(?:1[0-2]|[1-9]))\b\s*", t)
            if m:
                partes.append(m.group(1))
                t = t[m.end():]
                continue
            m = re.match(r"([a-z0-9])\b\s*", t)
            if m:
                partes.append(m.group(1))
                t = t[m.end():]
                continue
            return None
    if not partes or len(partes) > 4:
        return None
    return "+".join(partes)


def apertar(combo):
    import keyboard
    h = _preparar_alvo()
    keyboard.send(combo)
    return titulo_de(h) if h else ""


# ---------------------------------------------------------------------- volume, bloqueio, energia, print
VK_MUTE, VK_DOWN, VK_UP = 0xAD, 0xAE, 0xAF


def _tecla(vk, vezes=1):
    u = ctypes.windll.user32
    for _ in range(vezes):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


def volume(acao, valor=None):
    """acao: 'mais', 'menos', 'mudo', 'definir' (valor 0-100). Cada toque do Windows = 2%."""
    if acao == "mais":
        _tecla(VK_UP, 5)
    elif acao == "menos":
        _tecla(VK_DOWN, 5)
    elif acao == "mudo":
        _tecla(VK_MUTE)
    elif acao == "definir":
        _tecla(VK_DOWN, 50)
        _tecla(VK_UP, int(round(max(0, min(100, valor)) / 2)))


def bloquear():
    ctypes.windll.user32.LockWorkStation()


def energia(acao):
    """'desligar' / 'reiniciar' em 30 s (dá para cancelar); 'cancelar' cancela."""
    args = {"desligar": ["shutdown", "/s", "/t", "30"], "reiniciar": ["shutdown", "/r", "/t", "30"],
            "cancelar": ["shutdown", "/a"]}[acao]
    r = subprocess.run(args, capture_output=True, creationflags=SEM_JANELA)
    return r.returncode == 0


def print_tela():
    import shutil
    from . import tela
    tmp = tela.capturar()
    pasta = os.path.join(os.path.expanduser("~"), "Pictures", "Mantiqueira")
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(pasta, time.strftime("Print %Y-%m-%d %H-%M-%S.png"))
    shutil.copyfile(str(tmp), arq)
    return arq


def abertos():
    """Nomes dos programas com janela aberta (sem repetir)."""
    vistos, out = set(), []
    for _h, proc, titulo in _janelas():
        nome = textutil.nome_app(proc)
        if nome not in vistos:
            vistos.add(nome)
            out.append(nome)
    return out
