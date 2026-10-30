"""SolidWorks de mentira para o teste: anota cada comando que a Mantiqueira manda."""
class Reg:
    def __init__(self): self.chamadas = []
class Obj:
    def __init__(self, reg, nome, **kw):
        self._reg, self._nome = reg, nome
        self.__dict__.update(kw)
    def __getattr__(self, k):
        if k.startswith("_"): raise AttributeError(k)
        def f(*a):
            self._reg.chamadas.append((self._nome + "." + k, a))
            return True
        return f
class Feat:
    def __init__(self, reg, tipo, prox=None): self.reg, self.tipo, self.prox = reg, tipo, prox
    def GetTypeName2(self): return self.tipo
    def GetNextFeature(self): return self.prox
    def Select2(self, a, b): self.reg.chamadas.append(("Select2:" + self.tipo, (a, b))); return True
def fazer_sw():
    reg = Reg()
    planos = Feat(reg, "RefPlane", Feat(reg, "RefPlane", Feat(reg, "RefPlane", Feat(reg, "OriginProfileFeature"))))
    raiz = Feat(reg, "CommentsFolder", Feat(reg, "MaterialFolder", planos))
    sm = Obj(reg, "SM")
    fm = Obj(reg, "FM")
    doc = Obj(reg, "DOC", SketchManager=sm, FeatureManager=fm)
    doc.FirstFeature = lambda: raiz
    doc.FeatureByPositionReverse = lambda i: Feat(reg, "ProfileFeature")
    sw = Obj(reg, "SW")
    sw.GetUserPreferenceStringValue = lambda i: __file__
    sw.NewDocument = lambda *a: reg.chamadas.append(("NewDocument", a)) or doc
    return sw, reg, sm
