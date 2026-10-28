"""Gera o ícone da Mantiqueira (serra estilizada em azul) em build/mantiqueira.ico."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, S - 8, S - 8), fill=(3, 10, 28, 255), outline=(90, 160, 255, 255), width=10)
brilho = Image.new("RGBA", (S, S), (0, 0, 0, 0))
g = ImageDraw.Draw(brilho)
serra = [(46, 178), (92, 116), (118, 142), (156, 74), (210, 178)]
g.line(serra, fill=(90, 160, 255, 255), width=18, joint="curve")
brilho = brilho.filter(ImageFilter.GaussianBlur(10))
img = Image.alpha_composite(img, brilho)
d = ImageDraw.Draw(img)
d.line(serra, fill=(238, 244, 255, 255), width=12, joint="curve")
d.line([(46, 194), (210, 194)], fill=(90, 160, 255, 255), width=5)
saida = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("mantiqueira.ico"))
img.save(saida, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("ícone:", saida)
