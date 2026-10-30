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
RX_IMPRIMIR = re.compile(r"\bimprim\w*|\bimpressao\b|\b(gera|gere|gerar|salva|salve|salvar|cria|crie|criar|faz|faca|fazer|"
                         r"exporta|exporte|exportar|tira|tire)\w*\b.{0,40}\bpdfs?\b|\bem pdf\b|\bo pdf d[aeo]s? cnps?\b")
RX_ABRIR = re.compile(r"\b(abre|abra|abrir|abrindo|abri)\b")
# tipo de arquivo citado → extensões aceitas
TIPOS = [
    (r"\b(?:em |no formato )?pdfs?\b", [".pdf"]),
    (r"\b(planilhas?|excel|xlsx?)\b", [".xlsx", ".xls", ".xlsm", ".csv"]),
    (r"\b(word|docx?)\b", [".docx", ".doc"]),
    (r"\bdxf\b", [".dxf"]),
    (r"\bdwg\b|\bautocad\b", [".dwg"]),
    (r"\bmontage(m|ns)\b", [".sldasm"]),
    (r"\b(detalhamento|desenho do solid\w*)\b", [".slddrw"]),
    (r"\bdesenhos?\b", [".slddrw", ".dwg", ".dxf"]),
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
        r = self._tratar(pergunta, historico)
        if getattr(self, "_acao", "abrir") == "imprimir" and r:
            r = re.sub(r"^Abrindo (\d+) arquivos", r"Mandei imprimir \1 arquivos", r)
            r = re.sub(r"^Abrindo ", "Mandei imprimir ", r)
        self._acao = "abrir"
        return r

    def _tratar(self, pergunta, historico):
        p = textutil.sem_acento(pergunta.lower()).strip(" ?!.")
        for f in (self.confirmar_energia, self.parar, self.imprimir_pedido, self.computador, self.peca_solidworks, self.achou, self.repetir, self.sons, self.voz_ajuste, self.silencio, self.apelidos, self.abrir_resultado,
                  self.programa, self.abertos_hoje, self.mudou_na_pasta, self.memoria, self.frases, self.sistema_abrir, self.sistema_consulta,
                  self.conteudo_pasta, self.abrir_pedido, self.buscar, self.ranking, self.ler_janela):
            try:
                r = f(p, pergunta)
            except Exception:
                log.exception("intenção %s", f.__name__)
                r = None
            if r:
                if f != self.peca_solidworks:
                    self._peca_pendente = None
                if f in (self.abrir_pedido, self.buscar, self.conteudo_pasta) and getattr(self, "_acao", "abrir") == "abrir":
                    self._acao_lista, self._impressora_lista = "abrir", None     # lista nova de abrir
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
        self._peca_pendente = None
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
            # 1º "no file projetos" (com "file"); só depois "no projetos" sozinho — "na pasta projetos" é uma PASTA, não a unidade
            for exige in (True, False):
                for w in palavras:
                    pref = r"(?:file|fail|faile|fala|servidor)\s*[-_ ]?\s*" if exige else r"(?<!pasta )"
                    m = re.search(r"\b(no|na|em|do|da|dentro do|dentro da)\s+" + pref + re.escape(w) + r"\b", p)
                    if m and not (not exige and re.search(r"\bpasta\s*$", p[:m.start()])):
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
    def _pastas_citadas(p):
        """'dentro de engenharia na pasta projetos' → (['engenharia', 'projetos'], frase sem essas partes)."""
        dicas = []
        fim = r"(?=\s+(?:na|no|da|do|de|dentro|que|em|e)\b|\s*$)"
        rx = re.compile(r"\b(?:dentro d[aeo]s?|na pasta|no diretorio|da pasta|na subpasta|pasta)\s+(?:pasta\s+)?([a-z0-9][a-z0-9 _\-]*?)" + fim)
        while True:
            m = rx.search(p)
            if not m:
                break
            dicas.append(m.group(1).strip())
            fim_m = m.end()
            p = p[:m.start()] + " " + p[fim_m:]
            # encadeado: "na pasta projetos da engenharia"
            while True:
                m2 = re.match(r"\s*(?:da|do|de|dentro da|dentro do)\s+(?:pasta\s+)?([a-z0-9][a-z0-9 _\-]*?)" + fim, p[m.start():])
                if not m2 or m2.group(1) in ("arquivo", "computador", "rede"):
                    break
                dicas.append(m2.group(1).strip())
                p = p[:m.start()] + " " + p[m.start() + m2.end():]
        p = re.sub(r"\bque (esta|ta|fica|ficam|estao)\b", " ", p)
        return [d for d in dicas if d], p

    @staticmethod
    def _na_pasta(caminho, dicas):
        partes = [textutil.sem_acento(x.lower()).strip() for x in re.split(r"[\\/]", caminho)[:-1]]
        return all(any(d == x or d in x.split() or x.startswith(d) for x in partes) for d in dicas)

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
        dicas, resto = self._pastas_citadas(resto)
        exts, resto = self._tipo(resto)
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
        if len(consulta) < 2:
            return f"O que o {self._trat()} quer que eu procure?"
        exatos, parecidos = ix.buscar(consulta, onde, limite=60 if dicas else 6, exts=exts)
        if dicas:
            exatos = [r for r in exatos if self._na_pasta(r["caminho"], dicas)][:6]
            parecidos = [r for r in parecidos if self._na_pasta(r["caminho"], dicas)][:6]
            lugar = f" dentro de {' / '.join(dicas)}{lugar}"
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
        if RX_IMPRIMIR.search(p):
            return None
        self._acao = getattr(self, "_acao_lista", "abrir")     # lista que veio de "imprime …": "o 2" imprime
        self._impressora_atual = getattr(self, "_impressora_lista", None)
        if not re.search(r"\b(abr[ea]|abrir|pode abrir|sim|isso|esse|essa|esse mesmo|o primeiro|o segundo|o terceiro|"
                         r"a primeira|a segunda|a pasta|mostra a pasta|onde fica a pasta|primeiro|segundo|terceiro|quarto|quinto|"
                         r"ultimo|todos|todas|ambos|ambas|\d{1,2})\b", p):
            return None
        sobra = re.sub(r"\b(abr[ea]|abrir|pode|sim|isso|esse|essa|este|esta|mesmo|o|a|os|as|pra|para|mim|me|por|favor|pasta|"
                       r"mostra|onde|fica|dele|dela|ele|ela|eles|elas|entao|agora|ai|la|logo|arquivo|arquivos|numero|n|mantiqueira|ok|"
                       r"quero|que|voce|vc|todos|todas|tudo|ambos|ambas|dois|duas|tres|e|de|uma|vez|eles|lista|da|do|"
                       r"\d{1,2}|" + "|".join(ORDINAIS) + r")\b", " ", p)
        if len(sobra.split()) > 1:
            return None
        # "abre todos" / "abre os dois" / "abre o 1 e o 3"
        escolhidos = None
        self._idx_unico = None
        if re.search(r"\b(todos|todas|tudo|ambos|ambas)\b", p):
            escolhidos = list(range(len(self.resultados)))
        else:
            mm = re.search(r"\b(?:os|as) (dois|duas|tres) primeir[oa]s\b|\b(?:os|as) (dois|duas|tres)\b", p)
            if mm:
                k = {"dois": 2, "duas": 2, "tres": 3}[mm.group(1) or mm.group(2)]
                escolhidos = list(range(min(k, len(self.resultados))))
            else:
                nums = []
                for m_ in re.finditer(r"\b(" + "|".join(sorted(ORDINAIS, key=len, reverse=True)) + r"|\d{1,2})\b", p):
                    w = m_.group(1)
                    i_ = ORDINAIS.get(w, int(w) - 1 if w.isdigit() else None)
                    if i_ is not None and i_ not in nums:
                        nums.append(i_)
                if len(nums) > 1:
                    escolhidos = nums
                elif len(nums) == 1:
                    self._idx_unico = nums[0]
        if escolhidos is not None:
            lista = []
            for i_ in escolhidos:
                try:
                    lista.append(self.resultados[i_])
                except IndexError:
                    pass
            if not lista:
                return f"Só achei {len(self.resultados)} resultados, {self._trat()}."
            lista = lista[:15]
            for r in lista:
                if "pasta" in p:
                    subprocess.Popen(["explorer", "/select,", r["caminho"]])
                else:
                    self._usar(r["caminho"])
                time.sleep(0.3)
            self.ultimo_caminho = lista[-1]["caminho"]
            self.resultados = []
            extra = " (abri os 15 primeiros)" if len(escolhidos) > 15 else ""
            return f"Abrindo {len(lista)} arquivos{extra}: " + "; ".join(r["nome"] for r in lista) + "."
        idx = getattr(self, "_idx_unico", None)
        self._idx_unico = None
        if idx is None:
            idx = 0
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
        self._usar(r["caminho"])
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
        mp = re.search(r"\b(?:abr[ea]|abrir)\s+(?:a|essa|esta)?\s*pasta\s+(.+)$", p)
        if mp and not (self.resultados and re.fullmatch(r"(a )?pasta( dele| dela| do arquivo)?", mp.group(1).strip())):
            onde, lugar, resto = self._onde(mp.group(1))
            raizes = [r for r, _, _ in (self.n.indice.locais() if self.n.indice else [])]
            raiz = onde if (onde in raizes or re.fullmatch(r"[A-Z]:\\", onde or "")) else ("C:\\" if onde == "pc" else None)
            partes = [re.sub(r"\s+", " ", re.sub(r"\b(pasta|a|o|que|esta|fica|mantiqueira|pra|para|mim)\b", " ", x)).strip()
                      for x in re.split(r"\s+(?:da|do|de|dentro da|dentro do)\s+(?:pasta\s+)?", resto.strip())]
            partes = [x for x in partes if x]
            if partes:
                alvo = self._achar_pasta(partes, raiz, raizes)
                if alvo:
                    os.startfile(alvo)
                    self.ultimo_caminho = alvo
                    return f"Abrindo a pasta {os.path.basename(alvo.rstrip(chr(92)))}."
                return f"Não encontrei a pasta \"{' / '.join(partes)}\"{lugar}, {self._trat()}."
        ix = self.n.indice
        onde, lugar, resto = self._onde(p)
        dicas, resto = self._pastas_citadas(resto)
        exts, resto = self._tipo(resto)
        resto = RX_ABRIR.sub(" ", resto)
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
        consulta = re.sub(r"\b(o|a|arquivo|arquivos|pra|para|mim|favor|por|todos|todas|quero|que|voce|vc)\b", " ", consulta)
        consulta = re.sub(r"\s+", " ", consulta).strip()
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
        todos = bool(re.search(r"\b(todos|todas)\b", p))
        exatos, parecidos = ix.buscar(consulta, onde, limite=60 if (dicas or todos) else 6, exts=exts) if ix else ([], [])
        if dicas:
            exatos = [r for r in exatos if self._na_pasta(r["caminho"], dicas)][:6]
            parecidos = [r for r in parecidos if self._na_pasta(r["caminho"], dicas)][:6]
            lugar = f" dentro de {' / '.join(dicas)}{lugar}"
        if not exatos and not parecidos and self.n.olhos:
            c = self.n.olhos.recentes.achar(consulta)          # mapa ainda não pronto: tenta os recentes
            if c and (not exts or os.path.splitext(c)[1].lower() in exts):
                self._usar(c)
                return f"Abrindo {os.path.basename(c)}."
        self.consulta, self.quando_busca = consulta, time.time()
        self.ultima_busca = {"consulta": consulta, "onde": onde, "exts": exts, "lugar": lugar,
                             "achou": len(exatos), "parecidos": len(parecidos)}
        if re.search(r"\b(todos|todas)\b", p) and exatos:
            # "abre todos os PDFs da espreguiçadeira aura"
            lista = exatos[:15] if len(exatos) <= 15 else exatos[:15]
            for r in lista:
                self._usar(r["caminho"])
                time.sleep(0.3)
            self.resultados = []
            return f"Abrindo {len(lista)} arquivos: " + "; ".join(r["nome"] for r in lista) + "."
        # nome do arquivo igual ao que ele disse (sem "PLANO DE CORTE…" e afins): é esse
        iguais = [r for r in exatos if not r["eh_pasta"] and
                  re.sub(r"\s+", " ", textutil.sem_acento(os.path.splitext(r["nome"])[0].lower())).strip() == consulta]
        if len(iguais) == 1:
            exatos = iguais
        if len(exatos) == 1:
            r = exatos[0]
            if ix:
                ix.lembrar_escolha(consulta, r["caminho"])
            self.ultimo_caminho = r["caminho"]
            self._usar(r["caminho"])
            self.resultados = []
            return f"Abrindo {r['nome']}."
        if exatos:
            pref = [r for r in exatos if ix and ix.q("SELECT vezes FROM preferidos WHERE consulta=? AND caminho=? AND vezes>=2",
                                                        (consulta, r["caminho"]))]
            if len(pref) == 1:
                self._usar(pref[0]["caminho"])
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
        pergunta_sistema = original
        u = getattr(self, "ultimo_cnp", None)
        if not s and u and time.time() - u["t"] < 600 and len(p.split()) <= 9 and \
                not re.search(r"planilha|excel|projetista|semana|arquivo|pdf|pasta|lembr|agenda|abre|procur|solid|tela", p):
            campo_aqui = any(re.search(rx, p) for _, rx in sw.PERGUNTA_CAMPO)
            if re.match(r"^e (o|a|os|as|do|da|no|na|quanto|qual|quando|quem|pra|para|ela|ele)?\b", p) or \
                    re.search(r"\b(dela|dele|desse|dessa)\b", p) or campo_aqui:
                s = u["s"]                              # continuação do assunto: "e a poltrona?", "e o pedido dela?"
        if not s:
            return None
        if u and u["s"] is s and time.time() - u["t"] < 600:
            # completa a pergunta curta com o que faltou da anterior (o produto ou o que ele queria saber)
            tem_campo = any(re.search(rx, p) for _, rx in sw.PERGUNTA_CAMPO)
            d_cache = sw.ultimos.get(s["nome"]) or {}
            m = sw._mapa(d_cache.get("cab") or []) if d_cache else {}
            i = m.get("produto")
            palavras = [w for w in re.findall(r"[a-z0-9]{4,}", p)]
            tem_produto = bool(i is not None and any(
                any(re.search(r"\b" + re.escape(w), textutil.sem_acento((l[i] if i < len(l) else "").lower())) for w in palavras)
                for l in d_cache.get("linhas", [])))
            if not tem_campo and u.get("campo_txt") and not re.search(r"\b(quantos|quantas|quais|lista|todos|todas)\b", p):
                pergunta_sistema += " " + u["campo_txt"]
            pergunta_geral = re.search(r"\b(quantos|quantas|quais|lista|listar|todos|todas|foram|ontem|hoje|anteontem|semana|"
                                       r"mes|ate|desde|entre|\d{1,2}/\d{1,2})\b", p)
            if not tem_produto and not pergunta_geral and u.get("produto_txt") and \
                    re.search(r"\b(dela|dele|ela|ele|desse|dessa|mesmo|mesma|isso)\b|^e (o|a|os) (pedido|data|status|setores?|"
                              r"quantidade|linha|carga|aprovacao)\b|^(quem criou|quando foi criad[oa]|qual o pedido|"
                              r"qual a data)\b\W*$", p):
                pergunta_sistema += " " + u["produto_txt"]
        campo_txt = next((re.search(rx, p).group(0) for _, rx in sw.PERGUNTA_CAMPO if re.search(rx, p)), "")
        ps = textutil.sem_acento(pergunta_sistema.lower())
        produto_txt = re.sub(r"\s+", " ", re.sub(r"\b(qual|quais|quando|quem|data|prevista|previsto|o|a|os|as|de|da|do|no|na|e|"
                                                  r"cnp|cnps|sistema|origus|foi|criad[oa]|gerad[oa]|pedido|status|setores?|"
                                                  r"tem|esta|dela|dele|ela|ele|mantiqueira)\b|[?!.,]", " ", ps)).strip()
        self.ultimo_cnp = {"s": s, "t": time.time(),
                           "campo_txt": campo_txt or (u.get("campo_txt", "") if u else ""),
                           "produto_txt": (u.get("produto_txt", "") if u else "")}
        original = pergunta_sistema
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
            u2 = getattr(self, "ultimo_cnp", None)
            if u2 is not None:
                u2["produto_txt"] = getattr(sw, "ultimo_produto", "") or u2.get("produto_txt", "")
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

    # ------------------------------------------------------------------ "quantas pastas tem no File Projetos?"
    def conteudo_pasta(self, p, original):
        """Lista o que existe numa unidade ou pasta (só o primeiro nível, como o Explorador mostra ao entrar)."""
        if re.search(r"\b(cnp|cnps|origus|planilha|excel|agenda|lembr|procur|abre|abrir)\b", p):
            return None
        if not (re.search(r"\b(quantas|quantos|quais|lista|listar|mostra|mostre|o que (tem|existe|ha))\b", p) and
                re.search(r"\b(pastas?|arquivos?|itens|conteudo|tem dentro|tem na|tem no|existe na|existe no)\b", p)):
            return None
        onde, lugar, resto = self._onde(p)
        raiz = None
        raizes = [r for r, _, _ in (self.n.indice.locais() if self.n.indice else [])]
        if onde in raizes or re.fullmatch(r"[A-Z]:\\", onde or ""):
            raiz = onde
        elif onde == "pc":
            raiz = "C:\\"
        # nome da pasta citada: "na engenharia", "dentro da pasta ateliê"
        nome = ""
        m = re.search(r"\b(?:na|no|da|do|dentro da|dentro do|em)\s+(?:pasta\s+)?([a-z0-9][a-z0-9 _\-]*)", resto)
        if m:
            nome = m.group(1)
        lixo = r"\b(quantas|quantos|quais|lista|listar|mostra|mostre|o que|tem|ha|existe|existem|pastas?|arquivos?|itens|aba|" \
               r"inicial|inicialmente|assim|que|voce|vc|entra|entrar|quando|logo|ao|na|no|da|do|de|dentro|primeira|tela|" \
               r"mantiqueira|agora|hoje|e|a|o|os|as|nela|nele|conteudo)\b"
        partes = [re.sub(r"\s+", " ", re.sub(lixo, " ", x)).strip()
                  for x in re.split(r"\s+(?:da|do|de|dentro da|dentro do)\s+(?:pasta\s+)?", nome)]
        partes = [x for x in partes if x]
        nome = " / ".join(partes)
        alvo = raiz
        if partes:
            alvo = self._achar_pasta(partes, raiz, raizes)
            if not alvo:
                return f"Não encontrei a pasta \"{nome}\"{lugar}, {self._trat()}."
        if not alvo:
            return None                                   # não disse onde: deixa outra parte responder
        try:
            itens = list(os.scandir(alvo))
        except OSError as e:
            return f"Não consegui abrir {alvo}, {self._trat()}. Pode ser que a rede esteja desconectada ({e.strerror})."

        def visivel(e):
            if e.name.startswith(("$", "~$", ".")) or e.name.lower() in ("system volume information", "desktop.ini", "thumbs.db"):
                return False
            try:
                return not (e.stat().st_file_attributes & 0x6)    # oculto ou de sistema
            except (OSError, AttributeError):
                return True
        itens = [e for e in itens if visivel(e)]
        pastas = sorted([e.name for e in itens if e.is_dir()], key=str.lower)
        arqs = sorted([e.name for e in itens if not e.is_dir()], key=str.lower)
        rot = os.path.basename(alvo.rstrip("\\")) or (lugar.strip().replace("no ", "", 1) or alvo)
        if raiz and alvo == raiz:
            rot = (lugar.strip()[3:] if lugar.strip().startswith("no ") else lugar.strip()) or alvo
            rot = f"{rot} ({alvo[:2]})"
        self.ultimo_caminho = alvo
        self.n.detalhe_texto = "\n".join([alvo] + [f"[pasta] {x}" for x in pastas] + [f"{x}" for x in arqs])
        fp = ("nenhuma pasta" if not pastas else ("uma pasta" if len(pastas) == 1 else f"{len(pastas)} pastas"))
        fa = ("nenhum arquivo" if not arqs else ("um arquivo" if len(arqs) == 1 else f"{len(arqs)} arquivos"))
        lista_p = (": " + ", ".join(pastas[:12]) + (f", e mais {len(pastas) - 12}" if len(pastas) > 12 else "")) if pastas else ""
        lista_a = (": " + ", ".join(arqs[:5]) + (f", e mais {len(arqs) - 5}" if len(arqs) > 5 else "")) if arqs else ""
        # "abre o terceiro" logo depois abre o item da lista falada (primeiro as pastas, depois os arquivos)
        self.resultados = [{"nome": x, "caminho": os.path.join(alvo, x), "pasta": alvo, "origem": "", "eh_pasta": 1}
                           for x in pastas] + \
                          [{"nome": x, "caminho": os.path.join(alvo, x), "pasta": alvo, "origem": "", "eh_pasta": 0}
                           for x in arqs]
        self.consulta, self.quando_busca = os.path.basename(alvo), time.time()
        if not pastas and not arqs:
            return f"A pasta {rot} está vazia, {self._trat()}."
        if not pastas:
            return f"Em {rot} não há pastas, só {fa}{lista_a}."
        if not arqs:
            return f"Em {rot} há {fp}{lista_p}, e nenhum arquivo solto."
        return f"Em {rot} há {fp}{lista_p}. E {fa}{lista_a}."

    def _achar_pasta(self, partes, raiz, raizes):
        """partes = ['impressos', 'espreguicadeira alemanha'] → a pasta IMPRESSOS que fica dentro de ESPREGUIÇADEIRA ALEMANHA."""
        nome, acima = partes[0], partes[1:]
        bases = [raiz] if raiz else raizes
        if not acima:
            for b in bases:                               # primeiro: pasta com esse nome logo na entrada da unidade
                try:
                    for e in os.scandir(b):
                        if e.is_dir() and textutil.sem_acento(e.name.lower()).strip() == nome:
                            return e.path
                except OSError:
                    continue
        if not self.n.indice:
            return None
        ex, par = self.n.indice.buscar(nome, raiz or "tudo", limite=200)
        cands = [r for r in ex if r["eh_pasta"]]
        if acima:
            cands = [r for r in cands if self._na_pasta(r["caminho"], acima)]
        iguais = [r for r in cands if textutil.sem_acento(r["nome"].lower()).strip() == nome]
        cands = sorted(iguais or cands, key=lambda r: r["caminho"].count("\\"))
        return cands[0]["caminho"] if cands else None

    def _usar(self, caminho):
        """Abre o arquivo — ou manda imprimir, quando o pedido foi de impressão."""
        if getattr(self, "_acao", "abrir") == "imprimir":
            from .sistemas_web import SistemasWeb
            SistemasWeb.imprimir(caminho, getattr(self, "_impressora_atual", None))
            time.sleep(1.5)
        else:
            os.startfile(caminho)

    # ------------------------------------------------------------------ imprimir / gerar PDF (CNPs e arquivos achados)
    @staticmethod
    def _selecao(p, total):
        """Índices escolhidos numa lista falada: 'todos', 'os dois primeiros', 'o 1 e o 3', 'o segundo'. None = não disse."""
        if re.search(r"\b(todos|todas|tudo|ambos|ambas|eles|elas)\b", p):
            return list(range(total))
        mm = re.search(r"\b(?:os|as) (dois|duas|tres) primeir[oa]s\b|\b(?:os|as) (dois|duas|tres)\b", p)
        if mm:
            return list(range(min({"dois": 2, "duas": 2, "tres": 3}[mm.group(1) or mm.group(2)], total)))
        nums = []
        for m_ in re.finditer(r"\b(" + "|".join(sorted(ORDINAIS, key=len, reverse=True)) + r"|\d{1,2})\b", p):
            w = m_.group(1)
            i_ = ORDINAIS.get(w, int(w) - 1 if w.isdigit() else None)
            if i_ is not None and i_ not in nums:
                nums.append(i_ if i_ >= 0 else total - 1)
        if nums:
            return [i for i in nums if 0 <= i < total]
        if total == 1 and re.search(r"\b(esse|essa|este|esta|ele|ela|dele|dela|isso|o pdf|a cnp|o cnp)\b", p):
            return [0]
        return None

    def _impressora(self, p, sw):
        m = re.search(r"\bna (?:impressora|maquina)(?: d[aeo])?\s+([a-z0-9][a-z0-9 \-]*)", p)
        if not m:
            return None, None
        pedido = m.group(1).strip()
        lista = sw.impressoras() if sw else []
        pal = [w for w in re.findall(r"[a-z0-9]+", pedido) if w not in ("da", "do", "de", "com", "sem", "foto")]
        for nome in lista:
            nn = textutil.sem_acento(nome.lower())
            if pal and all(w in nn for w in pal[:2]):
                return nome, None
        for nome in lista:
            nn = textutil.sem_acento(nome.lower())
            if pal and any(w in nn for w in pal if len(w) >= 2):
                return nome, None
        return None, (f"Não achei a impressora \"{pedido}\", {self._trat()}. As impressoras deste computador são: "
                      + "; ".join(lista) + ".") if lista else f"Não consegui ver as impressoras deste computador, {self._trat()}."

    def imprimir_pedido(self, p, original):
        if not RX_IMPRIMIR.search(p):
            return None
        if RX_ABRIR.search(p) and not re.search(r"imprim|\bgera|\bgere|\bsalva|\bexporta|\bcria", p):
            return None                                 # "abre o plano de corte em pdf" é abrir arquivo
        imprimir = bool(re.search(r"\bimprim\w*|\bimpressao\b", p))
        sw = self.n.sistemas
        u = getattr(self, "ultimo_cnp", None)
        lista_cnp = getattr(sw, "ultima_lista", []) if sw else []
        recente_cnp = bool(u and time.time() - u["t"] < 900 and lista_cnp)
        fala_cnp = bool(re.search(r"\bcnps?\b|\borigus\b", p))
        # o que sobra da frase tirando "imprime", impressora, números e palavras de escolha: se sobrar um nome, é um pedido novo
        sobra = re.sub(r"\b(imprim\w*|impressao|gera\w*|gere|salva\w*|cria\w*|faz|faca|fazer|exporta\w*|tira|tire|pdfs?|em|com|"
                       r"sem|foto|fotos|pra|para|mim|me|o|a|os|as|um|uma|de|do|da|dos|das|e|todos|todas|tudo|ambos|ambas|eles|elas|"
                       r"esse|essa|este|esta|isso|dele|dela|ele|ela|dois|duas|tres|primeir[oa]s?|segund[oa]s?|terceir[oa]s?|"
                       r"quart[oa]s?|quint[oa]s?|ultim[oa]s?|numero|n|por|favor|mantiqueira|agora|ai|la|quero|que|voce|vc|"
                       r"arquivos?|\d{1,2})\b", " ", re.sub(r"\bna (impressora|maquina)\b.*$", " ", p))
        sobra = re.sub(r"\s+", " ", sobra).strip()
        # 1) arquivos que acabei de achar ("imprime todos" / "imprime o 2" depois de uma busca)
        if imprimir and not fala_cnp and not sobra and self.resultados and time.time() - self.quando_busca < 600 and \
                not (recente_cnp and u["t"] > self.quando_busca):
            sel = self._selecao(p, len(self.resultados))
            if sel is None:
                sel = [0] if len(self.resultados) == 1 else None
            if sel is None:
                self._acao_lista = "imprimir"
                return f"Qual deles eu imprimo, {self._trat()}? Diga o número, ou \"imprime todos\"."
            impressora, erro = self._impressora(p, sw)
            if erro:
                return erro
            arqs = [self.resultados[i] for i in sel if not self.resultados[i]["eh_pasta"]][:20]
            from .sistemas_web import SistemasWeb
            for r in arqs:
                SistemasWeb.imprimir(r["caminho"], impressora)
                time.sleep(1.5)
            self.resultados = []
            return (f"Mandei imprimir {len(arqs)} arquivo{'s' if len(arqs) > 1 else ''}"
                    f"{' na ' + impressora if impressora else ' na impressora padrão'}: " + "; ".join(r["nome"] for r in arqs) + ".")
        # 1b) arquivo pelo nome, no computador, pendrive, File Projetos ou File Aluminas: "imprime o pdf da mesa luna"
        if imprimir and not fala_cnp and sobra and not (recente_cnp and not sobra):
            impressora, erro = self._impressora(p, sw)
            if erro:
                return erro
            p2 = re.sub(r"\bna (impressora|maquina)\b.*$", " ", p)
            p2 = re.sub(r"\b(imprim\w*|manda imprimir)\b", "abre", p2, count=1)
            self._acao, self._impressora_atual = "imprimir", impressora
            try:
                r = self.abrir_pedido(p2, original)
            finally:
                self._acao = "abrir"
            if not r:
                return None
            if self.resultados:
                self._acao_lista = "imprimir"
                self._impressora_lista = impressora
            r = r.replace("Qual deles eu abro?", "Qual deles eu imprimo? Diga o número, ou \"imprime todos\".")
            r = re.sub(r"^Abrindo (\d+) arquivos", r"Mandei imprimir \1 arquivos", r)
            r = re.sub(r"^Abrindo ", "Mandei imprimir ", r)
            r = r.replace("Não abri nada", "Não imprimi nada")
            if r.startswith("Mandei imprimir"):
                r = r.rstrip(".") + (f", na {impressora}." if impressora else ", na impressora padrão.")
            return r
        # 2) CNPs do sistema
        if not sw or not (fala_cnp or recente_cnp):
            return None
        s = sw.qual(p) or (u["s"] if u else None) or next((x for x in sw.lista() if "cnp" in (x["url"] + x["nome"]).lower()), None)
        if not s:
            return None
        try:
            d = sw.ler(s)
        except Exception as e:
            return f"Não consegui ler o sistema de {s['nome']} agora, {self._trat()} ({e})."
        if d.get("login"):
            return f"O sistema de {s['nome']} está pedindo login, {self._trat()}. Clique em Entrar nas Configurações."
        m = sw._mapa(d["cab"])
        ids_sistema = {(l[m["id"]] if m.get("id") is not None and m["id"] < len(l) else ""): l for l in d["linhas"]}
        itens = []
        # números de CNP ditos ("imprime o CNP 953 e o 954")
        for n_ in re.findall(r"\b(\d{3,5})\b", p):
            if n_ in ids_sistema:
                l = ids_sistema[n_]
                prod = re.split(r"\s+similar:", l[m["produto"]], flags=re.I)[0].strip() if m.get("produto") is not None else ""
                itens.append((n_, f"CNP {n_}, {prod}"))
        if not itens:
            sel = self._selecao(re.sub(r"\b\d{3,5}\b", " ", p), len(lista_cnp)) if recente_cnp else None
            if sel is not None:
                itens = [lista_cnp[i] for i in sel]
            else:
                # pelo nome do produto / período: "imprime o CNP da banqueta miches", "gera pdf dos CNPs criados ontem"
                consulta = re.sub(r"\b(imprim\w*|impressao|gera\w*|gere|salva\w*|cria\w*|faz|faca|fazer|exporta\w*|tira|tire|"
                                  r"pdfs?|em|com|sem|foto|fotos|na|impressora|maquina|pcp|rh|engenharia|pra|para|mim|me|o|a|os|as|"
                                  r"um|uma|de|do|da|dos|das|cnp|cnps)\b", " ", p)
                consulta = re.sub(r"\s+", " ", consulta).strip()
                if consulta:
                    resp = sw.responder(s, d, "cnp " + consulta)
                    lista_cnp = getattr(sw, "ultima_lista", [])
                    if not lista_cnp:
                        return resp or f"Não achei esse CNP, {self._trat()}."
                    if len(lista_cnp) > 1 and not re.search(r"\b(todos|todas|ambos|ambas)\b", p):
                        self.ultimo_cnp = {"s": s, "t": time.time(), "campo_txt": "", "produto_txt": ""}
                        nomes = "; ".join(f"{i + 1}, {nm}" for i, (_, nm) in enumerate(lista_cnp[:8]))
                        return (f"Achei {len(lista_cnp)} CNPs: {nomes}. Qual eu {'imprimo' if imprimir else 'passo para PDF'}? "
                                f"Diga o número, ou \"todos\".")
                    itens = lista_cnp
        if not itens:
            return (f"Qual CNP eu {'imprimo' if imprimir else 'passo para PDF'}, {self._trat()}? Diga o número do CNP, "
                    f"o nome do produto, ou peça depois de uma lista: \"imprime todos\".")
        itens = itens[:30]
        impressora, erro = self._impressora(p, sw) if imprimir else (None, None)
        if erro:
            return erro
        foto = not re.search(r"\bsem foto", p)
        aviso = (f"Um instante, {self._trat()}. Estou preparando {len(itens)} CNP{'s' if len(itens) > 1 else ''}.")
        try:
            self.n.ultima["assistente"] = aviso
            if self.n.voz and not self.n.em_silencio():
                self.n.voz.falar(aviso)
        except Exception:
            pass
        try:
            pdfs = sw.gerar_pdfs(s, [(i_, nm.split(", ", 1)[-1]) for i_, nm in itens], foto=foto)
        except Exception as e:
            log.exception("PDF do CNP")
            return f"Não consegui gerar o PDF, {self._trat()} ({e})."
        self.n.detalhe_texto = "\n".join(str(x) for x in pdfs)
        self.ultimo_cnp = {"s": s, "t": time.time(), "campo_txt": "", "produto_txt": ""}
        if imprimir:
            erros = 0
            for arq in pdfs:
                try:
                    sw.imprimir(arq, impressora)
                    time.sleep(2)
                except Exception:
                    log.exception("imprimir")
                    erros += 1
            if erros == len(pdfs):
                return (f"Gerei os PDFs, mas o Windows não conseguiu mandar para a impressora, {self._trat()}. "
                        f"Eles estão em Documentos, Mantiqueira, CNPs.")
            return (f"Mandei imprimir {len(pdfs) - erros} CNP{'s' if len(pdfs) - erros > 1 else ''}"
                    f"{' na ' + impressora if impressora else ' na impressora padrão'}"
                    f"{', sem foto' if not foto else ''}: " + "; ".join(nm for _, nm in itens[:6]) + ".")
        if len(pdfs) == 1:
            os.startfile(str(pdfs[0]))
            return f"Pronto, gerei o PDF do {itens[0][1]} e abri. Ele fica em Documentos, Mantiqueira, CNPs."
        os.startfile(str(pdfs[0].parent))
        return (f"Pronto, gerei {len(pdfs)} PDFs e abri a pasta Documentos, Mantiqueira, CNPs: "
                + "; ".join(nm for _, nm in itens[:6]) + ".")

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

    # ------------------------------------------------------------------ programas e comandos do computador
    def _avisar(self, texto):
        try:
            self.n.ultima["assistente"] = texto
            if self.n.voz and not self.n.em_silencio():
                self.n.voz.falar(texto)
        except Exception:
            pass

    def confirmar_energia(self, p, original):
        """Resposta ao "tem certeza que quer desligar?"."""
        c = getattr(self, "_confirmar", None)
        if not c:
            return None
        self._confirmar = None
        if time.time() - c["t"] > 60:
            return None
        if re.fullmatch(r"(mantiqueira )?(sim|pode|pode sim|confirmo|confirma|confirmado|isso|isso mesmo|com certeza|claro|"
                        r"pode (desligar|reiniciar)|(desliga|desligar|reinicia|reiniciar)( sim)?|manda ver|faz isso)"
                        r"( sim| mantiqueira| senhor| por favor| agora)*", p):
            from . import programas
            if programas.energia(c["acao"]):
                self._energia_t = time.time()
                verbo = "desligar" if c["acao"] == "desligar" else "reiniciar"
                return (f"Certo, {self._trat()}. O computador vai {verbo} em 30 segundos. Salve o que estiver aberto. "
                        f"Para cancelar, diga: cancela o desligamento.")
            return f"O Windows não aceitou o comando, {self._trat()}. Não desliguei nada."
        if re.search(r"\b(nao|cancela|cancele|deixa|esquece|para)\b", p):
            return f"Tudo bem, {self._trat()}. Não {'desliguei' if c['acao'] == 'desligar' else 'reiniciei'}."
        return None

    def computador(self, p, original):
        from . import programas
        t = self._trat()
        # cancelar desligamento
        if re.search(r"\b(cancela|cancele|cancelar|para|nao)\b.*\b(desligamento|desligar|deslig\w*|reinici\w*)\b", p) and \
                (time.time() - getattr(self, "_energia_t", 0) < 120 or re.search(r"\bdesligamento\b", p)):
            programas.energia("cancelar")
            self._energia_t = 0
            return f"Cancelado, {t}. O computador não vai mais desligar."
        # desligar / reiniciar: sempre pergunta antes
        m = re.search(r"\b(desliga|desligue|desligar|reinicia|reinicie|reiniciar)\s+(o |a )?(computador|pc|maquina|windows)\b", p)
        if m and not re.search(r"\b(nao|como|quando|por que|porque)\b", p):
            acao = "desligar" if m.group(1).startswith("deslig") else "reiniciar"
            self._confirmar = {"acao": acao, "t": time.time()}
            return f"Tem certeza que quer {acao} o computador, {t}? Diga sim para confirmar."
        if re.search(r"\b(bloqueia|bloqueie|bloquear|trava|trave|travar)\s+(o |a )?(computador|pc|tela|maquina|windows)\b", p):
            programas.bloquear()
            return f"Computador bloqueado, {t}."
        # volume do Windows (o volume da minha voz continua em "fala mais alto/baixo")
        if re.search(r"\b(volume|som)\b.*\b(computador|pc|windows|geral|do sistema)\b|\b(computador|pc)\b.*\bvolume\b", p) or \
                re.fullmatch(r"(mantiqueira )?(coloca o |poe o |deixa o )?volume (em|no|para|pra|a) \d{1,3}( por cento|%)?", p):
            mv = re.search(r"\bvolume\b.*?\b(?:em|no|para|pra|a)\s+(\d{1,3})\b", p)
            if mv:
                programas.volume("definir", int(mv.group(1)))
                return f"Volume do computador em {min(100, int(mv.group(1)))} por cento, {t}."
            if re.search(r"\b(aumenta|aumente|sobe|suba|mais alto|aumentar)\b", p):
                programas.volume("mais")
                return f"Aumentei o volume do computador, {t}."
            if re.search(r"\b(abaixa|abaixe|diminui|diminua|baixa|mais baixo|diminuir)\b", p):
                programas.volume("menos")
                return f"Abaixei o volume do computador, {t}."
        if re.search(r"\b(muta|mute|silencia|silencie)\s+(o )?(computador|pc|windows)\b|"
                     r"\b(tira|tire|desliga|corta)\s+(o )?(som|audio)\s+do\s+(computador|pc|windows)\b|"
                     r"\b(tira|tire)\s+(o computador |o pc )?do mudo\b|\bdesmuta\b|\b(volta|liga)\s+o\s+(som|audio)\s+do\s+(computador|pc)\b", p):
            liga = bool(re.search(r"\bdo mudo\b|\bdesmuta\b|\b(volta|liga)\b", p))
            if liga == getattr(self, "_mudo", False) or not hasattr(self, "_mudo"):
                programas.volume("mudo")
            self._mudo = not liga
            return f"Tirei o computador do mudo, {t}." if liga else f"Coloquei o computador no mudo, {t}."
        # print
        if re.search(r"\b(tira|tire|tirar|faz|faca|salva|salve)\s+(um |uma )?(print|captura|foto da tela)\b|"
                     r"^(print( da tela)?|captura( a)? tela)$", p):
            arq = programas.print_tela()
            self.ultimo_caminho = arq
            return f"Tirei um print da tela e salvei em Imagens, Mantiqueira, {t}."
        # área de trabalho / janela atual
        if re.search(r"\b(minimiza|minimize|esconde|esconda)\s+(tudo|todas as janelas|todos)\b|\bmostra a area de trabalho\b", p):
            programas.minimizar_tudo()
            return f"Pronto, {t}."
        if re.fullmatch(r"(mantiqueira )?(fecha|feche|fechar)\s+(essa|esta|a)\s+janela( ai| por favor| pra mim)*", p):
            tt = programas.fechar_janela_atual()
            if not tt:
                return f"Não achei uma janela para fechar, {t}."
            return f"Fechei a janela {textutil.curto(tt, 60)}. Se tinha algo sem salvar, ela pergunta antes."
        # digitar
        md = re.match(r"^\s*(?:mantiqueira[\s,]+)?(?:digita|digite|digitar|escreve a[ií]|escreva a[ií])\s*[:,]?\s+(.+)$",
                      original.strip(), re.I | re.S)
        if md:
            texto = md.group(1).strip().strip('"“”')
            jan = programas.digitar(texto)
            return f"Digitei{(' no ' + textutil.curto(jan, 50)) if jan else ''}, {t}."
        # teclas
        mk = re.match(r"^(?:mantiqueira )?(?:aperta|aperte|apertar|pressiona|pressione|tecla|da um|de um)\s+(.+)$", p)
        if mk:
            combo = programas.combinacao(mk.group(1))
            if combo:
                jan = programas.apertar(combo)
                return f"Apertei {combo.replace('+', ' + ')}{(' no ' + textutil.curto(jan, 50)) if jan else ''}, {t}."
            return None
        if re.search(r"\b(quais|que)\s+(programas|janelas|aplicativos)\b.*\b(abert[oa]s|rodando)\b", p):
            lista = programas.abertos()
            if not lista:
                return f"Não há nenhum programa com janela aberta agora, {t}."
            return f"Estão abertos {len(lista)} programas: " + ", ".join(lista[:12]) + "."
        return None

    def programa(self, p, original):
        from . import programas
        m = re.match(r"^(?:mantiqueira )?(abre|abra|abrir|inicia|inicie|iniciar|executa|execute|roda|rode|liga|ligue|"
                     r"fecha|feche|fechar|encerra|encerre|sai do|sai da|"
                     r"vai para|vai pro|vai pra|volta para|volta pro|volta pra|muda para|muda pro|muda pra|troca para|"
                     r"troca pro|troca pra|mostra|mostre|traz|traga|minimiza|minimize|esconde|esconda)\s+(.+?)"
                     r"(?:\s+(?:pra frente|para frente|pra mim|por favor|ai|agora))*$", p)
        if not m:
            return None
        if self._apelido_na_frase(p):
            return None                                         # apelido dele vale mais
        verbo, alvo = m.group(1), m.group(2)
        prog = programas.resolver(alvo, aceitar_qualquer=bool(re.search(r"\b(programa|aplicativo)\b", alvo)))
        if not prog:
            return None
        nome, t = prog["nome"], self._trat()
        art = "a" if nome in ("Calculadora",) else "o"
        if verbo.startswith(("abr", "inic", "exec", "rod", "lig")):
            r = programas.abrir(prog)
            self.resultados = []
            if r == "frente":
                return f"{art.upper()} {nome} já estava {'aberta' if art == 'a' else 'aberto'}; trouxe para a frente, {t}."
            if r == "aberto":
                return f"Abrindo {art} {nome}."
            return f"Não achei {art} {nome} instalado neste computador, {t}. Não abri nada."
        if verbo.startswith(("fech", "encerr", "sai")):
            n = programas.fechar(prog)
            if not n:
                return f"{art.upper()} {nome} não está {'aberta' if art == 'a' else 'aberto'}, {t}."
            return (f"Fechei {art} {nome}, {t}. Se tinha algo sem salvar, ele pergunta antes de fechar."
                    if n == 1 else f"Fechei {n} janelas do {nome}, {t}. Se tinha algo sem salvar, ele pergunta antes.")
        if verbo.startswith(("minimi", "escond")):
            n = programas.minimizar(prog)
            return f"Minimizei {art} {nome}, {t}." if n else f"{art.upper()} {nome} não está aberto, {t}."
        if programas.focar(prog):
            return f"Pronto, {art} {nome} está na frente, {t}."
        if verbo.startswith(("mostr",)):
            return None                                         # "mostra o …" pode ser outra coisa
        return f"{art.upper()} {nome} não está aberto, {t}. Se quiser, diga: abre {art} {nome}."

    # ------------------------------------------------------------------ peças simples no SolidWorks
    def peca_solidworks(self, p, original):
        from . import solidworks_pecas as sp
        texto = original
        pend = getattr(self, "_peca_pendente", None)
        if pend and time.time() - pend["t"] < 180 and re.search(r"\d", p) and not sp.RX_PEDIDO.search(sp._texto(p)) and \
                not RX_ABRIR.search(p):
            texto = pend["texto"] + " com " + original            # completa o que faltou ("100", "1,5 de parede")
        tt = sp._texto(texto)
        if not sp.RX_PEDIDO.search(tt):
            return None
        if re.search(r"\b(como|qual|quais|onde|porque|por que|o que)\b", tt) or textutil.pede_lembrete(p):
            return None                                         # pergunta sobre como fazer: a IA explica
        if not re.search(r"\d|\b(solidworks|solid)\b", tt) and not re.search(r"\b(cubo|chapa|cilindro|tubo|metalon)\b", tt):
            return None
        ped, erro = sp.entender(texto)
        if not ped:
            self._peca_pendente = {"texto": texto, "t": time.time()} if erro else None
            return erro
        self._peca_pendente = None
        from . import sistema
        aberto = True
        try:
            aberto = sistema.solidworks_aberto()
        except Exception:
            pass
        self._avisar(f"Um instante, {self._trat()}. " + ("Estou fazendo a peça no SolidWorks." if aberto else
                                                          "Vou abrir o SolidWorks primeiro; isso demora um pouco."))
        try:
            ok, msg = sp.criar(ped)
        except Exception as e:
            log.exception("peça no SolidWorks")
            return f"Não consegui fazer a peça no SolidWorks, {self._trat()}. O SolidWorks respondeu: {str(e)[:120]}"
        return msg
