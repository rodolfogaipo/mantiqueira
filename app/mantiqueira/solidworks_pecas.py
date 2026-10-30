"""Peças simples no SolidWorks pela própria interface de programação dele (a mesma das macros):
cubo/bloco, chapa (com furos), cilindro, tubo redondo, tubo retangular/quadrado.

Tudo é um esboço só e uma extrusão só (o furo e o miolo do tubo são contornos internos do mesmo esboço),
numa peça NOVA — nunca mexe em peça aberta, nunca salva sozinho."""
import os
import re
import glob
import logging
from . import textutil

log = logging.getLogger("solidworks_pecas")

FORMAS = {
    "cubo": "bloco", "bloco": "bloco", "caixa": "bloco", "paralelepipedo": "bloco",
    "chapa": "chapa", "placa": "chapa",
    "cilindro": "cilindro", "eixo": "cilindro", "tarugo": "cilindro", "barra redonda": "cilindro",
    "tubo": "tubo", "cano": "tubo", "metalon": "tubo",
}
NOME = {"bloco": "bloco", "cubo": "cubo", "chapa": "chapa", "cilindro": "cilindro", "tubo_r": "tubo redondo",
        "tubo_q": "tubo"}
RX_PEDIDO = re.compile(r"\b(faz|faca|fazer|cria|crie|criar|desenha|desenhe|desenhar|modela|modele|modelar|gera|gere|"
                       r"monta|monte|quero|preciso de|me da|me de)\s+(?:(?:pra mim|para mim|no solidworks|no solid|"
                       r"la no solidworks|ai|me|um|uma|outro|outra|novo|nova|mais um|mais uma)\s+)*"
                       r"(cubo|bloco|caixa|paralelepipedo|chapa|placa|cilindro|eixo|tarugo|barra redonda|tubo|cano|metalon)\b")
NUM = r"(\d+(?:[.,]\d+)?)"
UNID = r"\s*(mm|milimetros?|cm|centimetros?|m|metros?)?\b"


def _mm(v, u):
    v = float(v.replace(",", "."))
    u = (u or "").strip()
    if u.startswith("c"):
        return v * 10
    if u in ("m", "metro", "metros"):
        return v * 1000
    return v


def _texto(p):
    t = textutil.sem_acento(p.lower())
    t = re.sub(r"(\d)\s*[x×]\s*(?=\d)", r"\1 por ", t)          # 1200x600 → 1200 por 600
    t = re.sub(r"\b(\d+) virgula (\d+)\b", r"\1,\2", t)
    t = re.sub(r"\bmeio\b", "0,5", t)
    return t


def _numeros(t):
    """Medidas em mm na ordem em que foram ditas, com o papel de cada uma (parede, furo, comprimento…)."""
    out = []
    for m in re.finditer(NUM + UNID, t):
        antes, depois = t[max(0, m.start() - 30):m.start()], t[m.end():m.end() + 30]
        papel = "medida"
        if re.match(r"\s*furos?\b", depois):
            papel = "qtd_furos"
        elif re.search(r"\bfuros?\s+(de\s+)?(diametro\s+)?(de\s+)?$", antes):
            papel = "furo"
        elif re.match(r"\s*de\s+parede\b", depois) or re.search(r"\bparede\s+(de\s+)?$", antes):
            papel = "parede"
        elif re.match(r"\s*de\s+(espessura|grossura)\b", depois) or re.search(r"\b(espessura|grossura)\s+(de\s+)?$", antes):
            papel = "espessura"
        elif re.match(r"\s*(da|das|de)\s+(borda|bordas|beirada|ponta|pontas)\b", depois):
            papel = "margem"
        elif re.match(r"\s*de\s+(comprimento|altura)\b", depois) or re.search(r"\b(comprimento|altura)\s+(de\s+)?$", antes):
            papel = "comprimento"
        elif re.match(r"\s*de\s+diametro\b", depois) or re.search(r"\bdiametro\s+(de\s+)?$", antes):
            papel = "diametro"
        out.append({"v": _mm(m.group(1), m.group(2)), "num": m.group(1), "unid": m.group(2) or "", "papel": papel})
    # unidade dita só no fim ("100 por 50 por 30 cm") vale para as medidas sem unidade
    com = [n for n in out if n["unid"]]
    if len(com) == 1 and out and out[-1]["unid"] and out[-1]["papel"] == "medida":
        for n in out[:-1]:
            if not n["unid"] and n["papel"] == "medida":
                n["v"] = _mm(n["num"], out[-1]["unid"])
    return out


def entender(pergunta):
    """Devolve (pedido, erro). pedido = {forma, medidas…}. erro = frase pedindo o que falta."""
    t = _texto(pergunta)
    m = RX_PEDIDO.search(t)
    if not m:
        return None, None
    palavra = m.group(2)
    forma = FORMAS[palavra]
    resto = t[m.end():]
    nums = _numeros(resto)

    def um(papel):
        x = [n["v"] for n in nums if n["papel"] == papel]
        return x[0] if x else None
    v = [n["v"] for n in nums if n["papel"] == "medida"]
    ped = {"forma": forma, "palavra": palavra}
    if forma == "bloco":
        if um("comprimento") is not None:
            v.append(um("comprimento"))
        if palavra == "cubo" and len(v) == 1:
            v = v * 3
        if len(v) < 3:
            if not v:
                return None, ("De quantos milímetros é o cubo? Por exemplo: um cubo de 100." if palavra == "cubo" else
                              "Quais as medidas? Por exemplo: um bloco de 200 por 100 por 50.")
            return None, "Preciso das três medidas: comprimento, largura e altura. Por exemplo: 200 por 100 por 50."
        ped.update(c=v[0], l=v[1], a=v[2])
    elif forma == "chapa":
        esp = um("espessura")
        if esp is None and len(v) >= 3:
            esp, v = v[2], v[:2]
        if len(v) < 2 or esp is None:
            return None, ("Preciso do comprimento, da largura e da espessura da chapa. Por exemplo: chapa de 1200 por "
                          "600 com 3 de espessura.")
        ped.update(c=v[0], l=v[1], a=esp)
    elif forma == "cilindro":
        d, comp = um("diametro"), um("comprimento")
        if d is None and v:
            d, v = v[0], v[1:]
        if comp is None and v:
            comp = v[0]
        if d is None or comp is None:
            return None, "Preciso do diâmetro e do comprimento. Por exemplo: cilindro de 40 por 200."
        ped.update(d=d, a=comp)
    elif forma == "tubo":
        parede, comp = um("parede") or um("espessura"), um("comprimento")
        if parede is None:
            return None, ("Qual a espessura da parede do tubo? Por exemplo: tubo de 50 por 30 com 1,5 de parede e 800 "
                          "de comprimento.")
        if comp is None and len(v) >= 2:
            comp, v = v[-1], v[:-1]
        if comp is None or not v:
            return None, ("Preciso da medida do tubo e do comprimento. Por exemplo: tubo redondo de 50 com 2 de parede "
                          "e 600 de comprimento.")
        quadrado = bool(re.search(r"\b(quadrado|retangular|metalon)\b", resto)) or palavra == "metalon"
        redondo = bool(re.search(r"\b(redondo|circular)\b", resto))
        if len(v) >= 2 and not redondo:
            ped.update(forma="tubo_q", c=v[0], l=v[1], e=parede, comp=comp)
        elif quadrado and not redondo:
            ped.update(forma="tubo_q", c=v[0], l=v[0], e=parede, comp=comp)
        else:
            ped.update(forma="tubo_r", d=v[0], e=parede, comp=comp)
    furo = um("furo")
    if furo is not None:
        if ped["forma"] not in ("chapa", "bloco"):
            return None, "Por enquanto eu faço furos só em chapa e bloco."
        canto = bool(re.search(r"\b(nos|nas|em cada|em todos os) (quatro |4 )?(cantos|pontas|extremidades)\b", resto))
        mq = re.search(r"\b(\d+|um|uma|dois|duas|quatro)\s+furos?\b", resto)
        qtd = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "quatro": 4}.get(mq.group(1)) if mq else None
        if mq and qtd is None:
            qtd = int(mq.group(1))
        qtd = qtd or (4 if canto else 1)
        if qtd not in (1, 4):
            return None, "Por enquanto eu faço 1 furo no centro ou 4 furos nos cantos."
        ped["furo"], ped["qtd_furos"] = furo, qtd
        margem = um("margem")
        ped["margem"] = (margem if margem is not None else round(max(furo, 10.0) * 1.5, 1)) if qtd == 4 else 0
    erro = validar(ped)
    if erro:
        return None, erro
    return ped, None


def validar(p):
    vals = [v for k, v in p.items() if k in ("c", "l", "a", "d", "e", "comp", "furo")]
    if any(v <= 0 for v in vals):
        return "As medidas têm de ser maiores que zero."
    if any(v > 20000 for v in vals):
        return "Essa medida passa de 20 metros; confira o número, senhor."
    f = p["forma"]
    if f == "tubo_r" and p["e"] * 2 >= p["d"]:
        return "A parede ficou grossa demais para esse diâmetro."
    if f == "tubo_q" and p["e"] * 2 >= min(p["c"], p["l"]):
        return "A parede ficou grossa demais para essa medida de tubo."
    if p.get("furo"):
        if p["qtd_furos"] == 1 and p["furo"] >= min(p["c"], p["l"]):
            return "O furo ficou maior que a peça."
        if p["qtd_furos"] == 4 and (p["margem"] + p["furo"] / 2 >= min(p["c"], p["l"]) / 2 or p["margem"] < p["furo"] / 2):
            return "Os furos dos cantos não cabem com essa distância da borda."
    return None


def _n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def descrever(p):
    f = p["forma"]
    if f in ("bloco", "chapa"):
        if p.get("palavra") == "cubo" and p["c"] == p["l"] == p["a"]:
            txt = f"um cubo de {_n(p['c'])} milímetros"
        elif f == "chapa":
            txt = f"uma chapa de {_n(p['c'])} por {_n(p['l'])} com {_n(p['a'])} de espessura"
        else:
            txt = f"um bloco de {_n(p['c'])} por {_n(p['l'])} por {_n(p['a'])}"
        if p.get("furo"):
            if p["qtd_furos"] == 4:
                txt += f", com 4 furos de {_n(p['furo'])} a {_n(p['margem'])} da borda"
            else:
                txt += f", com um furo de {_n(p['furo'])} no centro"
        return txt
    if f == "cilindro":
        return f"um cilindro de {_n(p['d'])} de diâmetro por {_n(p['a'])} de comprimento"
    if f == "tubo_r":
        return f"um tubo redondo de {_n(p['d'])} com {_n(p['e'])} de parede e {_n(p['comp'])} de comprimento"
    return f"um tubo de {_n(p['c'])} por {_n(p['l'])} com {_n(p['e'])} de parede e {_n(p['comp'])} de comprimento"


# ---------------------------------------------------------------------- SolidWorks
def _modelo_peca(sw):
    try:
        t = str(sw.GetUserPreferenceStringValue(8) or "")        # swDefaultTemplatePart
        if t and os.path.exists(t):
            return t
    except Exception:
        pass
    for padrao in (r"C:\ProgramData\SolidWorks\SOLIDWORKS 20*\templates\*.prtdot",
                   r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 20*\templates\*.prtdot",
                   r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\*\Tutorial\*.prtdot"):
        achados = sorted(glob.glob(padrao), reverse=True)
        if achados:
            return achados[0]
    return ""


def conectar(abrir_se_fechado=True):
    import comtypes
    import comtypes.client as cc
    comtypes.CoInitialize()
    try:
        return cc.GetActiveObject("SldWorks.Application", dynamic=True), False
    except Exception:
        if not abrir_se_fechado:
            raise
    sw = cc.CreateObject("SldWorks.Application", dynamic=True)
    try:
        sw.Visible = True
    except Exception:
        pass
    return sw, True


def _planos(doc):
    """Os três primeiros planos da árvore: Frontal, Superior, Direito (em qualquer idioma)."""
    out = []
    f = doc.FirstFeature()
    while f is not None and len(out) < 3:
        try:
            if str(f.GetTypeName2()) == "RefPlane":
                out.append(f)
        except Exception:
            pass
        f = f.GetNextFeature()
    return out


def _extrudar(doc, prof_m):
    fm = doc.FeatureManager
    args = (True, False, False, 0, 0, prof_m, 0.0, False, False, False, False, 0.0, 0.0,
            False, False, False, False, True, True, True, 0, 0.0, False)
    feat = None
    for nome in ("FeatureExtrusion3", "FeatureExtrusion2"):
        try:
            feat = getattr(fm, nome)(*args)
            if feat is not None:
                return feat
        except Exception:
            log.debug("%s falhou", nome, exc_info=True)
    return feat


def criar(p, sw=None):
    """Cria a peça numa peça nova. Devolve (ok, mensagem)."""
    abriu = False
    if sw is None:
        sw, abriu = conectar()
    modelo = _modelo_peca(sw)
    if not modelo:
        return False, "Não achei o modelo de peça do SolidWorks (arquivo .prtdot) para criar a peça nova."
    doc = sw.NewDocument(modelo, 0, 0, 0)
    if doc is None:
        return False, "O SolidWorks não deixou criar uma peça nova agora."
    planos = _planos(doc)
    if len(planos) < 3:
        return False, "Não achei os planos da peça nova no SolidWorks."
    frontal, superior = planos[0], planos[1]
    k = 0.001                                        # a interface do SolidWorks trabalha em metros
    f = p["forma"]
    plano = frontal if f in ("tubo_r", "tubo_q") else superior
    doc.ClearSelection2(True)
    plano.Select2(False, 0)
    sm = doc.SketchManager
    sm.InsertSketch(True)
    sm.AddToDB = True                                # desenha sem grudar em nada
    try:
        if f in ("bloco", "chapa"):
            sm.CreateCenterRectangle(0, 0, 0, p["c"] / 2 * k, p["l"] / 2 * k, 0)
            if p.get("furo"):
                r = p["furo"] / 2 * k
                if p["qtd_furos"] == 4:
                    dx, dy = (p["c"] / 2 - p["margem"]) * k, (p["l"] / 2 - p["margem"]) * k
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            sm.CreateCircleByRadius(sx * dx, sy * dy, 0, r)
                else:
                    sm.CreateCircleByRadius(0, 0, 0, r)
            prof = p["a"]
        elif f == "cilindro":
            sm.CreateCircleByRadius(0, 0, 0, p["d"] / 2 * k)
            prof = p["a"]
        elif f == "tubo_r":
            sm.CreateCircleByRadius(0, 0, 0, p["d"] / 2 * k)
            sm.CreateCircleByRadius(0, 0, 0, (p["d"] / 2 - p["e"]) * k)
            prof = p["comp"]
        else:
            sm.CreateCenterRectangle(0, 0, 0, p["c"] / 2 * k, p["l"] / 2 * k, 0)
            sm.CreateCenterRectangle(0, 0, 0, (p["c"] / 2 - p["e"]) * k, (p["l"] / 2 - p["e"]) * k, 0)
            prof = p["comp"]
    finally:
        sm.AddToDB = False
    sm.InsertSketch(True)                            # sai do esboço
    doc.ClearSelection2(True)
    try:
        doc.FeatureByPositionReverse(0).Select2(False, 0)   # seleciona o esboço que acabou de fazer
    except Exception:
        log.debug("selecionar esboço", exc_info=True)
    feat = _extrudar(doc, prof * k)
    if feat is None:
        return False, "Desenhei o esboço, mas o SolidWorks não fez a extrusão. O esboço ficou na peça nova."
    doc.ClearSelection2(True)
    try:
        doc.ShowNamedView2("", 7)                    # isométrica
        doc.ViewZoomtofit2()
    except Exception:
        pass
    msg = f"Pronto, fiz {descrever(p)} numa peça nova do SolidWorks. Ela ainda não está salva."
    if abriu:
        msg = "Abri o SolidWorks e " + msg[0].lower() + msg[1:]
    return True, msg
