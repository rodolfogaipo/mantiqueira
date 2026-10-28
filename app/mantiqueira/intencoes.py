"""Pedidos tratados direto pelo programa (sem a IA inventar): procurar e abrir arquivos, memória,
curiosidades, frases, ler janelas e entrar nos sistemas da empresa.
Cada função devolve o texto a falar, ou None se o pedido não for daquele tipo."""
import os
import re
import time
import logging
import subprocess
from . import textutil
from .indice import descrever, ORIGEM_NOME

log = logging.getLogger("intencoes")

RX_BUSCA = re.compile(r"\b(procur\w*|pesquis(a|e|ar)\b|localiz\w*|encontr(a|e|ar)\b|ach(a|e|ar) (pra mim|o|a|os|as|um|uma|meu|minha)\b|"
                      r"onde (esta|estao|fica|ficam|ta|tao|guardei|salvei)|cade)\b")
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


class Intencoes:
    def __init__(self, nucleo):
        self.n = nucleo
        self.resultados = []        # última busca
        self.consulta = ""
        self.quando_busca = 0

    def _trat(self):
        return self.n.cfg["tratamento"]

    # ------------------------------------------------------------------ roteador
    def tratar(self, pergunta, historico):
        p = textutil.sem_acento(pergunta.lower()).strip(" ?!.")
        for f in (self.parar, self.abrir_resultado, self.memoria, self.frases, self.sistema_abrir, self.sistema_consulta,
                  self.abrir_pedido, self.buscar, self.ler_janela):
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
    def buscar(self, p, original):
        if not RX_BUSCA.search(p) or textutil.pede_lembrete(p):
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
        aviso = ""
        if ix.varrendo:
            aviso = f" Ainda estou terminando de mapear {ix.varrendo}, então pode haver mais coisas."
        if exatos:
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
        sobra = re.sub(r"\b(abr[ea]|abrir|pode|sim|isso|esse|essa|mesmo|o|a|os|as|pra|para|mim|me|por|favor|pasta|mostra|onde|"
                       r"fica|dele|dela|numero|n|mantiqueira|ok|quero|" + "|".join(ORDINAIS) + r")\b", " ", p)
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
        ix = self.n.indice
        onde, lugar, resto = self._onde(p)
        exts, resto = self._tipo(resto)
        resto = RX_ABRIR.sub(" ", resto)
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", resto)).strip()
        consulta = re.sub(r"\b(o|a|arquivo|pra|para|mim|favor|por)\b", " ", consulta).strip()
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
        if len(exatos) == 1:
            r = exatos[0]
            if ix:
                ix.lembrar_escolha(consulta, r["caminho"])
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
            return f"Abri o sistema de {s['nome']} para o {self._trat()} fazer o login. Depois pode fechar a janela."
        if re.search(r"\b(abr[ea]|abrir|mostra)\b.*\b(sistema|site|pagina|tela)\b|\babre o (sistema|site)\b", p):
            os.startfile(s["url"])
            return f"Abrindo o sistema de {s['nome']} no navegador."
        return None

    def sistema_consulta(self, p, original):
        """Pergunta sobre o sistema da empresa: lê os dados; se não der, explica (sem a IA inventar)."""
        sw = self.n.sistemas
        if not sw:
            return None
        s = sw.qual(p)
        if not s:
            return None
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
        self.n.contexto_extra = sw.formatar(s, d, original)
        return None                                     # a IA responde usando os dados lidos

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
