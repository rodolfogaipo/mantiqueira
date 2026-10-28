"""Leitura da tela (OCR) — usa o OCR do próprio Windows; se não houver, usa o RapidOCR."""
import asyncio
import logging
from . import paths

log = logging.getLogger("tela")


def capturar():
    import mss
    import mss.tools
    arq = paths.DADOS / "tela.png"
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        img = sct.grab(mon)
        mss.tools.to_png(img.rgb, img.size, output=str(arq))
    return arq


async def _ocr_windows(caminho):
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.storage import StorageFile, FileAccessMode
    f = await StorageFile.get_file_from_path_async(str(caminho))
    stream = await f.open_async(FileAccessMode.READ)
    dec = await BitmapDecoder.create_async(stream)
    bmp = await dec.get_software_bitmap_async()
    motor = None
    try:
        motor = OcrEngine.try_create_from_language(Language("pt-BR"))
    except Exception:
        pass
    if motor is None:
        motor = OcrEngine.try_create_from_user_profile_languages()
    if motor is None:
        raise RuntimeError("OCR do Windows indisponível")
    res = await motor.recognize_async(bmp)
    return "\n".join(l.text for l in res.lines)


def _ocr_rapid(caminho):
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()
    res, _ = eng(str(caminho))
    return "\n".join(r[1] for r in (res or []))


def ler_tela(limite=3500):
    caminho = capturar()
    texto = ""
    try:
        texto = asyncio.run(_ocr_windows(caminho))
    except Exception:
        log.warning("OCR do Windows falhou; tentando RapidOCR", exc_info=True)
        try:
            texto = _ocr_rapid(caminho)
        except Exception:
            log.exception("RapidOCR falhou")
    texto = "\n".join(l.strip() for l in texto.splitlines() if l.strip())
    return texto[:limite]
