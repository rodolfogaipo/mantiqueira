"""Gera Mantiqueira-Atualizacao.zip só com o programa (pasta app/ e o LEIA-ME), para atualizar sem baixar tudo.
Uso: python atualizacao.py <pasta_saida>"""
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
saida = Path(sys.argv[1]).resolve() / "Mantiqueira-Atualizacao.zip"
saida.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((RAIZ / "app").rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            z.write(f, f.relative_to(RAIZ).as_posix())
    z.write(RAIZ / "LEIA-ME.txt", "LEIA-ME.txt")
print("atualização:", saida, f"{saida.stat().st_size / 1024:.0f} KB")
