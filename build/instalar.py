"""Instalador do Mantiqueira. Junta as partes baixadas e instala, sem precisar de internet.
Compilado como Instalar-Mantiqueira.exe (PyInstaller)."""
import json
import os
import shutil
import subprocess
import sys
import threading
import zipfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

AQUI = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
PADRAO = Path("C:/Mantiqueira")
ATUALIZACAO = AQUI / "Mantiqueira-Atualizacao.zip"
AZUL, FUNDO, TEXTO, CINZA = "#5aa0ff", "#030a1c", "#eef4ff", "#7f9fd6"


class Partes:
    """Lê várias partes como se fossem um único arquivo (para o zipfile)."""

    def __init__(self, caminhos):
        self.caminhos = caminhos
        self.tamanhos = [p.stat().st_size for p in caminhos]
        self.inicios, acc = [], 0
        for t in self.tamanhos:
            self.inicios.append(acc)
            acc += t
        self.total, self.pos = acc, 0
        self.abertos = {}

    def _f(self, i):
        if i not in self.abertos:
            if len(self.abertos) > 4:
                for k in list(self.abertos):
                    self.abertos.pop(k).close()
            self.abertos[i] = open(self.caminhos[i], "rb")
        return self.abertos[i]

    def seekable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.total + off)
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.total - self.pos
        out = bytearray()
        while n > 0 and self.pos < self.total:
            i = max(k for k, ini in enumerate(self.inicios) if ini <= self.pos)
            off = self.pos - self.inicios[i]
            f = self._f(i)
            f.seek(off)
            b = f.read(min(n, self.tamanhos[i] - off))
            if not b:
                break
            out += b
            self.pos += len(b)
            n -= len(b)
        return bytes(out)

    def close(self):
        for f in self.abertos.values():
            f.close()
        self.abertos.clear()


def verificar():
    """Confere se todas as partes estão na pasta. Devolve (pacotes_ok, problemas)."""
    man = AQUI / "manifesto.json"
    if not man.exists():
        return [], ["O arquivo manifesto.json não está na mesma pasta do instalador."]
    dados = json.loads(man.read_text(encoding="utf-8"))
    ok, problemas = [], []
    for nome, info in dados.items():
        caminhos, falta = [], []
        for p in info["partes"]:
            c = AQUI / p["nome"]
            if not c.exists():
                falta.append(p["nome"])
            elif c.stat().st_size != p["tamanho"]:
                falta.append(p["nome"] + " (incompleto, baixe de novo)")
            caminhos.append(c)
        if nome == "Mantiqueira-Turbo.zip" and len(falta) == len(info["partes"]):
            continue  # turbo é opcional
        if falta:
            problemas.append(f"{nome}: faltam " + ", ".join(falta))
        else:
            ok.append((nome, caminhos, info["conteudo"]))
    return ok, problemas


def atalhos(destino: Path):
    exe = destino / "Mantiqueira.exe"
    ps = ("$sh=New-Object -ComObject WScript.Shell;"
          "foreach($d in @([Environment]::GetFolderPath('Desktop'),"
          "(Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs'))){"
          "$s=$sh.CreateShortcut((Join-Path $d 'Mantiqueira.lnk'));"
          f"$s.TargetPath='{exe}';$s.WorkingDirectory='{destino}';$s.IconLocation='{exe},0';$s.Save()}}")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)


class App:
    def __init__(self):
        self.r = tk.Tk()
        self.r.title("Instalar Mantiqueira")
        self.r.configure(bg=FUNDO)
        self.r.geometry("620x360")
        self.r.resizable(False, False)
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("A.Horizontal.TProgressbar", troughcolor="#0c1f44", background=AZUL, bordercolor=FUNDO)
        tk.Label(self.r, text="MANTIQUEIRA", fg=TEXTO, bg=FUNDO, font=("Bahnschrift", 22, "bold")).pack(pady=(26, 0))
        tk.Label(self.r, text="assistente pessoal 100% offline", fg=CINZA, bg=FUNDO, font=("Segoe UI", 10)).pack()
        fr = tk.Frame(self.r, bg=FUNDO)
        fr.pack(pady=22, padx=30, fill="x")
        self.rotulo = tk.Label(fr, text="Instalar em:", fg=CINZA, bg=FUNDO, font=("Segoe UI", 10))
        self.rotulo.pack(anchor="w")
        linha = tk.Frame(fr, bg=FUNDO)
        linha.pack(fill="x", pady=4)
        self.pasta = tk.StringVar(value=str(PADRAO))
        tk.Entry(linha, textvariable=self.pasta, font=("Segoe UI", 11), bg="#020814", fg=TEXTO,
                 insertbackground=TEXTO, relief="flat").pack(side="left", fill="x", expand=True, ipady=5)
        tk.Button(linha, text="Alterar…", command=self.escolher, bg="#0c1f44", fg=TEXTO, relief="flat",
                  padx=10).pack(side="left", padx=(8, 0))
        self.barra = ttk.Progressbar(fr, style="A.Horizontal.TProgressbar", maximum=1000)
        self.barra.pack(fill="x", pady=(18, 6))
        self.msg = tk.StringVar(value="")
        tk.Label(fr, textvariable=self.msg, fg=CINZA, bg=FUNDO, font=("Segoe UI", 9), anchor="w",
                 justify="left", wraplength=560).pack(fill="x")
        self.botao = tk.Button(self.r, text="INSTALAR", command=self.iniciar, bg=AZUL, fg="#000",
                               font=("Segoe UI", 11, "bold"), relief="flat", padx=26, pady=6)
        self.botao.pack(pady=6)
        self.pacotes, problemas = verificar()
        self.modo = "completo"
        tem_base = any(n == "Mantiqueira.zip" for n, _, _ in self.pacotes)
        ja_instalado = any((c / "Mantiqueira.exe").exists()
                           for c in (PADRAO, Path(os.environ.get("LOCALAPPDATA", "C:/")) / "Mantiqueira"))
        if ATUALIZACAO.exists() and (ja_instalado or not tem_base):
            self.modo = "atualizar"
            for c in (PADRAO, Path(os.environ.get("LOCALAPPDATA", "C:/")) / "Mantiqueira"):
                if (c / "Mantiqueira.exe").exists():
                    self.pasta.set(str(c))
                    break
            self.r.title("Atualizar Mantiqueira")
            self.rotulo.configure(text="Atualizar a instalação em:")
            self.botao.configure(text="ATUALIZAR")
            self.msg.set("Atualização encontrada. Troca só o programa: lembretes, histórico e configurações são mantidos. "
                         "Se o Mantiqueira estiver aberto, ele será fechado.")
        elif problemas:
            self.msg.set("Atenção: " + " | ".join(problemas))
            self.botao.configure(state="disabled")
        else:
            gb = sum(c for _, _, c in self.pacotes) / 2**30
            extra = " (inclui o modo Turbo)" if any(n.startswith("Mantiqueira-Turbo") for n, _, _ in self.pacotes) else ""
            self.msg.set(f"Pronto para instalar {gb:.1f} GB{extra}.")

    def escolher(self):
        p = filedialog.askdirectory(initialdir=self.pasta.get())
        if p:
            self.pasta.set(str(Path(p) / "Mantiqueira") if Path(p).name.lower() != "mantiqueira" else p)

    def iniciar(self):
        self.botao.configure(state="disabled")
        threading.Thread(target=self.instalar, daemon=True).start()

    def ui(self, fn, *a):
        self.r.after(0, fn, *a)

    def instalar(self):
        if self.modo == "atualizar":
            return self.atualizar()
        try:
            destino = Path(self.pasta.get())
            try:
                destino.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                destino = Path(os.environ["LOCALAPPDATA"]) / "Mantiqueira"
                destino.mkdir(parents=True, exist_ok=True)
                self.ui(self.pasta.set, str(destino))
            total = sum(c for _, _, c in self.pacotes)
            livre = shutil.disk_usage(destino).free
            if livre < total + 2**30:
                raise RuntimeError(f"Espaço insuficiente: precisa de {total / 2**30:.1f} GB, "
                                   f"há {livre / 2**30:.1f} GB livres.")
            feito = 0
            for nome, caminhos, _ in self.pacotes:
                fonte = Partes(caminhos)
                with zipfile.ZipFile(fonte) as z:
                    for info in z.infolist():
                        rel = info.filename.split("/", 1)[1] if "/" in info.filename else info.filename
                        if not rel or info.is_dir():
                            continue
                        alvo = destino / rel
                        alvo.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(info) as src, open(alvo, "wb") as dst:
                            while True:
                                b = src.read(8 * 2**20)
                                if not b:
                                    break
                                dst.write(b)
                                feito += len(b)
                                self.ui(self.barra.configure, {"value": feito * 1000 // max(1, total)})
                        self.ui(self.msg.set, f"Instalando… {feito / 2**30:.1f} de {total / 2**30:.1f} GB — {rel[-60:]}")
                fonte.close()
            if ATUALIZACAO.exists():
                self.ui(self.msg.set, "Aplicando a atualização…")
                with zipfile.ZipFile(ATUALIZACAO) as z:
                    shutil.rmtree(destino / "app", ignore_errors=True)
                    z.extractall(destino)
            self.ui(self.msg.set, "Criando atalhos…")
            atalhos(destino)
            self.ui(self.fim, destino)
        except Exception as e:
            self.ui(self.erro, str(e))

    def atualizar(self):
        try:
            destino = Path(self.pasta.get())
            if not (destino / "Mantiqueira.exe").exists():
                raise RuntimeError(f"Não encontrei o Mantiqueira instalado em {destino}. Escolha a pasta da instalação.")
            self.ui(self.msg.set, "Fechando o Mantiqueira…")
            ps = ("Get-Process pythonw,python,llama-server -ErrorAction SilentlyContinue | "
                  f"Where-Object {{ $_.Path -like '{destino}*' }} | Stop-Process -Force")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)
            import time
            time.sleep(2)
            with zipfile.ZipFile(ATUALIZACAO) as z:
                nomes = [i for i in z.infolist() if not i.is_dir()]
                if not any(i.filename.startswith("app/") for i in nomes):
                    raise RuntimeError("O arquivo de atualização não parece válido.")
                shutil.rmtree(destino / "app", ignore_errors=True)
                for k, info in enumerate(nomes, 1):
                    alvo = destino / info.filename
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, open(alvo, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    self.ui(self.barra.configure, {"value": k * 1000 // len(nomes)})
            self.ui(self.fim, destino)
        except Exception as e:
            self.ui(self.erro, str(e))

    def fim(self, destino):
        self.barra.configure(value=1000)
        self.msg.set(f"Pronto: {destino}.")
        titulo = "Atualização concluída!" if self.modo == "atualizar" else "Instalação concluída!"
        if messagebox.askyesno("Mantiqueira", titulo + "\n\nAbrir o Mantiqueira agora?\n"
                                              "(A primeira abertura leva cerca de 1 minuto.)"):
            os.startfile(str(destino / "Mantiqueira.exe"))
        self.r.destroy()

    def erro(self, texto):
        self.msg.set("Erro: " + texto)
        self.botao.configure(state="normal")
        messagebox.showerror("Mantiqueira", texto)

    def rodar(self):
        self.r.mainloop()


if __name__ == "__main__":
    App().rodar()
