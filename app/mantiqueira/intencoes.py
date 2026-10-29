"""Pedidos tratados direto pelo programa (sem a IA inventar): procurar e abrir arquivos, memória,
curiosidades, frases, ler janelas e entrar nos sistemas da empresa.
Cada função devolve o texto a falar, ou None se o pedido não for daquele tipo."""
import os
import re
import time
import datetime as dt
import logging
import subprocess
import threading
from . import textutil
from .indice import descrever, ORIGEM_NOME

log = logging.getLogger("intencoes")

RX_BUSCA = re.compile(r"\b(procur\w*|pesquis(a|e|ar)\b|localiz\w*|encontr(a|e|ar)\b|ach(a|e|ar) (pra mim|o|a|os|as|um|uma|meu|minha)\b|"
                      r"onde (esta|estao|fica|ficam|ta|tao|guardei|salvei)|cade)\b")
# "o pdf está no computador X", "a planilha fica na rede", "tá no file projetos"
RX_BUSCA_LUGAR = re.compile(r"\b(esta|ta|fica|ficou|salvei|guardei|tem|tenho|existe)\s+(um |uma |o |a )?(arquivo |pdf |planilha )?"
                            r"(no|na|em|dentro do|dentro da)\s+(computador|pc|rede|pendrive|pen drive|file|servidor|pasta|disco|"
                            r"area de trabalho|desktop|documentos|downloads|[a-z]\b)")
RX_TIPO_SOLTO = re.compile(r"\b(pdfs?|planilhas?|montagem|montagens|dxf|dwg|arquivo|desenho|pasta)\b")
# pronomes: "abre ele", "abre esse", "abre o arquivo"
RX_PRONOME = re.compile(r"\b(ele|ela|esse|essa|este|esta|isso|aquilo|o arquivo|a pasta dele|la|entao|agora|ai|logo|mesmo)\b")
RX_LIXO = re.compile(r"\b(mantiqueira|procur\w*|pesquis\w*|localiz\w*|encontr\w*|ach[ae]r?|pra mim|para mim|por favor|onde|esta|estao|"
                     r"fica|ficam|ta|tao|guardei|salvei|cade|no computador|no pc|na rede|no pendrive|em tudo|arquivo|arquivos|"
                     r"pasta|o|a|os|as|um|uma|de|do|da|dos|das|me|meu|minha|que|eu|e|ai|aqui)\b")
ORDINAIS = {"primeiro": 0, "primeira": 0, "1": 0, "segundo": 1, "segunda": 1, "2": 1, "terceiro": 2, "terceira": 2, "3": 2,
            "quarto": 3, "quarta": 3, "4": 3, "quinto": 4, "quinta": 4, "5": 4, "ultimo": -1, "ultima": -1}
# palavras que só servem para parar/cancelar (a frase inteira tem que ser feita delas)
PARAR_NUCLEO = {"nao", "para", "pare", "parar", "cancela", "cancele", "cancelar", "chega", "deixa", "silencio", "quieto",
                "esquece", "stop"}
PARAR_RESTO = {"quero", "precisa", "pra", "la", "isso", "nada", "obrigado", "obrigada", "mantiqueira", "ok", "mais", "agora",
               "por", "favor", "de", "falar", "senhor", "tudo", "bem", "e", "o", "a", "ja", "pode", "nao"}
RX_ABRIR = re.compile(r"\b(abre|abra|abrir|abrindo|abri)\b")
# tipo de arquivo citado → extensões aceitas
TIPOS = [
    (r"\bpdfs?\b", [".pdf"]),
    (r"\b(planilhas?|excel|xlsx?)\b", [".xlsx", ".xls", ".xlsm", ".csv"]),
    (r"\b(word|docx?)\b", [".docx", ".doc"]),
    (r"\bdxf\b", [".dxf"]),
    (r"\bdwg\b|\bautocad\b", [".dwg"]),
    (r"\bmontage(m|ns)\b", [".sldasm"]),
    (r"\b(detalhamento|desenho do solid\w*)\b", [".slddrw"]),
    (r"\b(solid\s*works?|solid)\b", [".sldprt", ".sldasm", ".slddrw"]),
    (r"\bpeca\b", [".sldprt"]),
    (r"\b(sketchup|skp)\b", [".skp"]),
    (r"\b(apresentacao|power\s*point|pptx?)\b", [".pptx", ".ppt"]),
    (r"\b(foto|imagem|jpg|png)\b", [".jpg", ".jpeg", ".png"]),
]
NOME_TIPO = {".pdf": "PDF", ".xlsx": "planilha", ".docx": "documento do Word", ".dxf": "DXF", ".dwg": "DWG",
             ".sldasm": "montagem", ".slddrw": "desenho do SolidWorks", ".sldprt": "peça", ".skp": "SketchUp",
             ".pptx": "apresentação", ".jpg": "imagem"}

APPS_FALADOS = {"cypcut": "cypcut", "cyp cut": "cypcut", "aspire": "aspire", "chrome": "chrome", "navegador": "chrome",
                "edge": "edge", "pdf": "acrobat", "acrobat": "acrobat", "autocad": "autocad", "sketchup": "sketchup",
                "3ds": "3ds", "max": "3dsmax", "outlook": "outlook", "whatsapp": "whatsapp", "excel": "excel",
                "word": "word", "explorador": "explorer", "teams": "teams", "nest": "nest", "gaipo": "gaipo"}


NUM_FALADO = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "dez": 10, "quinze": 15,
              "vinte": 20, "trinta": 30, "quarenta": 40, "quarenta e cinco": 45, "meia": 0.5}


def _numero(t):
    t = (t or "").strip()
    if not t:
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return NUM_FALADO.get(t)


class Intencoes:
    def __init__(self, nucleo):
        self.n = nucleo
        self.resultados = []        # última busca
        self.consulta = ""
        self.quando_busca = 0
        self.ultimo_caminho = None  # último arquivo/pasta aberto ou achado (para "chama esse de ...")
        self.apelido_pendente = None
        db = nucleo.db
        db.x("CREATE TABLE IF NOT EXISTS apelidos(apelido TEXT PRIMARY KEY, caminho TEXT, criado TEXT)")

    def _trat(self):
        return self.n.cfg["tratamento"]

    # ------------------------------------------------------------------ roteador
    def tratar(self, pergunta, historico):
        p = textutil.sem_acento(pergunta.lower()).strip(" ?!.")
        for f in (self.parar, self.achou, self.repetir, self.sons, self.voz_ajuste, self.silencio, self.apelidos, self.abrir_resultado,
                  self.abertos_hoje, self.mudou_na_pasta, self.memoria, self.frases, self.sistema_abrir, self.sistema_consulta,
                  self.abrir_pedido, self.buscar, self.ranking, self.ler_janela):
            try:
                r = f(p, pergunta)
            except Exception:
                log.exception("intenção %s", f.__name__)
                r = None
            if r:
                return r
        return None

    # ------------------------------------------------------------------ parar / não / cancela
    def parar(self, p, original):
        palavras = re.findall(r"[a-z]+", p)
        if not palavras or len(palavras) > 6:
            return None
        if not any(w in PARAR_NUCLEO for w in palavras) or not all(w in PARAR_NUCLEO or w in PARAR_RESTO for w in palavras):
            return None
        if re.search(r"\besquece (que|o que|de|do|da)\b", p):
            return None                                     # "esquece que..." é pedido de memória
        self.n.parar_fala()
        self.resultados = []
        c = getattr(self.n, "cerebro", None)
        if c:
            c.lembrete_pendente = None
        return f"Ok, {self._trat()}."

    # ------------------------------------------------------------------ "achou?"
    def achou(self, p, original):
        if not re.fullmatch(r"(e (ai|entao) )?(achou|encontrou|conseguiu|e ai|deu certo|e entao|cade|ja achou|achou ai|"
                            r"achou o arquivo|encontrou o arquivo|achou ele|achou ou nao)( ele| o arquivo| ai)?( mantiqueira)?", p):
            return None
        b = getattr(self, "ultima_busca", None)
        if not b or time.time() - self.quando_busca > 900:
            return (f"Ainda não procurei nada, {self._trat()}. Diga, por exemplo: procura no computador o PDF da mesa luna "
                    f"oval, e eu já respondo se achei.")
        if self.resultados:
            nomes = "; ".join(f"{i + 1}, {descrever(r)}" for i, r in enumerate(self.resultados[:4]))
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(self.resultados[:8]))
            return f"Sim. Encontrei: {nomes}. Quer que eu abra? Diga o número."
        return f"Não achei \"{b['consulta']}\"{b['lugar']}, {self._trat()}."

    # ------------------------------------------------------------------ repete
    def repetir(self, p, original):
        if not re.fullmatch(r"(mantiqueira )?(repete|repita|repetir|fala de novo|fale de novo|pode repetir|repete por favor|"
                            r"o que (voce|vc) (disse|falou)|nao entendi|hein)( isso| de novo| por favor| ai)*", p):
            return None
        u = getattr(self.n, "ultima_fala", "")
        return u or f"Ainda não falei nada, {self._trat()}."

    # ------------------------------------------------------------------ sons
    def sons(self, p, original):
        m = re.search(r"\b(desliga|desligar|desative|desativa|tira|tirar|sem|corta|remove|para de tocar|nao quero)\b.*\b(bip|bipe|bips|som|sons|sinal|barulho|toque|campainha|apito)\b", p)
        liga = re.search(r"\b(liga|ligar|ativa|ativar|volta|voltar|coloca|quero)\b.*\b(bip|bipe|bips|som|sons|sinal|barulho|toque|campainha|apito)\b", p)
        if not m and not liga:
            return None
        if re.search(r"\b(fala|voz|volume)\b", p) and not re.search(r"\b(bip|bipe|sinal|toque|campainha|apito)\b", p):
            return None
        valor = not bool(m)
        if re.search(r"\b(bip|bipe|bips|apito)\b", p) and not re.search(r"\b(lembrete|aviso|notifica)", p):
            chaves, txt = ["som_bip"], "o bip de quando me chama"
        elif re.search(r"\b(lembrete|aviso|notifica\w*|sinal|toque|campainha)\b", p):
            chaves, txt = ["som_lembrete"], "o sinal antes dos avisos"
        else:
            chaves, txt = ["som_bip", "som_lembrete"], "o bip e o sinal dos avisos"
        self.n.cfg.atualizar({k: valor for k in chaves})
        if valor:
            return f"Pronto, {self._trat()}. Liguei {txt}."
        return f"Pronto, {self._trat()}. Desliguei {txt}; agora eu só falo."

    # ------------------------------------------------------------------ volume e velocidade
    def voz_ajuste(self, p, original):
        cfg = self.n.cfg
        vol, vel = float(cfg["voz_volume"] or 1.0), float(cfg["voz_velocidade"] or 1.0)
        if re.search(r"\b(fala|fale|falar|voz)\b.*\bmais (baixo|baixinho)\b|\b(abaixa|abaixe|diminui|diminua)\b.*\b(volume|voz|som)\b", p):
            vol, txt = max(0.15, round(vol * 0.7, 2)), "Falo mais baixo agora"
        elif re.search(r"\b(fala|fale|falar|voz)\b.*\bmais alto\b|\b(aumenta|aumente|sobe|suba)\b.*\b(volume|voz|som)\b", p):
            vol, txt = min(1.8, round(vol * 1.35, 2)), "Falo mais alto agora"
        elif re.search(r"\b(fala|fale|falar)\b.*\bmais (devagar|lento|calmo)\b", p):
            vel, txt = max(0.75, round(vel - 0.1, 2)), "Falo mais devagar agora"
        elif re.search(r"\b(fala|fale|falar)\b.*\bmais (rapido|depressa|ligeiro)\b", p):
            vel, txt = min(1.35, round(vel + 0.1, 2)), "Falo mais rápido agora"
        elif re.search(r"\b(volume|voz|velocidade)\b.*\bnormal\b|\bfala normal\b", p):
            vol, vel, txt = 1.0, 1.0, "Voltei ao volume e à velocidade normais"
        else:
            return None
        cfg.atualizar({"voz_volume": vol, "voz_velocidade": vel})
        return f"{txt}, {self._trat()}."

    # ------------------------------------------------------------------ silêncio
    def silencio(self, p, original):
        n = self.n
        if re.search(r"\b(sai|saia|sair|tira|desliga)\b.*\b(silencio|silencioso|modo silencioso)\b|"
                     r"^(pode falar|pode voltar a falar|volta a falar|pode falar de novo)$", p):
            n.cfg.atualizar({"silencio_ate": 0})
            n.silencio_comeca = 0
            threading.Thread(target=lambda: (time.sleep(6), n.liberar_silenciados()), daemon=True).start()
            return f"Voltei a falar, {self._trat()}."
        if not re.search(r"\b(modo silencioso|fica em silencio|fique em silencio|fica quieto|fique quieto|silencio|"
                         r"nao fala ate|nao fale ate|nao me interrompe|estou em reuniao|to em reuniao|vou entrar em reuniao)\b", p):
            return None
        if re.search(r"\b(o que|como|quando)\b.*\bsilencio\b", p) and "modo silencioso" not in p:
            return None
        agora = time.time()
        fim = None
        m = re.search(r"\b(?:por|durante|uns|umas)\s+(?:mais\s+)?([\d,\.]+|\w+(?: e \w+)?)\s*(min|minuto|minutos|h|hora|horas)\b", p)
        if m and _numero(m.group(1)) is not None:
            qtd = _numero(m.group(1))
            fim = agora + qtd * (3600 if m.group(2).startswith("h") else 60)
        m2 = re.search(r"\bate (as )?(\d{1,2})(?:[:h ](\d{2}))?\b", p)
        if not fim and m2:
            alvo = dt.datetime.now().replace(hour=int(m2.group(2)) % 24, minute=int(m2.group(3) or 0), second=0, microsecond=0)
            if alvo <= dt.datetime.now():
                alvo += dt.timedelta(days=1)
            fim = alvo.timestamp()
        if not fim:
            fim = agora + 3600
        n.cfg.atualizar({"silencio_ate": fim})
        n.silencio_comeca = agora + 6               # dá tempo de confirmar antes de calar
        hora = time.strftime("%H:%M", time.localtime(fim))
        return (f"Certo, {self._trat()}. Fico em silêncio até as {hora}: os avisos aparecem só na tela e eu conto "
                f"depois. Para eu voltar antes, é só dizer \"pode falar\".")

    # ------------------------------------------------------------------ apelidos de arquivos e pastas
    def _apelidos(self):
        return self.n.db.q("SELECT * FROM apelidos ORDER BY apelido")

    def _salvar_apelido(self, apelido, caminho):
        from .db import s as fmt
        self.n.db.x("INSERT OR REPLACE INTO apelidos(apelido, caminho, criado) VALUES(?,?,?)",
                    (textutil.sem_acento(apelido.lower()).strip(), caminho, fmt(dt.datetime.now())))

    def _apelido_na_frase(self, p):
        melhor = None
        for a in self._apelidos():
            if re.search(r"\b" + re.escape(a["apelido"]) + r"\b", p):
                if not melhor or len(a["apelido"]) > len(melhor["apelido"]):
                    melhor = a
        return melhor

    def apelidos(self, p, original):
        m = re.search(r"\bquando eu (falar|disser|pedir|digitar|mandar abrir)\s+(?:o |a )?[\"']?(.+?)[\"']?\s*,?\s+"
                      r"(?:voce |vc )?(abre|abra|abrir|e pra abrir|e para abrir|quero dizer|significa)\s+(?:o |a |os |as )?(.+)$", p)
        if m:
            ap, alvo = m.group(2).strip(" ,"), m.group(4).strip(" .")
            if re.fullmatch(r"[a-z]:\\.*", original.split()[-1].lower()) or ":\\" in original:
                caminho = original[original.find(":\\") - 1:].strip(" .\"'")
                if os.path.exists(caminho):
                    self._salvar_apelido(ap, caminho)
                    return f"Combinado. Quando o {self._trat()} disser \"{ap}\", eu abro {caminho}."
            ix = self.n.indice
            onde, _, resto = self._onde(alvo)
            exts, resto = self._tipo(resto)
            consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
            pasta = bool(re.search(r"\bpasta\b", alvo))
            ex, par = ix.buscar(consulta, onde, limite=6, exts=exts) if ix and consulta else ([], [])
            if pasta:
                ex = [r for r in ex if r["eh_pasta"]] or ex
            if len(ex) == 1:
                self._salvar_apelido(ap, ex[0]["caminho"])
                self.n.detalhe_texto = ex[0]["caminho"]
                return f"Combinado. Quando o {self._trat()} disser \"{ap}\", eu abro {ex[0]['nome']}."
            lista = ex or par
            if not lista:
                return f"Não encontrei \"{consulta}\" para guardar como \"{ap}\", {self._trat()}. Nada foi guardado."
            self.resultados, self.consulta, self.quando_busca, self.apelido_pendente = lista, consulta, time.time(), ap
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(lista[:8]))
            nomes = "; ".join(f"{i + 1}, {descrever(r)}" for i, r in enumerate(lista[:4]))
            return f"Achei mais de um: {nomes}. Qual deles fica com o nome \"{ap}\"?"
        m = re.search(r"\b(chama|chame|guarda|guarde|grava|grave|salva|salve)\s+(esse|essa|este|esta|isso|ele|ela)"
                      r"(?: arquivo| pasta)?\s+(como|de)\s+(.+)$", p)
        if m:
            ap = m.group(4).strip(" .\"'")
            if not self.ultimo_caminho:
                return f"Ainda não sei de qual arquivo o {self._trat()} está falando. Peça para eu procurar ou abrir primeiro."
            self._salvar_apelido(ap, self.ultimo_caminho)
            return f"Combinado. Quando o {self._trat()} disser \"{ap}\", eu abro {os.path.basename(self.ultimo_caminho)}."
        m = re.search(r"\b(apaga|apague|esquece|esqueca|tira|remove)\s+o apelido\s+(.+)$", p)
        if m:
            ap = textutil.sem_acento(m.group(2).strip(" .\"'"))
            if not self.n.db.q("SELECT 1 FROM apelidos WHERE apelido=?", (ap,)):
                return f"Não achei o apelido \"{ap}\", {self._trat()}."
            self.n.db.x("DELETE FROM apelidos WHERE apelido=?", (ap,))
            return f"Pronto, apaguei o apelido \"{ap}\"."
        if re.search(r"\b(quais|meus|lista|mostra)\b.*\bapelidos\b", p):
            lista = self._apelidos()
            if not lista:
                return (f"Ainda não há apelidos, {self._trat()}. Diga, por exemplo: quando eu falar pasta da Brisa, "
                        f"abre a pasta Poltrona Brisa no File Projetos.")
            self.n.detalhe_texto = "\n".join(f"{a['apelido']} → {a['caminho']}" for a in lista)
            return ("Tenho um apelido: " if len(lista) == 1 else f"Tenho {len(lista)} apelidos: ") + "; ".join(a["apelido"] for a in lista[:10]) + ". A lista está na tela."
        return None

    # ------------------------------------------------------------------ o que eu abri hoje
    def abertos_hoje(self, p, original):
        if not re.search(r"\b(o que|quais|que arquivos?|quais arquivos)\b.*\b(abri|usei|mexi|trabalhei|editei)\b.*\b(hoje|ontem)\b", p):
            return None
        if not self.n.olhos:
            return f"O registro de atividades está desligado, {self._trat()}."
        dia = dt.date.today() - dt.timedelta(days=1 if "ontem" in p else 0)
        ini = dt.datetime.combine(dia, dt.time())
        vistos = {}
        for b in self.n.olhos.blocos(ini, ini + dt.timedelta(days=1), juntar_min=10):
            if not b["arquivo"] or b["app"] == "Privado":
                continue
            v = vistos.setdefault(b["arquivo"], {"app": b["app"], "inicio": b["inicio"], "seg": 0})
            v["seg"] += b["seg"]
        quando = "ontem" if "ontem" in p else "hoje"
        if not vistos:
            return f"Não registrei nenhum arquivo aberto {quando}, {self._trat()}."
        lista = sorted(vistos.items(), key=lambda x: x[1]["inicio"])
        self.n.detalhe_texto = "\n".join(f"{v['inicio']:%H:%M}  {v['app']} · {a}  ({textutil.duracao_texto(v['seg'])})"
                                          for a, v in lista)
        principais = sorted(lista, key=lambda x: -x[1]["seg"])[:4]
        txt = "; ".join(f"{a} por {textutil.duracao_texto(v['seg'])}" for a, v in principais)
        return (f"{quando.capitalize()} o {self._trat()} abriu {len(lista)} arquivos. Os que mais usou: {txt}. "
                f"A lista completa, com os horários, está na tela.")

    # ------------------------------------------------------------------ o que mudou na pasta X
    def mudou_na_pasta(self, p, original):
        m = re.search(r"\b(o que|quais arquivos|que arquivos)\b.*\b(mudou|mudaram|mexeram|alteraram|alterado|alterados|"
                      r"salvaram|salvos|novo|novos)\b.*\b(na|no|da|do)\s+(pasta\s+)?(.+?)(\s+hoje|\s+ontem)?$", p)
        if not m:
            return None
        alvo = m.group(5).strip()
        ontem = "ontem" in p
        caminho = None
        ap = self._apelido_na_frase(p)
        if ap and os.path.isdir(ap["caminho"]):
            caminho = ap["caminho"]
        ix = self.n.indice
        if not caminho and ix:
            onde, _, resto = self._onde(alvo)
            consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
            ex, par = ix.buscar(consulta, onde, limite=8) if consulta else ([], [])
            pastas = [r for r in ex + par if r["eh_pasta"]]
            if pastas:
                caminho = pastas[0]["caminho"]
        if not caminho or not os.path.isdir(caminho):
            return f"Não encontrei a pasta \"{alvo}\", {self._trat()}."
        dia = dt.date.today() - dt.timedelta(days=1 if ontem else 0)
        ini = dt.datetime.combine(dia, dt.time()).timestamp()
        fim = ini + 86400
        achados, contados = [], 0
        for raiz, dirs, arqs in os.walk(caminho):
            if raiz[len(caminho):].count(os.sep) >= 3:
                dirs[:] = []
            for a in arqs:
                contados += 1
                if contados > 20000:
                    break
                if a.startswith("~$"):
                    continue
                try:
                    mt = os.path.getmtime(os.path.join(raiz, a))
                except OSError:
                    continue
                if ini <= mt < fim:
                    achados.append((mt, os.path.join(raiz, a)))
            if contados > 20000:
                break
        quando = "ontem" if ontem else "hoje"
        nome_pasta = os.path.basename(caminho.rstrip("\\")) or caminho
        if not achados:
            return f"Nada mudou {quando} na pasta {nome_pasta}, {self._trat()}."
        achados.sort(reverse=True)
        self.n.detalhe_texto = "\n".join(f"{time.strftime('%H:%M', time.localtime(t))}  {c}" for t, c in achados[:30])
        nomes = "; ".join(f"{os.path.basename(c)} às {time.strftime('%H:%M', time.localtime(t))}" for t, c in achados[:4])
        if len(achados) == 1:
            return f"{quando.capitalize()} mudou um arquivo na pasta {nome_pasta}: {nomes}."
        return f"{quando.capitalize()} mudaram {len(achados)} arquivos na pasta {nome_pasta}. Os mais recentes: {nomes}."

    # ------------------------------------------------------------------ onde procurar
    def _onde(self, p):
        """(onde, texto do lugar, frase sem o lugar). onde: 'tudo', 'pc', 'rede', 'pendrive' ou 'Z:\\'."""
        ix = self.n.indice
        locais = ix.locais() if ix else []
        for raiz, origem, apel in locais:                  # pelo nome da pasta de rede: "no file projetos", "no aluminas"
            if origem != "rede" or not apel:
                continue
            palavras = [w for w in re.findall(r"[a-z0-9]+", textutil.sem_acento(apel.lower())) if len(w) >= 4 and w != "file"]
            for w in palavras:
                m = re.search(r"\b(no|na|em|do|da|dentro do|dentro da)\s+(?:(?:file|fail|faile|fala|arquivo|pasta|servidor)\s*[-_ ]?\s*)?"
                              + re.escape(w) + r"\b", p)
                if m:
                    return raiz, f" no {apel.replace('_', ' ').replace('-', ' ')}", p[:m.start()] + " " + p[m.end():]
        m = re.search(r"\b(no|na|em) (unidade |disco |drive )?([a-z])\b(?! de)", p)
        if m and m.group(3) in "cdefghijklmnopqrstuvwxyz" and any(r[0].lower().startswith(m.group(3)) for r in locais):
            raiz = m.group(3).upper() + ":\\"
            if raiz == "C:\\":
                return "pc", " no computador", p[:m.start()] + " " + p[m.end():]
            return raiz, f" no {raiz[:2]}", p[:m.start()] + " " + p[m.end():]
        for rx, onde, txt in ((r"\b(na rede|no servidor|nas pastas da rede)\b", "rede", " na rede"),
                              (r"\b(no|neste|nesse) (computador|pc)\b|\bno meu (computador|pc)\b", "pc", " no computador"),
                              (r"\bno pen ?drive\b", "pendrive", " no pendrive")):
            m = re.search(rx, p)
            if m:
                return onde, txt, p[:m.start()] + " " + p[m.end():]
        return "tudo", "", p

    @staticmethod
    def _tipo(p):
        for rx, exts in TIPOS:
            m = re.search(rx, p)
            if m:
                return exts, p[:m.start()] + " " + p[m.end():]
        return None, p

    # ------------------------------------------------------------------ busca de arquivos
    def buscar_forcado(self, pergunta):
        """Usado quando a IA tentou 'procurar' sozinha: faz a busca de verdade com a frase do usuário."""
        p = textutil.sem_acento(pergunta.lower()).strip(" ?!.")
        return self.buscar(p, pergunta, forcar=True)

    def buscar(self, p, original, forcar=False):
        lugar_frase = RX_BUSCA_LUGAR.search(p) and RX_TIPO_SOLTO.search(p) and not RX_ABRIR.search(p)
        if (not RX_BUSCA.search(p) and not lugar_frase and not forcar) or textutil.pede_lembrete(p):
            return None
        ix = self.n.indice
        if not ix:
            return f"Ainda estou preparando o mapa de arquivos, {self._trat()}."
        onde, lugar, resto = self._onde(p)
        exts, resto = self._tipo(resto)
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
        if len(consulta) < 2:
            return f"O que o {self._trat()} quer que eu procure?"
        exatos, parecidos = ix.buscar(consulta, onde, limite=6, exts=exts)
        self.consulta, self.quando_busca = consulta, time.time()
        self.ultima_busca = {"consulta": consulta, "onde": onde, "exts": exts, "lugar": lugar,
                             "achou": len(exatos), "parecidos": len(parecidos)}
        aviso = ""
        if ix.varrendo:
            aviso = f" Ainda estou terminando de mapear {ix.varrendo}, então pode haver mais coisas."
        if exatos:
            if len(exatos) == 1:
                self.ultimo_caminho = exatos[0]["caminho"]
            self.resultados = exatos + parecidos[:3]
            r0 = exatos[0]
            frase = f"Achei: {descrever(r0)}."
            if len(exatos) > 1:
                outros = ", ".join(r["nome"] for r in exatos[1:4])
                frase += f" Também tem {outros}."
            frase += " Quer que eu abra?" + aviso
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(self.resultados[:8]))
            return frase
        if parecidos:
            self.resultados = parecidos
            nomes = "; ".join(r["nome"] for r in parecidos[:4])
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(parecidos[:8]))
            return (f"Não achei exatamente \"{consulta}\"{lugar}, mas encontrei parecidos: {nomes}. "
                    f"É algum desses? Posso abrir o primeiro, o segundo...{aviso}")
        self.resultados = []
        return f"Não encontrei nada parecido com \"{consulta}\"{lugar}, {self._trat()}.{aviso}"

    def abrir_resultado(self, p, original):
        """Resposta a uma lista que acabei de dar: "sim", "abre", "o segundo", "abre a pasta". Uma frase com outro
        nome de arquivo não entra aqui (vira um pedido novo)."""
        if not self.resultados or time.time() - self.quando_busca > 600:
            return None
        if not re.search(r"\b(abr[ea]|abrir|pode abrir|sim|isso|esse|essa|esse mesmo|o primeiro|o segundo|o terceiro|"
                         r"a primeira|a segunda|a pasta|mostra a pasta|onde fica a pasta|primeiro|segundo|terceiro|quarto|quinto|"
                         r"ultimo|1|2|3|4|5)\b", p):
            return None
        sobra = re.sub(r"\b(abr[ea]|abrir|pode|sim|isso|esse|essa|este|esta|mesmo|o|a|os|as|pra|para|mim|me|por|favor|pasta|"
                       r"mostra|onde|fica|dele|dela|ele|ela|entao|agora|ai|la|logo|arquivo|numero|n|mantiqueira|ok|quero|" + "|".join(ORDINAIS) + r")\b", " ", p)
        if len(sobra.split()) > 1:
            return None
        idx = 0
        for palavra, i in ORDINAIS.items():
            if re.search(r"\b" + palavra + r"\b", p):
                idx = i
                break
        try:
            r = self.resultados[idx]
        except IndexError:
            return f"Só achei {len(self.resultados)} resultados, {self._trat()}."
        if self.apelido_pendente:
            ap, self.apelido_pendente = self.apelido_pendente, None
            self._salvar_apelido(ap, r["caminho"])
            self.resultados = []
            return f"Combinado. Quando o {self._trat()} disser \"{ap}\", eu abro {r['nome']}."
        self.ultimo_caminho = r["caminho"]
        self.n.indice.lembrar_escolha(self.consulta, r["caminho"])
        if "pasta" in p:
            subprocess.Popen(["explorer", "/select,", r["caminho"]])
            self.resultados = []
            return f"Abri a pasta de {r['nome']}."
        os.startfile(r["caminho"])
        self.resultados = []
        if self.n.memoria and not r["eh_pasta"]:
            self.n.memoria.adicionar(f"O arquivo {r['nome']} fica em {r['pasta']}")
        return f"Abrindo {r['nome']}."

    # ------------------------------------------------------------------ "abre o pdf da mesa luna"
    def abrir_pedido(self, p, original):
        if not RX_ABRIR.search(p) or textutil.pede_lembrete(p):
            return None
        ap = self._apelido_na_frase(p)
        if ap:
            caminho = ap["caminho"]
            if not os.path.exists(caminho):
                return (f"O apelido \"{ap['apelido']}\" aponta para {caminho}, mas não encontrei mais esse caminho, "
                        f"{self._trat()}. Pode ser que a rede esteja desconectada ou que o arquivo tenha mudado de lugar.")
            os.startfile(caminho)
            self.ultimo_caminho = caminho
            return f"Abrindo {os.path.basename(caminho.rstrip(chr(92))) or caminho}."
        ix = self.n.indice
        onde, lugar, resto = self._onde(p)
        exts, resto = self._tipo(resto)
        resto = RX_ABRIR.sub(" ", resto)
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
        consulta = re.sub(r"\b(o|a|arquivo|pra|para|mim|favor|por)\b", " ", consulta).strip()
        sem_pronome = re.sub(r"\s+", " ", RX_PRONOME.sub(" ", consulta)).strip()
        b = getattr(self, "ultima_busca", None)
        if len(sem_pronome) < 2 and b and time.time() - self.quando_busca < 900:
            # "abre ele": o arquivo da última busca
            consulta = b["consulta"]
            if onde == "tudo":
                onde, lugar = b["onde"], b["lugar"]
            exts = exts or b["exts"]
        else:
            consulta = sem_pronome or consulta
        if len(consulta) < 2:
            return f"Qual arquivo o {self._trat()} quer que eu abra?"
        tipo_txt = (" " + NOME_TIPO.get(exts[0], "")) if exts else ""
        exatos, parecidos = ix.buscar(consulta, onde, limite=6, exts=exts) if ix else ([], [])
        if not exatos and not parecidos and self.n.olhos:
            c = self.n.olhos.recentes.achar(consulta)          # mapa ainda não pronto: tenta os recentes
            if c and (not exts or os.path.splitext(c)[1].lower() in exts):
                os.startfile(c)
                return f"Abrindo {os.path.basename(c)}."
        self.consulta, self.quando_busca = consulta, time.time()
        self.ultima_busca = {"consulta": consulta, "onde": onde, "exts": exts, "lugar": lugar,
                             "achou": len(exatos), "parecidos": len(parecidos)}
        if len(exatos) == 1:
            r = exatos[0]
            if ix:
                ix.lembrar_escolha(consulta, r["caminho"])
            self.ultimo_caminho = r["caminho"]
            os.startfile(r["caminho"])
            self.resultados = []
            return f"Abrindo {r['nome']}."
        if exatos:
            pref = [r for r in exatos if ix and ix.q("SELECT vezes FROM preferidos WHERE consulta=? AND caminho=? AND vezes>=2",
                                                        (consulta, r["caminho"]))]
            if len(pref) == 1:
                os.startfile(pref[0]["caminho"])
                self.resultados = []
                return f"Abrindo {pref[0]['nome']}, o mesmo que o {self._trat()} costuma abrir."
            self.resultados = exatos
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(exatos[:8]))
            nomes = "; ".join(f"{i + 1}, {descrever(r)}" for i, r in enumerate(exatos[:4]))
            return f"Achei {len(exatos)} arquivos{tipo_txt}{lugar} com esse nome: {nomes}. Qual deles eu abro?"
        if parecidos:
            self.resultados = parecidos
            self.n.detalhe_texto = "\n".join(f"{i + 1}. {r['caminho']}" for i, r in enumerate(parecidos[:8]))
            nomes = "; ".join(f"{i + 1}, {r['nome']}" for i, r in enumerate(parecidos[:4]))
            return f"Não achei exatamente esse{tipo_txt}{lugar}. Parecidos: {nomes}. É algum desses?"
        self.resultados = []
        return f"Não encontrei nenhum{tipo_txt or ' arquivo'} \"{consulta}\"{lugar}, {self._trat()}. Não abri nada."

    # ------------------------------------------------------------------ memória
    def memoria(self, p, original):
        m = self.n.memoria
        if not m:
            return None
        if re.search(r"o que (voce )?(sabe|lembra|guardou) (sobre|de) mim|o que voce sabe de mim|o que tem na sua memoria", p):
            fatos = [f["texto"] for f in m.todos()]
            notas = [x["texto"] for x in self.n.db.notas(10)]
            if not fatos and not notas:
                return f"Ainda sei pouco sobre o {self._trat()}. Vou aprendendo conforme a gente conversa."
            self.n.detalhe_texto = "\n".join(["MEMÓRIA:"] + [f"- {f}" for f in fatos] + (["", "ANOTAÇÕES:"] + [f"- {x}" for x in notas] if notas else []))
            resumo = " ".join(fatos[-6:])
            qf = "uma coisa" if len(fatos) == 1 else f"{len(fatos)} coisas"
            qn = "nenhuma anotação" if not notas else ("uma anotação" if len(notas) == 1 else f"{len(notas)} anotações")
            return (f"Guardei {qf} sobre o {self._trat()} e {qn}. {'Algumas delas' if len(fatos) > 1 else 'É esta'}: {resumo} "
                    f"A lista completa está na tela.")
        if re.search(r"\b(esquece|esqueca|esquecer|apaga da (sua )?memoria|tira da (sua )?memoria)\b", p):
            apagados = m.esquecer(p)
            if apagados:
                return f"Pronto, esqueci: {' '.join(apagados)}"
            return f"Não achei isso na minha memória, {self._trat()}."
        return None

    # ------------------------------------------------------------------ curiosidades e frases
    def frases(self, p, original):
        from .frases import tema_da_pergunta
        f = self.n.frases
        if re.search(r"curiosidade|me conta (algo|alguma coisa) (interessante|legal|curios)|fato interessante|coisa interessante", p):
            return f.curiosidade(tema_da_pergunta(p))
        if re.search(r"motiva|frase (boa|bonita|do dia)|me anima|desanimad|preciso de (uma )?(forca|animo)|"
                     r"dia (dificil|pesado|ruim)|estressad", p):
            return f.motivacao()
        if re.search(r"relaxar|distrair|descansar a cabeca|me distrai", p):
            return f"Vamos lá. {f.curiosidade()} E pra fechar: {f.motivacao()}"
        return None

    # ------------------------------------------------------------------ sistemas da empresa
    def sistema_abrir(self, p, original):
        sw = self.n.sistemas
        if not sw:
            return None
        s = sw.qual(p)
        if not s:
            return None
        if re.search(r"\b(login|entrar|logar|fazer login)\b", p):
            sw.abrir_para_login(s)
            return (f"Abri o sistema de {s['nome']} numa janela do navegador. Faça o login; quando a lista aparecer, "
                    f"a janela fecha sozinha.")
        if re.search(r"\b(abr[ea]|abrir|mostra)\b.*\b(sistema|site|pagina|tela)\b|\babre o (sistema|site)\b", p):
            os.startfile(s["url"])
            return f"Abrindo o sistema de {s['nome']} no navegador."
        return None

    def sistema_consulta(self, p, original):
        """Pergunta sobre o sistema da empresa: lê os dados; se não der, explica (sem a IA inventar)."""
        sw = self.n.sistemas
        if not sw:
            return None
        s = sw.qual(p) or sw.citado_sem_nome(original)
        if not s:
            return None
        c = sw.cache.get(s["nome"])
        if not (c and time.time() - c[0] < 180):
            # leitura demora alguns segundos: avisa para ele não ficar sem resposta
            aviso = f"Um instante, {self._trat()}. Estou consultando o sistema de {s['nome']}."
            try:
                self.n.ultima["assistente"] = aviso
                if self.n.voz and not self.n.em_silencio():
                    self.n.voz.falar(aviso)
            except Exception:
                pass
        try:
            d = sw.ler(s)
        except Exception as e:
            log.info("sistema %s indisponível: %s", s["nome"], e)
            return (f"Não consegui ler o sistema de {s['nome']} agora, {self._trat()}. Vá em Configurações, Sistemas da "
                    f"empresa, clique em Entrar, faça o login, espere a lista aparecer e feche a janela. Depois me pergunte de novo.")
        if d.get("login"):
            return (f"O sistema de {s['nome']} está pedindo login, {self._trat()}. Vá em Configurações, Sistemas da empresa, "
                    f"clique em Entrar e faça o login uma vez. Depois me pergunte de novo.")
        if not d.get("linhas"):
            return f"Entrei no sistema de {s['nome']}, mas a lista veio vazia, {self._trat()}."
        try:
            exata = sw.responder(s, d, original)
        except Exception:
            log.exception("resposta exata do sistema")
            exata = None
        if exata:
            return exata                                # resposta tirada direto da tabela, sem a IA
        self.n.contexto_extra = sw.formatar(s, d, original)
        return None                                     # a IA responde usando os dados lidos

    def ranking(self, p, original):
        """'Quem é o melhor/pior projetista?' com o Excel aberto: conta direto da planilha."""
        if not re.search(r"\b(melhor|pior|maior|menor|ranking)\b", p):
            return None
        if not re.search(r"projetista|funcionari|pessoa|quem|equipe|colaborador|planilha|semana|ano|mes|nota|media", p):
            return None
        from . import leitor
        try:
            r = leitor.ranking_planilhas(original)
        except Exception:
            log.exception("ranking da planilha")
            return None
        if not r:
            return None
        texto, detalhe = r
        self.n.detalhe_texto = detalhe
        return texto

    # ------------------------------------------------------------------ ler outra janela
    def ler_janela(self, p, original):
        if not re.search(r"\b(o que (tem|esta|aparece|mostra|diz)|le |ler |leia |resume|resumo)\b", p):
            return None
        alvo = None
        for falado, chave in APPS_FALADOS.items():
            if re.search(r"\b" + re.escape(falado) + r"\b", p):
                alvo = chave
                break
        if not alvo or alvo in ("excel", "word"):
            return None                         # Excel/Word já são lidos direto pelo contexto
        from . import leitor
        titulo, texto = leitor.ler_janela(alvo)
        if titulo is None:
            return f"Não encontrei o {alvo} aberto, {self._trat()}."
        if not texto:
            return f"O {alvo} está minimizado ou não deu para ler a janela. Deixe ele aberto na tela e peça de novo."
        self.n.contexto_extra = f"TEXTO DA JANELA '{titulo}':\n{texto[:4000]}"
        return None                             # a IA responde usando o texto lido
