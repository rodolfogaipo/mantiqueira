"""Informações do computador: CPU, RAM, placa de vídeo, processos, inicialização com o Windows."""
import os
import shutil
import subprocess
import threading
import time
import logging
import psutil
from . import paths

log = logging.getLogger("sistema")
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW

_cache = {"t": 0, "gpu": None}
_lock = threading.Lock()


def _nvidia_smi():
    p = shutil.which("nvidia-smi")
    if p:
        return p
    for c in (r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.exists(c):
            return c
    return None


def gpu(max_idade=4.0):
    """Devolve {'nome','usada','total','livre','uso'} em MB ou None se não houver NVIDIA."""
    with _lock:
        if time.time() - _cache["t"] < max_idade:
            return _cache["gpu"]
        info = None
        exe = _nvidia_smi()
        if exe:
            try:
                out = subprocess.run(
                    [exe, "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=4, creationflags=SEM_JANELA).stdout.strip()
                if out:
                    nome, usada, total, uso = [x.strip() for x in out.splitlines()[0].split(",")]
                    usada, total = int(float(usada)), int(float(total))
                    info = {"nome": nome, "usada": usada, "total": total, "livre": total - usada,
                            "uso": int(float(uso)) if uso.replace(".", "").isdigit() else 0}
            except Exception:
                log.debug("nvidia-smi falhou", exc_info=True)
        _cache.update(t=time.time(), gpu=info)
        return info


def cpu_ram():
    vm = psutil.virtual_memory()
    return psutil.cpu_percent(interval=None), vm.used / 2**30, vm.total / 2**30, vm.percent


def processo_rodando(nome: str) -> bool:
    nome = nome.lower()
    for p in psutil.process_iter(["name"]):
        try:
            if (p.info["name"] or "").lower() == nome:
                return True
        except Exception:
            pass
    return False


def solidworks_aberto() -> bool:
    return processo_rodando("SLDWORKS.exe")


def powershell(script: str, timeout=30) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", script], capture_output=True, timeout=timeout, creationflags=SEM_JANELA)
        return r.stdout.decode("utf-8", "replace")
    except Exception:
        log.exception("powershell falhou")
        return ""


def _atalho_inicializar():
    return os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\Mantiqueira.lnk")


def iniciar_com_windows(ativar: bool):
    lnk = _atalho_inicializar()
    if ativar:
        alvo = str(paths.LAUNCHER)
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
                  "$s.TargetPath='%s';$s.WorkingDirectory='%s';$s.Save()") % (
            lnk.replace("'", "''"), alvo.replace("'", "''"), str(paths.RAIZ).replace("'", "''"))
        powershell(script)
    else:
        try:
            os.remove(lnk)
        except FileNotFoundError:
            pass
