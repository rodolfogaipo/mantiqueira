"""Empacota a pasta de distribuição em partes de até ~1,9 GB (limite do GitHub é 2 GB por arquivo).
Gera Mantiqueira.zip.001, .002… e, se houver, Mantiqueira-Turbo.zip.001… (o modelo turbo é opcional).
Os arquivos de origem são apagados conforme são empacotados, para caber no disco da máquina de montagem.
Uso: python empacotar.py <pasta_dist> <pasta_saida>"""
import json
import os
import sys
import zipfile
from pathlib import Path

PARTE = int(os.environ.get("TAMANHO_PARTE", 1900 * 2**20))


class SaidaDividida:
    """Arquivo de escrita que se divide em partes. Não permite voltar (zipfile usa 'data descriptors')."""

    def __init__(self, base: Path, tamanho=PARTE):
        self.base, self.tamanho = base, tamanho
        self.n, self.pos, self.f, self.usado = 0, 0, None, 0
        self.partes = []
        self._nova()

    def _nova(self):
        if self.f:
            self.f.close()
        self.n += 1
        caminho = Path(f"{self.base}.{self.n:03d}")
        self.partes.append(caminho)
        self.f = open(caminho, "wb")
        self.usado = 0

    def write(self, b):
        b = memoryview(b)
        escrito = 0
        while escrito < len(b):
            livre = self.tamanho - self.usado
            if livre == 0:
                self._nova()
                continue
            pedaco = b[escrito:escrito + livre]
            self.f.write(pedaco)
            self.usado += len(pedaco)
            escrito += len(pedaco)
        self.pos += escrito
        return escrito

    def tell(self):
        return self.pos

    def seek(self, *a):
        raise OSError("não é possível voltar")

    def seekable(self):
        return False

    def flush(self):
        self.f.flush()

    def close(self):
        if self.f:
            self.f.close()
            self.f = None


def empacotar(raiz: Path, arquivos, base: Path):
    saida = SaidaDividida(base)
    total = 0
    with zipfile.ZipFile(saida, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for i, f in enumerate(arquivos, 1):
            rel = f.relative_to(raiz).as_posix()
            tam = f.stat().st_size
            z.write(f, "Mantiqueira/" + rel)
            total += tam
            f.unlink()
            if i % 2000 == 0 or tam > 200 * 2**20:
                print(f"  {i}/{len(arquivos)} {rel} ({total / 2**30:.2f} GB)", flush=True)
    saida.close()
    return saida.partes, total


def main():
    dist, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    todos = sorted(p for p in dist.rglob("*") if p.is_file())
    turbo = [p for p in todos if p.name == "turbo.gguf"]
    base = [p for p in todos if p not in turbo]
    manifesto = {}
    for nome, lista in (("Mantiqueira.zip", base), ("Mantiqueira-Turbo.zip", turbo)):
        if not lista:
            continue
        print("empacotando", nome, len(lista), "arquivos", flush=True)
        partes, total = empacotar(dist, lista, out / nome)
        manifesto[nome] = {"partes": [{"nome": p.name, "tamanho": p.stat().st_size} for p in partes],
                           "conteudo": total}
    (out / "manifesto.json").write_text(json.dumps(manifesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifesto, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
