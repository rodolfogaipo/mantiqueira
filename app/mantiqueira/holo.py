"""Holograma: decide o que mostrar no painel 'EM FOCO' e, no SolidWorks, exporta a peça aberta em 3D.

A exportação usa a interface oficial do SolidWorks (a mesma das macros): pede uma cópia em STL do documento
ativo, sem alterar o arquivo. Só acontece quando o documento muda ou é salvo, e há limites de tamanho/tempo
para nunca pesar — acima deles o painel mostra uma ilustração no lugar."""
import os
import time
import struct
import hashlib
import logging
import threading
import numpy as np
from . import paths, sistema

log = logging.getLogger("holo")
PASTA_UI = paths.UI / "_holo"
PASTA_TMP = paths.DADOS / "holo_tmp"
MAX_TRIANGULOS = 160_000
MAX_SEGUNDOS = 12
MAX_MB_STL = 40

CATEGORIA_APP = {
    "AutoCAD": "cad2d", "SketchUp": "movel", "3ds max": "movel", "3dsmax": "movel", "Rhino": "peca", "Inventor": "peca",
    "Aspire": "cnc", "VCarve": "cnc", "CypCut": "laser", "CypNest": "laser",
    "Excel": "planilha", "Word": "documento", "PowerPoint": "documento", "Acrobat": "documento",
    "Chrome": "globo", "Edge": "globo", "Firefox": "globo", "Opera": "globo",
    "Explorador": "pasta", "WhatsApp": "mensagem", "Outlook": "mensagem", "Teams": "mensagem",
    "eDrawings": "peca",
}


def categoria(foco):
    """Ilustração para o programa/arquivo em uso."""
    if not foco:
        return "familia"
    app = (foco.get("app") or "")
    arq = (foco.get("arquivo") or "").lower()
    proc = (foco.get("processo") or "").lower()
    if app == "SolidWorks" or proc == "sldworks.exe":
        if arq.endswith(".sldasm"):
            return "montagem"
        if arq.endswith(".slddrw"):
            return "desenho"
        if "chapa" in arq or "sheet" in arq:
            return "chapa"
        return "peca"
    if arq.endswith(".pdf"):
        return "documento"
    if arq.endswith((".dxf", ".dwg")):
        return "cad2d"
    for nome, cat in CATEGORIA_APP.items():
        if nome.lower() in app.lower() or nome.lower().replace(" ", "") in proc:
            return cat
    return "logo"


def ler_stl(caminho):
    """Lê STL binário ou texto e devolve um array float32 (n_triângulos, 9)."""
    with open(caminho, "rb") as f:
        dados = f.read()
    if len(dados) >= 84:
        n = struct.unpack_from("<I", dados, 80)[0]
        if 84 + n * 50 == len(dados):
            reg = np.frombuffer(dados, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", 9), ("a", "<u2")]), count=n, offset=84)
            return np.array(reg["v"], dtype=np.float32)
    txt = dados.decode("ascii", "ignore")
    vals = [float(x) for linha in txt.splitlines() if linha.strip().startswith("vertex") for x in linha.split()[1:4]]
    return np.array(vals, dtype=np.float32).reshape(-1, 9)


class Holo:
    def __init__(self, nucleo):
        self.n = nucleo
        self.atual = None          # {"tipo": "real"|categoria, "url":..., "chave":...}
        self._doc_chave = None
        self._ocupado = False
        self._falhas = {}
        PASTA_UI.mkdir(parents=True, exist_ok=True)
        PASTA_TMP.mkdir(parents=True, exist_ok=True)
        for f in PASTA_UI.glob("*.bin"):
            try:
                f.unlink()
            except Exception:
                pass

    def estado(self, foco, inativo):
        """Chamado pela tela: o que o painel deve mostrar agora."""
        if inativo or not foco:
            return {"tipo": "familia", "chave": "familia"}
        cat = categoria(foco)
        if cat in ("peca", "montagem", "chapa") and self.n.cfg["holo_real"]:
            chave = (foco.get("arquivo") or "") + ("*" if foco.get("nao_salvo") else "")
            if self.atual and self.atual.get("arquivo") == foco.get("arquivo") and self.atual.get("tipo") == "real":
                if chave != self._doc_chave and not foco.get("nao_salvo") and not self._ocupado:
                    self._exportar_async(foco)       # foi salvo de novo: atualizar
                self._doc_chave = chave
                return self.atual
            if not self._ocupado and self._falhas.get(foco.get("arquivo"), 0) < 2:
                self._doc_chave = chave
                self._exportar_async(foco)
        return {"tipo": cat, "chave": cat}

    def _exportar_async(self, foco):
        self._ocupado = True
        threading.Thread(target=self._exportar, args=(dict(foco),), daemon=True, name="holo").start()

    def _exportar(self, foco):
        arquivo = foco.get("arquivo") or ""
        try:
            import comtypes
            import comtypes.client as cc
            comtypes.CoInitialize()
            try:
                sw = cc.GetActiveObject("SldWorks.Application", dynamic=True)
                doc = sw.ActiveDoc
                if doc is None:
                    return
                tipo = doc.GetType()              # 1 peça, 2 montagem, 3 desenho
                titulo = str(doc.GetTitle() or "")
                if tipo not in (1, 2):
                    return
                if arquivo and os.path.splitext(arquivo)[0].lower() not in titulo.lower():
                    return                        # o documento ativo mudou
                if tipo == 2:
                    try:
                        if doc.GetComponentCount(False) > 400:
                            log.info("montagem grande demais para o holograma")
                            self._falhas[arquivo] = 9
                            return
                    except Exception:
                        pass
                base = PASTA_TMP / ("m_" + hashlib.md5(titulo.encode("utf-8")).hexdigest()[:10])
                for f in PASTA_TMP.glob("*.stl"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
                t0 = time.time()
                destino = str(base) + ".stl"
                erro = doc.SaveAs3(destino, 0, 3)  # versão atual, silencioso + salvar cópia (não muda o documento)
                dur = time.time() - t0
                log.info("STL exportado em %.1fs (código %s)", dur, erro)
                if dur > MAX_SEGUNDOS:
                    self._falhas[arquivo] = 9     # lento demais: não repetir para este arquivo
            finally:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
            arquivos = sorted(PASTA_TMP.glob(base.name + "*.stl"))
            if not arquivos:
                raise RuntimeError("o SolidWorks não gerou o STL")
            if sum(f.stat().st_size for f in arquivos) > MAX_MB_STL * 2**20:
                self._falhas[arquivo] = 9
                return
            tri = np.concatenate([ler_stl(f) for f in arquivos])
            if len(tri) == 0:
                raise RuntimeError("STL vazio")
            if len(tri) > MAX_TRIANGULOS:
                log.info("peça com %d triângulos: usando ilustração", len(tri))
                self._falhas[arquivo] = 9
                return
            chave = hashlib.md5(tri.tobytes()[:2_000_000]).hexdigest()[:12]
            saida = PASTA_UI / f"{chave}.bin"
            tri.astype(np.float32).tofile(saida)
            antigo = self.atual
            self.atual = {"tipo": "real", "url": f"_holo/{chave}.bin", "chave": "real:" + chave, "arquivo": arquivo}
            if antigo and antigo.get("url") and antigo["url"] != self.atual["url"]:
                try:
                    (paths.UI / antigo["url"]).unlink()
                except Exception:
                    pass
        except Exception as e:
            log.info("holograma real indisponível (%s)", e)
            self._falhas[arquivo] = self._falhas.get(arquivo, 0) + 1
        finally:
            self._ocupado = False
