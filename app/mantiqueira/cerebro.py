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
                                             "ler_tela", "concluir_lembrete"]},
        "quando": {"type": "string"},
        "repetir": {"type": "string", "enum": ["", "diario", "semanal", "dias_uteis"]},
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
        return "\n\n".join(partes)

    def _sistema(self, pergunta):
        cfg = self.n.cfg
        return f"""Você é a Mantiqueira, assistente pessoal de voz que roda 100% offline no computador de {cfg['nome']}.
Fale em português do Brasil, com educação e calma. Trate o usuário por "{cfg['tratamento']}".
Suas respostas serão FALADAS em voz alta: use 1 a 3 frases curtas, sem listas, sem markdown, sem emojis.
Sobre o que o usuário fez no computador, use SOMENTE os registros abaixo. Se não houver registro, diga que não encontrou. Nunca invente arquivos, horários ou fatos.

Responda SEMPRE em JSON com os campos:
- resposta: o que você vai falar.
- acao: nenhuma | criar_lembrete | abrir_arquivo | salvar_nota | ler_tela | concluir_lembrete
- quando: para criar_lembrete, data e hora no formato AAAA-MM-DD HH:MM (calcule a partir de AGORA).
- repetir: "" | diario | semanal | dias_uteis
- texto: o texto do lembrete, da nota, ou do lembrete a concluir.
- arquivo: o nome do arquivo a abrir (exatamente como aparece no registro).

Quando usar cada ação:
- "me lembra", "me avisa", "não me deixa esquecer" → criar_lembrete. Se a hora não foi dita, pergunte e use nenhuma.
- "abre", "abrir", "pode abrir" (inclusive "sim" logo depois de você oferecer abrir algo) → abrir_arquivo.
- "anota", "guarda que", "lembre-se que", "grava que" → salvar_nota com a informação.
- "o que tem na minha tela", "lê a tela", "o que está escrito aqui" → ler_tela.
- "já fiz", "pode tirar o lembrete", "conclui o lembrete" → concluir_lembrete.
Exemplos:
Usuário: me lembra amanhã às 9 de ligar pro fornecedor → {{"resposta":"Certo, {cfg['tratamento']}. Amanhã às 9 eu aviso para ligar ao fornecedor.","acao":"criar_lembrete","quando":"(data de amanhã) 09:00","repetir":"","texto":"Ligar para o fornecedor"}}
Usuário: que horas são? → {{"resposta":"São 10 e 30, {cfg['tratamento']}.","acao":"nenhuma"}}

{self._contexto(pergunta)}"""

    # ------------------------------------------------------------------ processar
    def processar(self, pergunta: str) -> str:
        n = self.n
        if not n.ia or not n.ia.pronta:
            return "Ainda estou carregando a inteligência, " + n.cfg["tratamento"] + ". Tente de novo em alguns segundos."
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
        try:
            resposta = self._executar(acao, r, pergunta, resposta)
        except Exception:
            log.exception("falha ao executar %s", acao)
            resposta = "Não consegui concluir isso agora, " + n.cfg["tratamento"] + "."
        if not resposta:
            resposta = "Pronto."
        self.historico += [{"role": "user", "content": pergunta}, {"role": "assistant", "content": resposta}]
        self.historico = self.historico[-12:]
        return resposta

    def _executar(self, acao, r, pergunta, resposta):
        n, db, trat = self.n, self.n.db, self.n.cfg["tratamento"]
        if acao == "criar_lembrete":
            texto = (r.get("texto") or "").strip() or pergunta
            quando = textutil.parse_quando(r.get("quando", ""), agora(), pergunta)
            if not quando:
                return f"Para quando devo marcar, {trat}?"
            if quando < agora() - dt.timedelta(minutes=1):
                quando = textutil.parse_quando("", agora(), pergunta) or quando
            repetir = r.get("repetir") or ""
            db.lembrete_novo(quando, texto[:1].upper() + texto[1:], "voz", repetir)
            if not resposta:
                resposta = f"Lembrete marcado para {quando:%d/%m} às {quando:%H:%M}."
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
                return resposta or f"Lembrete \"{melhor['texto']}\" concluído."
            return f"Não achei esse lembrete, {trat}."
        if acao == "ler_tela":
            from . import tela
            n.mostrar_mini_seguro(False)
            time.sleep(0.4)
            texto = tela.ler_tela()
            if not texto:
                return f"Não consegui ler nada na tela, {trat}."
            msgs = [{"role": "system", "content":
                     "Você é a Mantiqueira. Responda em português do Brasil, em 1 a 3 frases curtas para serem "
                     "faladas, sem listas. Use o TEXTO DA TELA para responder ao pedido do usuário."},
                    {"role": "user", "content": f"TEXTO DA TELA:\n{texto}\n\nPEDIDO: {pergunta}"}]
            return n.ia.conversar(msgs, None, max_tokens=250).strip()
        return resposta
