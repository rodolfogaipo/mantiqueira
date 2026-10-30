"""Teste rápido feito na máquina de montagem (sem placa de vídeo, sem microfone):
confere se as bibliotecas carregam, se a IA responde em JSON, se as vozes geram áudio e se o Whisper carrega.
Uso: <dist>\\python\\python.exe teste_fumaca.py <dist>"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DIST = Path(sys.argv[1]).resolve()
os.environ["MANTIQUEIRA_RAIZ"] = str(DIST)
os.environ["COQUI_TOS_AGREED"] = "1"
sys.path.insert(0, str(DIST / "app"))
falhas = []


def etapa(nome):
    def dec(fn):
        t = time.time()
        try:
            fn()
            print(f"[OK]   {nome} ({time.time() - t:.0f}s)", flush=True)
            print(f"::notice title=Teste OK::{nome} ({time.time() - t:.0f}s)", flush=True)
        except BaseException as e:
            import traceback
            tb = traceback.format_exc()
            print(tb, flush=True)
            print(f"[ERRO] {nome}: {e}", flush=True)
            msg = (tb[-3000:]).replace("%", "%25").replace("\r", "").replace("\n", "%0A")
            print(f"::error title=Teste {nome}::{msg}", flush=True)
            falhas.append(nome)
        return fn
    return dec


@etapa("bibliotecas")
def _():
    import torch, numpy, psutil, sounddevice, keyboard, webview, mss, vosk, faster_whisper  # noqa
    from TTS.tts.models.xtts import Xtts  # noqa
    import winsdk.windows.media.ocr  # noqa
    print("   torch", torch.__version__, "cuda compilado:", torch.version.cuda)


@etapa("módulos da Mantiqueira")
def _():
    from mantiqueira import config, db, textutil, sistema, ia, ouvido, voz, olhos, tela, cerebro, rotinas, nucleo, api  # noqa
    from mantiqueira import indice, leitor, sistemas_web, memoria, frases, intencoes, holo  # noqa
    import pystray  # noqa
    import playwright.sync_api  # noqa
    n = nucleo.Nucleo()                      # o mesmo que o programa faz ao abrir
    a = api.Api(n)
    e = a.estado()
    assert "boot" in e or "pronto" in e, e
    a.config()


@etapa("IA local responde em JSON")
def _():
    from mantiqueira import paths
    from mantiqueira.cerebro import ESQUEMA
    from mantiqueira.ia import PORTA, extrair_json
    p = subprocess.Popen([str(paths.LLAMA_CPU), "-m", str(paths.LLM_NORMAL), "--host", "127.0.0.1",
                          "--port", str(PORTA), "-c", "4096", "-ngl", "0"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(240):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/health", timeout=2) as r:
                    if b"ok" in r.read():
                        break
            except Exception:
                time.sleep(1)
        corpo = {"messages": [{"role": "system", "content": "Você é o Mantiqueira. AGORA: quarta-feira, 28 de outubro de 2026, 10:00. Responda em JSON com resposta, acao (nenhuma|criar_lembrete), quando (AAAA-MM-DD HH:MM) e texto."},
                              {"role": "user", "content": "me lembra amanhã às 9 de ligar pro fornecedor"}],
                 "max_tokens": 150, "temperature": 0.2,
                 "response_format": {"type": "json_object", "schema": ESQUEMA}}
        req = urllib.request.Request(f"http://127.0.0.1:{PORTA}/v1/chat/completions",
                                     data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = json.loads(r.read())["choices"][0]["message"]["content"]
        print("   resposta:", txt)
        print("::notice title=Resposta da IA::" + txt.replace("\n", " ")[:900], flush=True)
        dados = extrair_json(txt)
        assert dados.get("acao") == "criar_lembrete", dados
    finally:
        p.kill()


@etapa("voz rápida (Piper)")
def _():
    from mantiqueira import paths
    r = subprocess.run([str(paths.PIPER_EXE), "--model", str(paths.PIPER_VOZ), "--output_raw"],
                       input="Olá, senhor. Teste de voz.".encode("utf-8"), capture_output=True, timeout=120,
                       cwd=str(paths.PIPER_EXE.parent))
    assert len(r.stdout) > 10000, r.stderr.decode("utf-8", "replace")[-500:]


@etapa("voz natural (XTTS) gera áudio")
def _():
    import torch
    from mantiqueira import paths
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts
    cfg = XttsConfig()
    cfg.load_json(str(paths.XTTS / "config.json"))
    m = Xtts.init_from_config(cfg)
    m.load_checkpoint(cfg, checkpoint_dir=str(paths.XTTS), use_deepspeed=False, eval=True)
    nomes = list(m.speaker_manager.speakers.keys())
    print("   vozes:", len(nomes), nomes[:6])
    print("::notice title=Vozes XTTS::" + ", ".join(nomes)[:900], flush=True)
    sp = m.speaker_manager.speakers["Damien Black" if "Damien Black" in nomes else nomes[0]]
    with torch.inference_mode():
        out = m.inference("Olá, senhor.", "pt", sp["gpt_cond_latent"], sp["speaker_embedding"])
    assert len(out["wav"]) > 5000


@etapa("ouvido (Whisper + Vosk)")
def _():
    import numpy as np
    from mantiqueira.ouvido import Transcritor
    from mantiqueira import paths
    from vosk import Model
    Model(str(paths.VOSK))
    t = Transcritor()
    t.carregar()
    t.transcrever(np.zeros(16000, dtype=np.float32))


def pdf_simples(caminho, linhas):
    """Gera um PDF mínimo com texto (sem bibliotecas), para testar a leitura."""
    conteudo = "BT /F1 12 Tf 50 750 Td 16 TL " + " ".join(f"({l}) Tj T*" for l in linhas) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        pos.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{p:010d} 00000 n \n".encode() for p in pos)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(caminho).write_bytes(out)


@etapa("base de conhecimento (guias e PDF)")
def _():
    from mantiqueira import paths
    from mantiqueira.conhecimento import Conhecimento
    import pypdfium2  # noqa
    k = Conhecimento()
    assert k.fts, "busca de texto completo (FTS5) indisponível"
    k.importar_guias()
    guias = [d["nome"] for d in k.listar()]
    assert len(guias) >= 7, guias
    r = k.buscar("como exporto o dxf da chapa planificada no solidworks?")
    assert r and "SolidWorks" in r[0]["nome"], r
    pdf = paths.DADOS / "Tabela de dobra teste.pdf"
    pdf_simples(pdf, ["Tabela de dobra da empresa", "Chapa 2 mm aco carbono: raio interno 2 mm, fator K 0,42",
                      "Chapa 3 mm aco carbono: raio interno 3 mm, fator K 0,44"])
    nome, pag, tre = k.adicionar(pdf)
    assert tre >= 1, (nome, pag, tre)
    r = k.buscar("qual o fator K da chapa 3 mm?")
    assert r and "Tabela de dobra" in r[0]["nome"], r
    print("::notice title=Conhecimento::guias=" + ", ".join(guias) + " | PDF lido e encontrado: " +
          r[0]["texto"].replace("\n", " ")[:200], flush=True)


@etapa("holograma (STL, categorias) e áudio do celular")
def _():
    import struct
    import subprocess
    import numpy as np
    from mantiqueira import paths
    from mantiqueira.holo import ler_stl, categoria
    import comtypes.client  # noqa
    import imageio_ffmpeg
    # STL binário com 2 triângulos e o mesmo em texto
    tri = np.array([[0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 0, 0, 0, 1, 0, 0, 0, 1]], dtype=np.float32)
    b = paths.DADOS / "t.stl"
    with open(b, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", 2))
        for t in tri:
            f.write(struct.pack("<3f", 0, 0, 1) + t.tobytes() + b"\0\0")
    assert np.allclose(ler_stl(b), tri)
    a = paths.DADOS / "t_txt.stl"
    a.write_text("solid x\n" + "".join("facet normal 0 0 1\nouter loop\n" + "".join(
        f"vertex {t[i]} {t[i+1]} {t[i+2]}\n" for i in (0, 3, 6)) + "endloop\nendfacet\n" for t in tri) + "endsolid x\n")
    assert np.allclose(ler_stl(a), tri)
    cats = {categoria({"app": "SolidWorks", "arquivo": "Pergola.SLDASM"}): "montagem",
            categoria({"app": "Excel", "arquivo": "x.xlsx"}): "planilha",
            categoria({"app": "Aspire", "arquivo": ""}): "cnc", categoria(None): "familia"}
    for obtido, esperado in cats.items():
        assert obtido == esperado, (obtido, esperado)
    # áudio "do celular" (m4a gerado aqui) → voz
    m4a = paths.DADOS / "celular.m4a"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
                    "sine=frequency=180:duration=6", "-f", "lavfi", "-i", "anoisesrc=d=6:a=0.02",
                    "-filter_complex", "amix=inputs=2", "-c:a", "aac", str(m4a)], check=True, capture_output=True)
    from mantiqueira.voz import preparar_audio_voz
    seg = preparar_audio_voz(m4a, paths.DADOS / "voz_teste.wav")
    assert seg >= 3, seg
    print(f"::notice title=Holograma e voz::STL ok, categorias ok, áudio m4a convertido ({seg:.1f}s)", flush=True)


@etapa("busca de arquivos, memória e curiosidades")
def _():
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.indice import Indice
    from mantiqueira.memoria import Memoria
    from mantiqueira.frases import Frases
    from mantiqueira.intencoes import Intencoes

    class Falso:
        pass
    n = Falso()
    n.cfg = Config()
    n.db = Banco(paths.DADOS / "teste_intencoes.db")
    n.olhos = None
    n.sistemas = None
    n.detalhe_texto = ""
    n.contexto_extra = ""
    n.indice = Indice(n)
    n.memoria = Memoria(n)
    n.frases = Frases(n.db)
    pasta = paths.DADOS / "teste_busca"          # fora da pasta Temp do Windows, que o mapa ignora de propósito
    for nome in ("Mesa Luna Oval 2,80X1,20.SLDASM", "Poltrona Balanço Brisa.SLDASM", "Orçamento Cliente Silva.xlsx"):
        (pasta / "Projetos" / "Móveis").mkdir(parents=True, exist_ok=True)
        (pasta / "Projetos" / "Móveis" / nome).write_bytes(b"x")
    n.indice.varrer(str(pasta), "pc")
    it = Intencoes(n)
    relato = []
    for frase in ("procura a mesa luna oval", "procura a mesa lunna ovl", "onde está o orçamento do silva",
                  "me conta uma curiosidade sobre madeira", "preciso de uma frase motivacional"):
        r = it.tratar(frase, [])
        relato.append(f"{frase} → {r}")
        assert r, frase
    assert "Luna" in relato[0] and "Luna" in relato[1] and "Silva" in relato[2], relato
    n.memoria.adicionar("O Rodolfo trabalha com móveis de alumínio")
    r = it.tratar("o que você sabe sobre mim?", [])
    assert "alumínio" in n.detalhe_texto, n.detalhe_texto
    r2 = it.tratar("esquece que eu trabalho com móveis de alumínio", [])
    assert not n.memoria.todos(), r2
    relato += [f"memória → {r}", f"esquecer → {r2}"]
    print("\n".join(relato), flush=True)
    print("::notice title=Busca e memória::" + " %0A".join(x.replace("%", "%25") for x in relato)[:1500], flush=True)


@etapa("abrir só o que foi pedido, parar e procurar por lugar")
def _():
    import shutil
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.indice import Indice, NOMES
    from mantiqueira.memoria import Memoria
    from mantiqueira.frases import Frases
    from mantiqueira.intencoes import Intencoes
    import mantiqueira.intencoes as I
    abertos = []
    I.os.startfile = lambda c: abertos.append(c)
    class F: pass
    n = F(); n.cfg = Config(); n.db = Banco(paths.DADOS / "t141.db"); n.olhos = None; n.sistemas = None
    n.detalhe_texto = ""; n.contexto_extra = ""; n.parar_fala = lambda: abertos.append("PAROU"); n.cerebro = None
    n.indice = Indice(n); n.memoria = Memoria(n); n.frases = Frases(n.db)
    base = paths.DADOS / "t141"; shutil.rmtree(base, ignore_errors=True)
    arqs = {"C": ["Mesa Luna Oval.SLDASM", "Mesa Luna Oval.pdf", "Orcamento Silva.xlsx"],
            "Y": ["Mesa Luna Oval.pdf", "Banqueta Miches.SLDPRT"],
            "Z": ["Mesa Luna Oval.SLDASM", "Poltrona Brisa.pdf"]}
    for d, lst in arqs.items():
        (base / d / "Projetos").mkdir(parents=True)
        for a in lst: (base / d / "Projetos" / a).write_bytes(b"x")
        n.indice.varrer(str(base / d), "x")
        origem = "pc" if d == "C" else "rede"
        n.indice.con.execute("UPDATE arq SET raiz=?, origem=? WHERE raiz=?", (d + ":\\", origem, str(base / d))); n.indice.con.commit()
    NOMES.update({"Y:\\": "File_Aluminas", "Z:\\": "File-Projetos"})
    n.indice.locais = lambda: [("C:\\", "pc", ""), ("Y:\\", "rede", "File_Aluminas"), ("Z:\\", "rede", "File-Projetos")]
    it = Intencoes(n)
    relato = []
    def t(fr):
        abertos.clear(); r = it.tratar(fr, [])
        relato.append(f"{fr} → {r} {[os.path.basename(a) for a in abertos]}")
        return r
    assert "Qual deles" in t("abre o pdf da mesa luna oval") and not abertos
    t("o primeiro"); assert abertos and abertos[0].endswith(".pdf")
    t("abre o pdf da mesa luna oval no computador"); assert len(abertos) == 1 and abertos[0].endswith(".pdf")
    t("abre a montagem da mesa luna no file projetos"); assert abertos and "Z" in abertos[0] and abertos[0].endswith(".SLDASM")
    assert "Aluminas" in t("procura no aluminas a banqueta miches")
    assert "Não encontrei" in t("procura no file projetos a banqueta miches")
    assert "Não encontrei" in t("procura no computador banqueta miches")
    for fr in ("não", "para", "cancela", "não quero"):
        assert t(fr).startswith("Ok") and abertos == ["PAROU"], fr
    assert t("tudo bem com você?") is None
    print("\n".join(relato), flush=True)
    print("::notice title=Abrir, parar e lugares::" + " %0A".join(x.replace("%", "%25") for x in relato)[:1500], flush=True)



@etapa("sons, voz, silêncio, apelidos e aviso de CNP")
def _():
    import datetime as dt
    import shutil
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.indice import Indice, NOMES
    from mantiqueira.memoria import Memoria
    from mantiqueira.frases import Frases
    from mantiqueira.intencoes import Intencoes
    from mantiqueira.sistemas_web import SistemasWeb
    import mantiqueira.intencoes as I
    abertos = []
    I.os.startfile = lambda c: abertos.append(c)

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_142.db"); n.olhos = None; n.sistemas = None
    n.detalhe_texto = ""; n.contexto_extra = ""; n.parar_fala = lambda: None; n.cerebro = None; n.ultima_fala = "Teste."
    n.liberar_silenciados = lambda: None
    n.indice = Indice(n); n.memoria = Memoria(n); n.frases = Frases(n.db)
    base = paths.DADOS / "teste_142"
    shutil.rmtree(base, ignore_errors=True)
    (base / "Projetos" / "Poltrona Brisa").mkdir(parents=True)
    (base / "Projetos" / "Poltrona Brisa" / "Brisa.SLDASM").write_bytes(b"x")
    n.indice.varrer(str(base), "rede")
    n.indice.con.execute("UPDATE arq SET raiz=? WHERE raiz=?", ("Q:\\", str(base)))
    n.indice.con.commit()
    NOMES.update({"Q:\\": "File-Teste"})
    n.indice.locais = lambda: [("C:\\", "pc", ""), ("Q:\\", "rede", "File-Teste")]
    it = Intencoes(n)
    relato = []

    def t(fr):
        abertos.clear()
        r = it.tratar(fr, [])
        relato.append(f"{fr} → {r}")
        return r
    assert t("repete") == "Teste."
    t("desliga o bip"); assert n.cfg["som_bip"] is False and n.cfg["som_lembrete"] is True
    t("tira o som do aviso"); assert n.cfg["som_lembrete"] is False
    t("liga o bip"); t("liga o sinal do lembrete"); assert n.cfg["som_bip"] and n.cfg["som_lembrete"]
    t("fala mais baixo"); assert n.cfg["voz_volume"] < 1
    t("volume normal"); assert n.cfg["voz_volume"] == 1
    t("modo silencioso por 30 minutos"); assert 25 * 60 < n.cfg["silencio_ate"] - time.time() < 35 * 60
    t("pode falar"); assert n.cfg["silencio_ate"] == 0
    t("quando eu falar pasta da brisa, abre a pasta poltrona brisa no file teste")
    t("abre a pasta da brisa"); assert abertos and abertos[0].endswith("Poltrona Brisa"), abertos
    assert "mudou" in t("o que mudou na pasta poltrona brisa hoje")
    t("apaga o apelido pasta da brisa")
    falas = []
    n.falar_aviso = falas.append
    for r in n.db.q("SELECT chave FROM kv WHERE chave LIKE 'cnp%'"):
        n.db.x("DELETE FROM kv WHERE chave=?", (r["chave"],))
    sw = SistemasWeb(n)
    am = (dt.date.today() + dt.timedelta(days=1)).strftime("%d/%m/%Y")
    dados = {"login": False, "cab": ["ID", "Produto", "Pedido", "Data Prevista"], "paginas": 1, "hora": "10:00",
             "linhas": [["101", "Mesa Luna", "5501", "10/11/2030"]]}
    sw.ler = lambda s, cache_seg=180: dados
    s = sw.lista()[0]
    sw._conferir(s); assert not falas
    dados["linhas"].append(["102", "Banqueta Miches", "5502", am])
    sw._conferir(s); sw._conferir(s)
    assert len(falas) == 2 and "Banqueta" in falas[0] and "amanhã" in falas[1], falas
    relato += falas
    print("\n".join(relato), flush=True)
    print("::notice title=Novidades 1.4.2::" + " %0A".join(x.replace("%", "%25") for x in relato)[:1500], flush=True)


@etapa("saudação de abertura (bem-vindo de volta)")
def _():
    import numpy as np
    from mantiqueira.config import Config
    from mantiqueira import saudacao, nucleo

    class VozFalsa:
        def voz_padrao(self):
            return "xtts:teste"

        def gerar_audio(self, texto, voz_id=None):
            t = np.arange(24000) / 24000
            return (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 24000
    cfg = Config()
    for f in (saudacao.WAV, saudacao.META):
        try:
            f.unlink()
        except FileNotFoundError:
            pass
    assert not saudacao.pronta(cfg)
    assert saudacao.gravar(VozFalsa(), cfg) and saudacao.pronta(cfg)
    assert not saudacao.precisa_gravar(cfg, "xtts:teste")
    tocou = saudacao.tocar(cfg, esperar=True)
    travada = nucleo.Nucleo._tela_travada()
    print(f"::notice title=Saudação::gravada ok, tocou={tocou}, tela travada={travada}", flush=True)


@etapa("'achou?' e 'abre ele' (conversa de busca)")
def _():
    import shutil
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.indice import Indice
    from mantiqueira.memoria import Memoria
    from mantiqueira.frases import Frases
    from mantiqueira.intencoes import Intencoes
    import mantiqueira.intencoes as I
    abertos = []
    I.os.startfile = lambda c: abertos.append(c)

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_143.db"); n.olhos = None; n.sistemas = None
    n.detalhe_texto = ""; n.contexto_extra = ""; n.parar_fala = lambda: None; n.cerebro = None; n.ultima_fala = ""
    n.indice = Indice(n); n.memoria = Memoria(n); n.frases = Frases(n.db)
    base = paths.DADOS / "teste_143"
    shutil.rmtree(base, ignore_errors=True)
    d = base / "Projetos Rodolfo" / "MESA LUNA OVAL 2,80X1,20" / "IMPRESSOS"
    d.mkdir(parents=True)
    for a in ("MESA LUNA OVAL 2,80X1,20.pdf", "MESA LUNA OVAL 2,80X1,20.SLDDRW"):
        (d / a).write_bytes(b"x")
    n.indice.varrer(str(base), "pc")
    n.indice.con.execute("UPDATE arq SET raiz=? WHERE raiz=?", ("C:\\", str(base)))
    n.indice.con.commit()
    n.indice.locais = lambda: [("C:\\", "pc", "")]
    it = Intencoes(n)
    r1 = it.tratar("O PDF ESTA NO COMPUTADOR MESA LUNA OVAL 2,80X1,20", [])
    r2 = it.tratar("ACHOU?", [])
    r3 = it.tratar("ENTÃO ABRA ELE", [])
    assert "Achei" in r1 and "Sim" in r2 and abertos and abertos[-1].endswith("2,80X1,20.pdf"), (r1, r2, r3, abertos)
    print(f"::notice title=Conversa de busca::{r1} %0A{r2} %0A{r3}", flush=True)


@etapa("respostas exatas: CNPs e planilha por data")
def _():
    import datetime as dt
    from mantiqueira.config import Config
    from mantiqueira.sistemas_web import SistemasWeb
    from mantiqueira import leitor

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.detalhe_texto = ""
    sw = SistemasWeb(n)
    ontem = (dt.date.today() - dt.timedelta(days=1)).strftime("%d/%m/%Y")
    cab = ["ID", "Produto", "Pedido", "Linha", "Carga", "Qtd Peças", "Data Prevista", "Aprovação Gerência", "Setores",
           "Status Geral", "Criado por", "Data Criação", "Ações"]
    linhas = [["952", "banqueta miches Similar: banqueta pora", "121861", "banqueta", "-", "6", "07/12/2026",
               ontem + " 15:06", "TUBULAR: pendente", "em análise pcp", "Ana Laura Alves Ribeiro", ontem + " 14:56", ""],
              ["951", "poltrona miches Similar: poltrona pora", "121861", "poltrona", "-", "8", "07/12/2026",
               ontem + " 15:05", "TUBULAR: pendente", "em análise pcp", "Ana Laura Alves Ribeiro", ontem + " 14:55", ""]]
    d = {"cab": cab, "linhas": linhas, "hora": "08:00", "paginas": 1}
    s = sw.lista()[0]
    r = [sw.responder(s, d, q) for q in ("BANQUETA MICHES NA ORIGUS QUAL DIA PREVISTA?", "qual o pedido da poltrona miches",
                                          "quais cnps foram criados ontem", "quem criou o cnp da banqueta miches")]
    assert "07/12/2026" in r[0] and "banqueta" in r[0] and "15:06" not in r[0], r[0]
    assert "121861" in r[1] and "poltrona" in r[1], r[1]
    assert r[2].startswith("2 CNPs criados"), r[2]
    assert "Ana Laura" in r[3], r[3]
    lin = [["CONTROLE", "", ""], ["Semana", "Data", "Projetos"]]
    for k in range(1, 40):
        lin.append([str(k), (dt.date(2026, 1, 4) + dt.timedelta(weeks=k - 1)).strftime("%d/%m/%Y"), str(100 + k)])
    leitor.planilhas_abertas = lambda: {("CONTROLE_EQUIPE.xlsx", "Máyra"): {"linhas": lin, "lin0": 1, "col0": 1, "ativa": True}}
    t = "\n".join(leitor.trechos_planilhas("quantos projetos a mayra fez na semana de 23-08-2026"))
    assert "LINHA EXATA" in t and "Data=23/08/2026" in t and "Data=16/08/2026" not in t, t
    sw.ultimos["CNPs"] = d
    assert sw.citado_sem_nome("quando a banqueta miches foi criada?") is not None
    assert sw.citado_sem_nome("quando o pedido 121861 foi criado") is not None
    assert sw.citado_sem_nome("tudo bem com você?") is None
    assert "28/10" in sw.responder(s, d, "quando a banqueta miches foi gerada?") or ontem[:5] in sw.responder(s, d, "quando a banqueta miches foi gerada?")

    def aba(base):
        lin = [["CONTROLE"], ["Semana", "Data", "Projetos", "Nota"]]
        for k in range(1, 40):
            lin.append([str(k), (dt.date(2026, 1, 4) + dt.timedelta(weeks=k - 1)).strftime("%d/%m/%Y"),
                        str(base + k) if k < 36 else "-", str(base // 2 + k % 5) if k < 36 else "0,0"])
        return lin
    leitor.planilhas_abertas = lambda: {("CE.xlsx", "Máyra"): {"linhas": aba(100), "lin0": 1, "col0": 1, "ativa": True},
                                        ("CE.xlsx", "Leandrinho"): {"linhas": aba(180), "lin0": 1, "col0": 1, "ativa": False},
                                        ("CE.xlsx", "CADASTRO DE SERVIÇOS"): {"linhas": [["Serviço", "Nota"], ["a", "999"], ["b", "1"]],
                                                                              "lin0": 1, "col0": 1, "ativa": False}}
    rk = leitor.ranking_planilhas("quem é o melhor projetista?")
    assert rk and "Leandrinho" in rk[0].split(".")[0], rk
    rk2 = leitor.ranking_planilhas("quem é o pior projetista?")
    assert rk2 and "Máyra" in rk2[0].split(".")[0], rk2
    r += [rk[0], rk2[0]]
    print("::notice title=Respostas exatas::" + " %0A".join(x.replace("%", "%25") for x in r + [t.splitlines()[-1]])[:1500], flush=True)


@etapa("leitura do sistema de CNPs pelo navegador (página de teste)")
def _():
    from mantiqueira.config import Config
    from mantiqueira.sistemas_web import SistemasWeb

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.detalhe_texto = ""; n.falar_aviso = lambda t: None
    sw = SistemasWeb(n)
    pagina = Path(__file__).with_name("teste_cnps.html").resolve().as_uri()
    s = {"nome": "Teste", "url": pagina, "palavras": "cnp"}
    t0 = time.time()
    d = sw.ler(s, cache_seg=0)
    assert not d.get("login") and len(d["linhas"]) == 22, (d.get("login"), len(d.get("linhas") or []))
    assert d["linhas"][0][0] == "952" and d["linhas"][0][6] == "07/12/2026", d["linhas"][0]
    r = sw.responder(s, d, "qual a data prevista da banqueta miches")
    assert "07/12/2026" in r, r
    print(f"::notice title=Navegador do sistema::{len(d['linhas'])} CNPs em {d['paginas']} páginas, {time.time() - t0:.0f}s — {r}", flush=True)


@etapa("agenda: pedidos em várias formas viram lembretes certos")
def _():
    import datetime as dt
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.cerebro import Cerebro

    class IAFalsa:
        pronta = True

        def conversar(self, msgs, esquema, max_tokens=0):
            return {"resposta": "(IA)", "acao": "nenhuma"}

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_agenda.db"); n.ia = IAFalsa(); n.olhos = None; n.latencia = None
    n.detalhe_texto = ""; n.contexto_extra = ""; n.mostrar_mini_seguro = lambda *a, **k: None
    n.db.x("DELETE FROM lembretes")
    c = Cerebro(n)
    casos = [("coloca na agenda reunião com a equipe amanhã às 10", "Reunião com a equipe", 1, 10, 0),
             ("me lembra de ligar pro fornecedor", None, None, None, None),
             ("amanhã às 9", "Ligar pro fornecedor", 1, 9, 0),
             ("agenda pra mim dentista amanhã 15h", "Dentista", 1, 15, 0),
             ("me lembra amanhã às 7:15 de ir à marcenaria", "Ir à marcenaria", 1, 7, 15),
             ("não deixa eu esquecer de pagar o boleto amanhã às 8", "Pagar o boleto", 1, 8, 0),
             ("preciso que você me lembre de mandar o orçamento amanhã 16h", "Mandar o orçamento", 1, 16, 0)]
    relato = []
    for frase, texto, dias, h, mi in casos:
        r = c.processar(frase)
        relato.append(f"{frase} → {r}")
        if texto:
            l = [x for x in n.db.lembretes_proximos(50) if x["texto"] == texto]
            assert l, (frase, r, [x["texto"] for x in n.db.lembretes_proximos(50)])
            q = dt.datetime.fromisoformat(l[0]["quando"].replace(" ", "T"))
            assert q.date() == dt.date.today() + dt.timedelta(days=dias) and (q.hour, q.minute) == (h, mi), (frase, q)
        else:
            assert "Para quando" in r, r
    r = c.processar("o que tenho pra amanhã?")
    assert "Reunião com a equipe" in r and "Dentista" in r, r
    print("::notice title=Agenda::" + " %0A".join(x.replace("%", "%25") for x in relato)[:1500], flush=True)


@etapa("CNP: continuar o assunto ('e da poltrona?', 'e o pedido dela?')")
def _():
    import datetime as dt
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.sistemas_web import SistemasWeb
    from mantiqueira.intencoes import Intencoes

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_cnp_conv.db"); n.detalhe_texto = ""; n.contexto_extra = ""
    n.indice = None; n.olhos = None; n.memoria = None; n.frases = None; n.parar_fala = lambda: None; n.cerebro = None
    n.ultima = {}; n.voz = None; n.em_silencio = lambda: False
    cab = ["ID", "Produto", "Pedido", "Linha", "Carga", "Qtd Peças", "Data Prevista", "Aprovação Gerência", "Setores",
           "Status Geral", "Criado por", "Data Criação", "Ações"]
    d = {"login": False, "cab": cab, "hora": "16:00", "paginas": 1, "linhas": [
        ["952", "banqueta miches Similar: banqueta pora", "121861", "banqueta", "-", "6", "07/12/2026", "28/10/2026 15:06",
         "TUBULAR: pendente", "em análise pcp", "Ana Laura Alves Ribeiro", "28/10/2026 14:56", ""],
        ["943", "SOFÁ ARGENTINA Similar: SOFÁ ARGENTINA", "121595", "ARGENTINA", "-", "1", "-", "26/10/2026 13:01",
         "TUBULAR: pendente", "em análise pcp", "Laura Vitória Porto Martins", "23/10/2026 09:25", ""]]}
    n.sistemas = sw = SistemasWeb(n)
    sw.ler = lambda s, cache_seg=180: d
    sw.ultimos["CNPs"] = d
    it = Intencoes(n)
    r1 = it.tratar("qual a data prevista da banqueta miches?", [])
    r2 = it.tratar("e do sofá argentina?", [])
    r3 = it.tratar("e o pedido dela?", [])
    r4 = it.tratar("quem criou?", [])
    r5 = it.tratar("quando o sofá argentina foi criado?", [])
    assert "07/12/2026" in r1 and "ARGENTINA" in r2 and "121595" in r3 and "Laura Vitória" in r4 and "23/10/2026" in r5, \
        (r1, r2, r3, r4, r5)
    outra = it.tratar("qual o melhor projetista?", [])
    assert not outra or "CNP" not in outra, outra
    print("::notice title=CNP conversa::" + " %0A".join([r1, r2, r3, r4, r5]), flush=True)


@etapa("sistema de CNPs igual ao Órigus (DataTables no servidor): lê todos os registros")
def _():
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler
    from urllib.parse import urlparse, parse_qs
    from mantiqueira.config import Config
    from mantiqueira.sistemas_web import SistemasWeb
    pasta = Path(__file__).with_name("teste_dt")
    dados = []
    for i in range(865):
        id_ = 970 - i
        dados.append({"id": id_, "produto": "banqueta miches" if id_ == 952 else f"PRODUTO {id_}", "similar": "",
                      "pedido": 121861 if id_ == 952 else 120000 + i, "linha": "banqueta", "carga": None, "qtd": 6,
                      "dataPrevista": "2026-12-07T12:00:00" if id_ == 952 else None, "aprovacao": "2026-10-28T15:06:00",
                      "setores": [{"nome": "TUBULAR", "st": "pendente"}], "status": "em análise pcp",
                      "criadoPor": {"nome": "Ana Laura Alves Ribeiro"}, "dataCriacao": "2026-10-28T14:56:00"})

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(pasta), **k)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/cnp/cnps" and "draw" in u.query:
                q = parse_qs(u.query)
                ini, tam = int(q.get("start", ["0"])[0]), min(100, int(q.get("length", ["15"])[0]))   # servidor limita a 100
                corpo = json.dumps({"draw": int(q["draw"][0]), "recordsTotal": len(dados), "recordsFiltered": len(dados),
                                    "data": dados[ini:ini + tam]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(corpo)
                return
            if u.path == "/cnp/cnps":
                self.path = "/pagina.html"
            return super().do_GET()

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 18799), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.detalhe_texto = ""; n.falar_aviso = lambda t: None
    sw = SistemasWeb(n)
    s = {"nome": "CNPs", "url": "http://127.0.0.1:18799/cnp/cnps", "palavras": "cnp"}
    try:
        d = sw.ler(s, cache_seg=0)
    finally:
        srv.shutdown()
    assert len(d["linhas"]) == 865, len(d["linhas"])
    r = sw.responder(s, d, "que dia foi cadastrado a banqueta miches")
    assert "28/10/2026" in r and "banqueta" in r, r
    r2 = sw.responder(s, d, "qual a data prevista da banqueta miches")
    assert "07/12/2026" in r2, r2
    print(f"::notice title=Sistema igual ao Órigus::{len(d['linhas'])} registros lidos — {r} %0A{r2}", flush=True)


@etapa("CNP: contagens e períodos (criados/aprovados hoje, ontem, do dia X até hoje)")
def _():
    import datetime as dt
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.sistemas_web import SistemasWeb
    from mantiqueira.intencoes import Intencoes
    H = dt.date.today()

    def f(d):
        return d.strftime("%d/%m/%Y") + " 10:00"
    cab = ["ID", "Produto", "Pedido", "Linha", "Carga", "Qtd Peças", "Data Prevista", "Aprovação Gerência", "Setores",
           "Status Geral", "Criado por", "Data Criação", "Ações"]
    L = []

    def add(id_, prod, criado, aprov=None):
        L.append([str(id_), prod, "1219" + str(id_), "X", "-", "1", "-", f(aprov) if aprov else "", "", "em analise pcp",
                  "Janaína Ferreira", f(criado), "editcheck"])
    add(972, "BANCO HOJE A", H, H)
    add(971, "BANCO HOJE B", H)
    for i in range(5):
        add(966 - i, f"MESA ONTEM {i}", H - dt.timedelta(days=1), H - dt.timedelta(days=1) if i < 3 else None)
    add(960, "SOFA ANTEONTEM", H - dt.timedelta(days=2), H)
    for i in range(300):
        add(900 - i, f"PRODUTO {i}", H - dt.timedelta(days=200), H - dt.timedelta(days=199))
    d = {"login": False, "cab": cab, "linhas": L, "hora": "08:30", "paginas": 1}

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_periodo.db"); n.detalhe_texto = ""; n.contexto_extra = ""
    n.indice = None; n.olhos = None; n.memoria = None; n.frases = None; n.parar_fala = lambda: None; n.cerebro = None
    n.ultima = {}; n.voz = None; n.em_silencio = lambda: False
    n.sistemas = sw = SistemasWeb(n)
    sw.ler = lambda s, cache_seg=180: d
    sw.ultimos["CNPs"] = d
    it = Intencoes(n)
    dia = (H - dt.timedelta(days=2)).strftime("%d/%m")
    r = {q: it.tratar(q, []) for q in [
        "quantas cnp foram cadastradas ontem?", "quantas cnps foram criadas?", "tem mais alguma cnp nova criada hoje?",
        "quantas cnps foram aprovadas pela gerência hoje?", f"quais cnps foram aprovadas pela gerência do dia {dia} até hoje?"]}
    v = list(r.values())
    assert v[0].startswith("5 CNPs criados ontem"), v[0]
    assert "tem 308 CNPs" in v[1], v[1]
    assert v[2].startswith("2 CNPs criados hoje"), v[2]
    assert v[3].startswith("2 CNPs aprovados pela gerência hoje"), v[3]
    assert v[4].startswith("5 CNPs aprovados pela gerência de"), v[4]
    print("::notice title=CNP períodos::" + " %0A".join(f"{q} → {a[:120]}" for q, a in r.items()), flush=True)


@etapa("pastas: 'quantas pastas tem no File Projetos?' e 'o que tem na Engenharia?'")
def _():
    import shutil
    from mantiqueira import paths
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.indice import Indice, NOMES
    from mantiqueira.intencoes import Intencoes

    class Falso:
        pass
    n = Falso()
    n.cfg = Config(); n.db = Banco(paths.DADOS / "teste_pastas.db"); n.olhos = None; n.sistemas = None; n.detalhe_texto = ""
    n.contexto_extra = ""; n.parar_fala = lambda: None; n.cerebro = None; n.memoria = None; n.frases = None
    n.indice = Indice(n)
    Z = paths.DADOS / "teste_unidade_z"
    shutil.rmtree(Z, ignore_errors=True)
    for d in ["ATELIÊ", "CHINESA", "ENGENHARIA", "Nova pasta", "ENGENHARIA/2026", "ENGENHARIA/LASER", "ATELIÊ/TESTE MÁYRA"]:
        (Z / d).mkdir(parents=True, exist_ok=True)
    (Z / "Captura de tela.png").write_bytes(b"x")
    raiz = str(Z) + os.sep
    NOMES[raiz] = "File-Projetos"
    n.indice.locais = lambda: [(raiz, "rede", "File-Projetos")]
    it = Intencoes(n)
    r1 = it.tratar("no file projetos tem quantas pastas na aba inicial?", [])
    r2 = it.tratar("na engenharia no file projetos tem quais pastas inicialmente?", [])
    assert "4 pastas" in r1 and "ENGENHARIA" in r1 and "um arquivo" in r1, r1
    assert "2 pastas" in r2 and "LASER" in r2, r2
    import mantiqueira.intencoes as I
    abertos = []
    I.os.startfile = lambda c: abertos.append(c)
    for d, f in [("ENGENHARIA/PROJETOS/MESA LUNA", "MESA LUNA OVAL.pdf"), ("ENGENHARIA/PROJETOS/MESA LUNA", "MESA LUNA OVAL.SLDASM"),
                 ("ENGENHARIA/LASER", "MESA LUNA OVAL.dxf"), ("ATELIÊ/PROJETOS", "MESA LUNA OVAL.pdf")]:
        (Z / d).mkdir(parents=True, exist_ok=True)
        (Z / d / f).write_bytes(b"x")
    n.indice.varrer(raiz, "rede")
    r3 = it.tratar("abre o pdf da mesa luna oval que está dentro de engenharia na pasta projetos no file projetos", [])
    assert abertos and abertos[-1].replace("\\", "/").endswith("ENGENHARIA/PROJETOS/MESA LUNA/MESA LUNA OVAL.pdf"), (r3, abertos)
    r4 = it.tratar("abre a mesa luna oval na pasta laser", [])
    assert abertos[-1].endswith(".dxf"), (r4, abertos)
    print(f"::notice title=Pastas::{r1} %0A{r2} %0A{r3} %0A{r4}", flush=True)


@etapa("conversas de teste (secretário)")
def _():
    import datetime as dt
    from mantiqueira import paths
    from mantiqueira.ia import IA, PORTA
    from mantiqueira.config import Config
    from mantiqueira.db import Banco
    from mantiqueira.cerebro import Cerebro

    class Falso:
        pass
    n = Falso()
    n.cfg = Config()
    n.cfg.atualizar({"tratamento": "senhor", "nome": "Rodolfo"})
    n.db = Banco(paths.DADOS / "teste_conversa.db")
    n.olhos = None
    n.latencia = None
    n.mostrar_mini_seguro = lambda *a, **k: None
    n.ia = IA(n)
    p = subprocess.Popen([str(paths.LLAMA_CPU), "-m", str(paths.LLM_NORMAL), "--host", "127.0.0.1",
                          "--port", str(PORTA), "-c", "8192", "-ngl", "0"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(240):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/health", timeout=2) as r:
                    if b"ok" in r.read():
                        break
            except Exception:
                time.sleep(1)
        n.ia.pronta = True
        c = Cerebro(n)
        relato = []

        def diz(frase):
            r = c.processar(frase)
            lem = n.db.lembretes_proximos(20)
            relato.append(f"VOCÊ: {frase} → MANTIQUEIRA: {r} [lembretes: {len(lem)}; trato: {n.cfg['tratamento']}]")
            return r, lem

        diz("fale Leandrinho vá trabalhar")
        diz("me chame de doutor")
        diz("tudo bem com você?")
        diz("me lembra de ligar pro fornecedor")
        r, lem = diz("amanhã às 9")
        diz("me lembra daqui a 10 minutos de tirar o café")
        diz("tenho uma reunião sexta")
        from mantiqueira.conhecimento import Conhecimento
        n.conhecimento = Conhecimento()
        n.conhecimento.importar_guias()
        diz("qual o atalho da vista isométrica no SolidWorks?")
        diz("como apago linhas duplicadas no AutoCAD antes de mandar pro laser?")
        for l in n.db.lembretes_proximos(20):
            relato.append(f"LEMBRETE: {l['quando']} — {l['texto']} {l['repetir']}")
        texto = " %0A".join(x.replace("%", "%25").replace("\n", " ") for x in relato)
        print("\n".join(relato), flush=True)
        print("::notice title=Conversas de teste::" + texto[:3800], flush=True)
    finally:
        p.kill()


if falhas:
    print("FALHAS:", falhas)
    sys.exit(1)
print("TUDO OK")
