"""Mantiqueira — ponto de entrada. Abre a tela principal e a janela flutuante, e liga o núcleo."""
import os
import sys
import ctypes
import logging
import threading
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


def imagem_icone():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 62, 62), fill=(3, 10, 28, 255), outline=(60, 190, 255, 255), width=4)
    d.polygon([(12, 46), (24, 24), (32, 36), (40, 20), (52, 46)], fill=(60, 190, 255, 255))
    d.ellipse((27, 8, 37, 18), fill=(170, 235, 255, 255))
    return img


def icone_bandeja(nucleo, api):
    """Ícone ao lado do relógio: clique abre a barra rápida."""
    try:
        import pystray
    except Exception:
        log.info("pystray indisponível: sem ícone na bandeja")
        return
    try:
        menu = pystray.Menu(
            pystray.MenuItem("Barra rápida (Ctrl+Espaço)", lambda i, it: nucleo.alternar_barra(), default=True),
            pystray.MenuItem("Abrir painel", lambda i, it: api.mostrar_principal()),
            pystray.MenuItem("Parar de falar", lambda i, it: nucleo.parar_fala()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Encerrar o Mantiqueira", lambda i, it: (i.stop(), api.encerrar())),
        )
        ic = pystray.Icon("Mantiqueira", imagem_icone(), "Mantiqueira", menu)
        nucleo.janelas["bandeja"] = ic
        ic.run()
    except Exception:
        log.exception("ícone da bandeja")


def main():
    log.info("==== Mantiqueira %s iniciando ====", VERSAO)
    ctypes.windll.kernel32.CreateMutexW(None, False, "Mantiqueira_Instancia_Unica")
    if ctypes.windll.kernel32.GetLastError() == 183:
        # já está aberto (talvez minimizado): traz a janela para a frente
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, "Mantiqueira")
        if hwnd:
            u.ShowWindow(hwnd, 9)          # SW_RESTORE
            u.SetForegroundWindow(hwnd)
        else:
            aviso("O Mantiqueira já está aberto.", erro=False)
        return

    # como nos filmes: a saudação gravada toca antes de carregar o resto
    saudou = False
    try:
        from mantiqueira.config import Config
        from mantiqueira import saudacao
        saudou = saudacao.tocar(Config())
    except Exception:
        log.exception("saudação de abertura")

    import webview
    from mantiqueira.nucleo import Nucleo
    from mantiqueira.api import Api

    nucleo = Nucleo()
    nucleo.saudou_no_inicio = saudou
    if saudou:
        nucleo.ultima = {"usuario": "", "assistente": saudacao.texto(nucleo.cfg), "detalhe": ""}
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
    bx = by = None
    try:
        tela = webview.screens[0]
        bx, by = tela.width - 600, tela.height - 130     # canto direito, logo acima da barra de tarefas
    except Exception:
        pass
    barra = webview.create_window("Mantiqueira — barra", url="ui/barra.html", js_api=api, width=580, height=66,
                                  x=bx, y=by, frameless=True, easy_drag=True, on_top=True, hidden=True,
                                  resizable=False, background_color="#030a1c")
    nucleo.janelas.update(main=principal, mini=mini, barra=barra)
    threading.Thread(target=icone_bandeja, args=(nucleo, api), daemon=True, name="bandeja").start()

    def ao_fechar():
        log.info("fechando")
        try:
            if nucleo.ia:
                nucleo.ia.parar()
        finally:
            os._exit(0)

    avisou = {"x": False}

    def ao_pedir_fechar():
        """O X só minimiza: o Mantiqueira continua avisando e ouvindo. Para sair: Configurações > ENCERRAR."""
        if nucleo.cfg["x_esconde"] and not nucleo.saindo:
            try:
                principal.minimize()
            except Exception:
                log.exception("minimizar")
            if not avisou["x"]:
                avisou["x"] = True
                nucleo.falar_aviso("Continuo aqui minimizado, cuidando dos lembretes. "
                                   "Para me encerrar de vez, use o botão Encerrar nas configurações.")
            return False
        return True

    principal.events.closing += ao_pedir_fechar
    principal.events.closed += ao_fechar
    pasta_web = paths.DADOS / "navegador"           # guarda o login dos sistemas da empresa
    pasta_web.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(nucleo.iniciar, http_server=True, private_mode=False, storage_path=str(pasta_web),
                      debug=bool(os.environ.get("MANTIQUEIRA_DEBUG")))
    except TypeError:
        webview.start(nucleo.iniciar, http_server=True, private_mode=False,
                      debug=bool(os.environ.get("MANTIQUEIRA_DEBUG")))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.critical("erro fatal:\n%s", traceback.format_exc())
        aviso("O Mantiqueira encontrou um erro ao abrir.\n\nDetalhes em:\n" + str(paths.DADOS / "mantiqueira.log"))
        raise
