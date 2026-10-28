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
        for f in (self.abrir_resultado, self.memoria, self.frases, self.sistema_abrir, self.buscar, self.ler_janela):
            try:
                r = f(p, pergunta)
            except Exception:
                log.exception("intenção %s", f.__name__)
                r = None
            if r:
                return r
        return None

    # ------------------------------------------------------------------ busca de arquivos
    def buscar(self, p, original):
        if not RX_BUSCA.search(p) or textutil.pede_lembrete(p):
            return None
        ix = self.n.indice
        if not ix:
            return f"Ainda estou preparando o mapa de arquivos, {self._trat()}."
        onde = "tudo"
        if re.search(r"\bna rede\b|\bno servidor\b|\bno z\b|\bno y\b", p):
            onde = "rede"
        elif re.search(r"\bno (computador|pc)\b", p):
            onde = "pc"
        elif re.search(r"\bno pendrive\b|\bno pen drive\b", p):
            onde = "pendrive"
        consulta = re.sub(r"\s+", " ", RX_LIXO.sub(" ", p)).strip()
        if len(consulta) < 2:
            return f"O que o {self._trat()} quer que eu procure?"
        exatos, parecidos = ix.buscar(consulta, onde, limite=6)
        self.consulta, self.quando_busca = consulta, time.time()
        lugar = {"tudo": "", "pc": " no computador", "rede": " na rede", "pendrive": " no pendrive"}[onde]
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
        if not self.resultados or time.time() - self.quando_busca > 600:
            return None
        if not re.search(r"\b(abr[ea]|abrir|pode abrir|sim|isso|esse|essa|esse mesmo|o primeiro|o segundo|o terceiro|"
                         r"a primeira|a segunda|a pasta|mostra a pasta|onde fica a pasta)\b", p):
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
