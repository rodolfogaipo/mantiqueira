"""Cérebro: monta o contexto (agenda, atividade, notas), conversa com a IA e executa as ações."""
import os
import re
import time
import logging
import datetime as dt
from . import textutil
from .db import agora, d as parse_dt

log = logging.getLogger("cerebro")

ESQUEMA = {
    "type": "object",
    "properties": {
        "resposta": {"type": "string"},
        "acao": {"type": "string", "enum": ["nenhuma", "criar_lembrete", "abrir_arquivo", "salvar_nota",
                                             "ler_tela", "concluir_lembrete", "mudar_tratamento", "mudar_nome"]},
        "quando": {"type": "string"},
        "texto": {"type": "string"},
        "arquivo": {"type": "string"},
    },
    "required": ["resposta", "acao"],
}

PALAVRAS_VAZIAS = set("""a o as os um uma uns umas de do da dos das no na nos nas em por para pra pro com sem que
qual quais quando onde como eu me mim meu minha meus minhas voce você ele ela isso esse essa este esta aquele
ontem hoje amanha amanhã semana dia dias foi era estava estou tava fiz fez fazendo arquivo arquivos programa
mantiqueira favor pode poderia queria quero sobre ainda já ja mais muito pouco tudo nada algum alguma senhor
tarde manhã manha noite horas hora abre abrir lembra lembrar mostra""".split())


def _termos(pergunta):
    w = re.findall(r"[\wÀ-ú_.-]{4,}", pergunta.lower())
    return [x for x in w if textutil.sem_acento(x) not in {textutil.sem_acento(p) for p in PALAVRAS_VAZIAS}][:5]


class Cerebro:
    def __init__(self, nucleo):
        self.n = nucleo
        self.historico = []   # [{"role","content"}]
        self.lembrete_pendente = None
        for r in self.n.db.conversa_ultimas(8):
            self.historico.append({"role": "user" if r["papel"] == "usuario" else "assistant", "content": r["texto"]})

    # ------------------------------------------------------------------ contexto
    def _contexto(self, pergunta):
        n, cfg, db = self.n, self.n.cfg, self.n.db
        agora_ = agora()
        partes = []
        partes.append(f"AGORA: {textutil.data_extenso(agora_)}.")
        partes.append(f"USUÁRIO: {cfg['nome']}. Trate-o por '{cfg['tratamento']}'.")
        if n.olhos and n.olhos.foco:
            f = n.olhos.foco
            partes.append(f"EM USO AGORA: {f['app']} · {f['arquivo'] or textutil.curto(f['titulo'], 60)}"
                          + (" (com alterações não salvas)" if f.get("nao_salvo") else ""))
        lem = db.lembretes_proximos(10)
        if lem:
            partes.append("LEMBRETES PENDENTES:\n" + "\n".join(
                f"- {parse_dt(l['quando']):%d/%m %H:%M} {l['texto']}" + (f" (repete: {l['repetir']})" if l['repetir'] else "")
                for l in lem))
        else:
            partes.append("LEMBRETES PENDENTES: nenhum.")
        pend = db.pendencias_abertas()[:5]
        if pend:
            partes.append("PENDÊNCIAS PERCEBIDAS:\n" + "\n".join(f"- {p['texto']}" for p in pend))
        if n.olhos:
            hoje = dt.date.today()
            partes.append("REGISTRO DE ATIVIDADE DE HOJE:\n" + ("\n".join(n.olhos.texto_dia(hoje)) or "(nada ainda)"))
            partes.append("REGISTRO DE ATIVIDADE DE ONTEM:\n" +
                          ("\n".join(n.olhos.texto_dia(hoje - dt.timedelta(days=1), 18)) or "(nada registrado)"))
            low = textutil.sem_acento(pergunta.lower())
            if "semana" in low or any(re.search(r"\b" + d, low) for d in
                                      ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo", "anteontem")):
                linhas = []
                for k in range(2, 8):
                    dia = hoje - dt.timedelta(days=k)
                    top = n.olhos.totais(dia)[:5]
                    if top:
                        linhas.append(f"{dia:%d/%m} ({textutil.DIAS_SEMANA[dia.weekday()]}): " + "; ".join(
                            f"{a} · {nm} ({textutil.duracao_texto(s)})" for a, nm, s in top))
                if linhas:
                    partes.append("RESUMO DOS DIAS ANTERIORES:\n" + "\n".join(linhas))
            termos = _termos(pergunta)
            if termos:
                achados = n.olhos.buscar(termos)
                if achados:
                    partes.append("ATIVIDADE RELACIONADA À PERGUNTA (últimos 30 dias):\n" + "\n".join(achados))
        notas = db.notas(8)
        for t in _termos(pergunta):
            for x in db.notas(5, t):
                if x not in notas:
                    notas.append(x)
        if notas:
            partes.append("NOTAS GUARDADAS PELO USUÁRIO:\n" + "\n".join(
                f"- ({x['criado'][:10]}) {x['texto']}" for x in notas[:12]))
        base = getattr(n, "conhecimento", None)
        if base:
            try:
                achados = base.buscar(pergunta, 4)
            except Exception:
                log.exception("busca no conhecimento")
                achados = []
            if achados:
                partes.append("TRECHOS DA BASE DE CONHECIMENTO (guias de programas e documentos do usuário):\n" +
                              "\n\n".join(f"[{a['nome']} — {a['titulo']}]\n{a['texto'][:850]}" for a in achados))
        return "\n\n".join(partes)

    def _sistema(self, pergunta):
        cfg = self.n.cfg
        t = cfg["tratamento"]
        return f"""Você é o Mantiqueira, assistente pessoal e secretário de {cfg['nome']}. Você é masculino: fale de si mesmo no masculino ("estou pronto", "fiquei sabendo", "o Mantiqueira").
Você roda 100% offline no computador dele. Fale em português do Brasil, com educação, calma e jeito de um secretário experiente: atencioso, prático, um pouco formal.
Chame o usuário de "{t}". O seu nome é Mantiqueira; o usuário NÃO se chama Mantiqueira.
Suas respostas serão FALADAS: 1 a 3 frases curtas (até 5 quando estiver explicando como fazer algo num programa), sem listas, sem markdown, sem emojis.
Converse de verdade: se faltar informação para fazer o que ele pediu, PERGUNTE (por exemplo: para quando, a que horas, sobre o quê). Se ele só estiver conversando, converse.
Sobre o que ele fez no computador, use SOMENTE os registros abaixo. Se não houver registro, diga que não encontrou. Nunca invente arquivos, horários ou fatos.
Para dúvidas sobre programas (SolidWorks, AutoCAD, SketchUp, 3ds Max, Aspire, CypCut, Office) e sobre os documentos dele, use os TRECHOS DA BASE DE CONHECIMENTO quando houver: diga o nome do comando, o atalho e onde fica no menu. Se não houver trecho e você não tiver certeza, diga que não tem certeza em vez de inventar um comando.

Responda SEMPRE em JSON com os campos:
- resposta: o que você vai falar.
- acao: nenhuma | criar_lembrete | abrir_arquivo | salvar_nota | ler_tela | concluir_lembrete | mudar_tratamento | mudar_nome
- quando: só para criar_lembrete, no formato AAAA-MM-DD HH:MM, calculado a partir de AGORA, e SÓ se ele disse a hora ou o dia.
- texto: o texto do lembrete (curto, no infinitivo: "Ligar para o fornecedor"), da nota, do lembrete a concluir, ou o novo tratamento/nome.
- arquivo: o nome do arquivo a abrir (exatamente como aparece no registro).

Regras:
- criar_lembrete SOMENTE quando ele pedir para lembrar/avisar/agendar algo. Se ele não disse quando, use acao nenhuma e pergunte "Para quando, {t}?".
- "fale X", "diga X", "repete X" → apenas fale X na resposta (acao nenhuma). Não é lembrete.
- "me chame de X", "pode me chamar de X", "quero que me chame de X" → mudar_tratamento com texto X.
- "meu nome é X" → mudar_nome com texto X.
- "abre", "abrir", "pode abrir" (inclusive "sim" logo depois de você oferecer abrir algo) → abrir_arquivo.
- "anota que", "guarda que", "lembre-se que (uma informação, sem horário)" → salvar_nota.
- "o que tem na minha tela", "lê a tela" → ler_tela.
- "já fiz", "pode tirar o lembrete", "apaga o lembrete" → concluir_lembrete.

Exemplos:
Usuário: me lembra de ligar pro fornecedor → {{"resposta":"Claro, {t}. Para quando?","acao":"nenhuma"}}
Usuário: amanhã às 9 → {{"resposta":"Combinado. Amanhã às 9 eu aviso para ligar ao fornecedor.","acao":"criar_lembrete","quando":"(amanhã) 09:00","texto":"Ligar para o fornecedor"}}
Usuário: fale Leandrinho vá trabalhar → {{"resposta":"Leandrinho, vá trabalhar!","acao":"nenhuma"}}
Usuário: me chame de doutor → {{"resposta":"Como preferir, doutor.","acao":"mudar_tratamento","texto":"doutor"}}
Usuário: tudo bem com você? → {{"resposta":"Tudo ótimo, {t}, pronto para ajudar. E como está o seu dia?","acao":"nenhuma"}}
Usuário: tenho uma reunião amanhã → {{"resposta":"Quer que eu lembre, {t}? A que horas é a reunião?","acao":"nenhuma"}}

{self._contexto(pergunta)}"""

    # ------------------------------------------------------------------ processar
    def processar(self, pergunta: str) -> str:
        n = self.n
        if not n.ia or not n.ia.pronta:
            return "Ainda estou carregando a inteligência, " + n.cfg["tratamento"] + ". Tente de novo em alguns segundos."
        trat = n.cfg["tratamento"]

        # resposta a "Para quando?" de um lembrete pendente
        if self.lembrete_pendente:
            pend, self.lembrete_pendente = self.lembrete_pendente, None
            quando = textutil.parse_quando("", agora(), pergunta) if textutil.tem_tempo(pergunta) else None
            if quando and time.time() - pend["t"] < 600:
                resp = self._criar_lembrete(pend["texto"], quando, pend["pergunta"] + " " + pergunta)
                self._guardar(pergunta, resp)
                return resp

        msgs = [{"role": "system", "content": self._sistema(pergunta)}] + self.historico[-8:] + \
               [{"role": "user", "content": pergunta}]
        t0 = time.time()
        try:
            r = n.ia.conversar(msgs, ESQUEMA)
        except Exception:
            log.exception("IA falhou")
            return "Desculpe, tive um problema para pensar agora. Pode repetir?"
        n.latencia = time.time() - t0
        resposta = (r.get("resposta") or "").strip()
        acao = (r.get("acao") or "nenhuma").strip()
        log.info("IA: acao=%s r=%r", acao, r)

        # proteções contra a IA se confundir
        if acao == "criar_lembrete" and not textutil.pede_lembrete(pergunta) and not self._ultimo_perguntou_quando():
            acao = "nenhuma"
            resposta = self._conversa_simples(pergunta) or resposta
        if acao == "nenhuma" and textutil.pede_lembrete(pergunta) and not textutil.tem_tempo(pergunta):
            self.lembrete_pendente = {"texto": (r.get("texto") or "").strip() or textutil.texto_do_lembrete(pergunta),
                                      "pergunta": pergunta, "t": time.time()}
            if "?" not in resposta:
                resposta = f"Claro, {trat}. Para quando devo marcar?"
        try:
            resposta = self._executar(acao, r, pergunta, resposta)
        except Exception:
            log.exception("falha ao executar %s", acao)
            resposta = "Não consegui concluir isso agora, " + trat + "."
        if not resposta:
            resposta = "Pronto."
        self._guardar(pergunta, resposta)
        return resposta

    def _guardar(self, pergunta, resposta):
        self.historico += [{"role": "user", "content": pergunta}, {"role": "assistant", "content": resposta}]
        self.historico = self.historico[-12:]

    def _ultimo_perguntou_quando(self):
        if not self.historico:
            return False
        u = textutil.sem_acento(self.historico[-1]["content"].lower())
        return self.historico[-1]["role"] == "assistant" and "?" in u and \
            any(p in u for p in ("quando", "que horas", "qual horario", "que dia"))

    def _conversa_simples(self, pergunta):
        """Resposta comum, sem ações (usada quando a IA quis criar um lembrete que ninguém pediu)."""
        try:
            msgs = [{"role": "system", "content":
                     f"Você é o Mantiqueira, secretário pessoal de {self.n.cfg['nome']}, masculino, educado. "
                     f"Chame-o de '{self.n.cfg['tratamento']}'. Responda em português do Brasil, em 1 a 2 frases "
                     "curtas para serem faladas. Se ele pedir para você falar ou dizer algo, apenas diga aquilo."}] + \
                   self.historico[-6:] + [{"role": "user", "content": pergunta}]
            return self.n.ia.conversar(msgs, None, max_tokens=120).strip().strip('"')
        except Exception:
            log.exception("conversa simples")
            return ""

    def _criar_lembrete(self, texto, quando, frase_usuario):
        repetir = textutil.repeticao(frase_usuario)
        texto = (texto or "Lembrete").strip().rstrip(".")
        texto = texto[:1].upper() + texto[1:]
        self.n.db.lembrete_novo(quando, texto, "voz", repetir)
        hoje = dt.date.today()
        if quando.date() == hoje:
            dia = "hoje"
        elif quando.date() == hoje + dt.timedelta(days=1):
            dia = "amanhã"
        else:
            dia = f"{textutil.DIAS_SEMANA[quando.weekday()]}, dia {quando.day}"
        rep = {"diario": ", todos os dias", "semanal": ", toda semana", "dias_uteis": ", nos dias úteis"}.get(repetir, "")
        hora = f"{quando.hour}h" if quando.minute == 0 else f"{quando.hour}:{quando:%M}"
        return f"Combinado, {self.n.cfg['tratamento']}. Aviso {dia} às {hora}{rep}: {texto[:1].lower() + texto[1:]}."

    def _executar(self, acao, r, pergunta, resposta):
        n, db, trat = self.n, self.n.db, self.n.cfg["tratamento"]
        if acao == "criar_lembrete":
            texto = (r.get("texto") or "").strip() or textutil.texto_do_lembrete(pergunta)
            contexto = pergunta
            if self._ultimo_perguntou_quando() and len(self.historico) >= 2:
                contexto = self.historico[-2]["content"] + " " + pergunta
            quando = None
            if textutil.tem_tempo(pergunta):
                quando = textutil.parse_quando("", agora(), pergunta)
                if not quando:
                    quando = textutil.parse_quando(r.get("quando", ""), agora())
            if not quando or quando < agora() - dt.timedelta(minutes=1):
                self.lembrete_pendente = {"texto": texto, "pergunta": pergunta, "t": time.time()}
                return f"Claro, {trat}. Para quando devo marcar?"
            return self._criar_lembrete(texto, quando, contexto)
        if acao == "mudar_tratamento":
            novo = (r.get("texto") or "").strip().strip(".!").lower()
            novo = re.sub(r"^(o|a|de)\s+", "", novo)
            if not novo or len(novo) > 30:
                return f"Como o {trat} prefere ser chamado?"
            n.cfg.atualizar({"tratamento": novo})
            return f"Como preferir, {novo}."
        if acao == "mudar_nome":
            novo = (r.get("texto") or "").strip().strip(".!")
            if novo and len(novo) <= 40:
                n.cfg.atualizar({"nome": novo[:1].upper() + novo[1:]})
                return f"Muito prazer, {novo}. Vou lembrar disso."
            return resposta
        if acao == "abrir_arquivo":
            nome = (r.get("arquivo") or "").strip()
            caminho = n.olhos.recentes.achar(nome) if n.olhos else None
            if not caminho and n.olhos:
                n.olhos.recentes.atualizar()
                caminho = n.olhos.recentes.achar(nome)
            if not caminho:
                return f"Não encontrei o arquivo {nome or 'pedido'} entre os recentes, {trat}."
            os.startfile(caminho)
            return resposta or f"Abrindo {os.path.basename(caminho)}."
        if acao == "salvar_nota":
            texto = (r.get("texto") or pergunta).strip()
            db.nota_nova(texto)
            return resposta or "Anotado."
        if acao == "concluir_lembrete":
            alvo = textutil.sem_acento((r.get("texto") or pergunta).lower())
            melhor, nota = None, 0.0
            import difflib
            for l in db.lembretes_proximos(30) + db.q("SELECT * FROM lembretes WHERE status='avisado' ORDER BY id DESC LIMIT 10"):
                sc = difflib.SequenceMatcher(None, alvo, textutil.sem_acento(l["texto"].lower())).ratio()
                if sc > nota:
                    melhor, nota = l, sc
            if melhor and nota >= 0.35:
                db.lembrete_status(melhor["id"], "concluido")
                return f"Pronto, tirei o lembrete \"{melhor['texto']}\"."
            return f"Não achei esse lembrete, {trat}."
        if acao == "ler_tela":
            from . import tela
            n.mostrar_mini_seguro(False)
            time.sleep(0.4)
            texto = tela.ler_tela()
            if not texto:
                return f"Não consegui ler nada na tela, {trat}."
            msgs = [{"role": "system", "content":
                     f"Você é o Mantiqueira, secretário pessoal. Chame o usuário de '{trat}'. Responda em português "
                     "do Brasil, em 1 a 3 frases curtas para serem faladas, sem listas. Use o TEXTO DA TELA para "
                     "responder ao pedido do usuário."},
                    {"role": "user", "content": f"TEXTO DA TELA:\n{texto}\n\nPEDIDO: {pergunta}"}]
            return n.ia.conversar(msgs, None, max_tokens=250).strip()
        return resposta
