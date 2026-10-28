"""Mantiqueira — ponto de entrada. Abre a tela principal e a janela flutuante, e liga o núcleo."""
import os
import sys
import ctypes
import logging
import traceback
from pathlib import Path

AQUI = Path(__file__).resolve().parent
os.chdir(AQUI)
sys.path.insert(0, str(AQUI))

from mantiqueira import paths, VERSAO  # noqa: E402

logging.basicConfig(filename=str(paths.DADOS / "mantiqueira.log"), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")


def aviso(texto, erro=True):
    try:
        ctypes.windll.user32.MessageBoxW(0, texto, "Mantiqueira", 0x10 if erro else 0x40)
    except Exception:
        print(texto)


def main():
    log.info("==== Mantiqueira %s iniciando ====", VERSAO)
    ctypes.windll.kernel32.CreateMutexW(None, False, "Mantiqueira_Instancia_Unica")
    if ctypes.windll.kernel32.GetLastError() == 183:
        aviso("O Mantiqueira já está aberto.", erro=False)
        return

    import webview
    from mantiqueira.nucleo import Nucleo
    from mantiqueira.api import Api

    nucleo = Nucleo()
    api = Api(nucleo)

    opcoes = dict(title="Mantiqueira", url="ui/index.html", js_api=api, width=1440, height=900,
                  min_size=(960, 600), background_color="#030a1c")
    try:
        principal = webview.create_window(maximized=True, **opcoes)
    except TypeError:
        principal = webview.create_window(**opcoes)

    x = y = None
    try:
        tela = webview.screens[0]
        x, y = tela.width - 440, tela.height - 620
    except Exception:
        pass
    mini = webview.create_window("Mantiqueira — ouvindo", url="ui/mini.html", js_api=api, width=420, height=560,
                                 x=x, y=y, frameless=True, easy_drag=True, on_top=True, hidden=True,
                                 resizable=False, background_color="#030a1c")
    nucleo.janelas.update(main=principal, mini=mini)

    def ao_fechar():
        log.info("fechando")
        try:
            if nucleo.ia:
                nucleo.ia.parar()
        finally:
            os._exit(0)

    principal.events.closed += ao_fechar
    webview.start(nucleo.iniciar, http_server=True, private_mode=False,
                  debug=bool(os.environ.get("MANTIQUEIRA_DEBUG")))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.critical("erro fatal:\n%s", traceback.format_exc())
        aviso("O Mantiqueira encontrou um erro ao abrir.\n\nDetalhes em:\n" + str(paths.DADOS / "mantiqueira.log"))
        raise
