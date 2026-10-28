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
    import tempfile
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
    pasta = Path(tempfile.mkdtemp())
    for nome in ("Mesa Luna Oval 2,80X1,20.SLDASM", "Poltrona Balanço Brisa.SLDASM", "Orçamento Cliente Silva.xlsx"):
        (pasta / "Projetos" / "Móveis").mkdir(parents=True, exist_ok=True)
        (pasta / "Projetos" / "Móveis" / nome).write_bytes(b"x")
    n.indice.varrer(str(pasta), "pc")
    it = Intencoes(n)
    relato = []
    for frase in ("procura no computador a mesa luna oval", "procura a mesa lunna ovl", "onde está o orçamento do silva",
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
