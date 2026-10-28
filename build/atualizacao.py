"""Gera Mantiqueira-Atualizacao.zip: o programa (app/), o LEIA-ME e as bibliotecas Python que foram
adicionadas depois da primeira instalação (para quem só atualiza, sem baixar tudo de novo).
Uso: python atualizacao.py <pasta_saida> [<pasta_dist>]"""
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# bibliotecas que não existiam na instalação 1.0 (pastas e metadados dentro de site-packages)
EXTRAS = ["pypdf", "pypdf-*", "pypdfium2", "pypdfium2-*", "pypdfium2_raw", "comtypes", "comtypes-*",
          "imageio_ffmpeg", "imageio_ffmpeg-*", "pystray", "pystray-*", "six.py", "six-*"]

saida = Path(sys.argv[1]).resolve() / "Mantiqueira-Atualizacao.zip"
saida.parent.mkdir(parents=True, exist_ok=True)
dist = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
n_extras = 0
with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted((RAIZ / "app").rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and "_holo" not in f.parts:
            z.write(f, f.relative_to(RAIZ).as_posix())
    z.write(RAIZ / "LEIA-ME.txt", "LEIA-ME.txt")
    if dist:
        sp = dist / "python" / "Lib" / "site-packages"
        for padrao in EXTRAS:
            for item in sorted(sp.glob(padrao)):
                arquivos = [item] if item.is_file() else [x for x in item.rglob("*") if x.is_file()]
                for f in arquivos:
                    if "__pycache__" in f.parts:
                        continue
                    z.write(f, f.relative_to(dist).as_posix())
                    n_extras += 1
print("atualização:", saida, f"{saida.stat().st_size / 2**20:.1f} MB", f"({n_extras} arquivos de bibliotecas)")
if dist and n_extras == 0:
    raise SystemExit("nenhuma biblioteca extra encontrada — confira a lista EXTRAS")
