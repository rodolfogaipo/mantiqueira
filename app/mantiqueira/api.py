"""Funções chamadas pelas telas (JavaScript → Python)."""
import os
import shutil
import logging
import threading
from . import paths, sistema
from .db import agora

log = logging.getLogger("api")


class Api:
    def __init__(self, nucleo):
        self._n = nucleo

    # --------------------------------------------------------------- estado e conversa
    def estado(self):
        try:
            return self._n.estado_ui()
        except Exception as e:
            log.exception("estado")
            return {"pronto": False, "boot": f"Erro: {e}", "estado": "carregando"}

    def enviar(self, texto):
        self._n.processar_texto_async(texto, "texto")
        return True

    def ouvir(self):
        return bool(self._n.ouvir_agora())

    def historico(self):
        return self._n.db.conversa_ultimas(60)

    # --------------------------------------------------------------- lembretes e pendências
    def lembrete(self, id_, acao):
        db = self._n.db
        if acao == "concluir":
            db.lembrete_status(int(id_), "concluido")
        elif acao == "adiar":
            db.lembrete_adiar(int(id_), 10)
        elif acao == "cancelar":
            db.lembrete_status(int(id_), "cancelado")
        if self._n.alerta and self._n.alerta.get("id") == int(id_):
            self._n.alerta = None
            self._n.mostrar_mini_seguro(False)
        return True

    def fechar_alerta(self):
        self._n.alerta = None
        self._n.mostrar_mini_seguro(False)
        return True

    def pendencia(self, id_, acao):
        db = self._n.db
        p = db.pendencia(int(id_))
        if not p:
            return False
        if acao == "abrir" and p["arquivo"] and self._n.olhos:
            caminho = self._n.olhos.recentes.achar(p["arquivo"])
            if caminho:
                os.startfile(caminho)
                return True
            return False
        if acao == "adiar":
            db.pendencia_status(p["id"], "adiada", adiar_min=60)
        else:
            db.pendencia_status(p["id"], "resolvida")
        return True

    # --------------------------------------------------------------- janelas
    def esconder_mini(self):
        self._n.mostrar_mini_seguro(False)
        return True

    def mostrar_principal(self):
        w = self._n.janelas.get("main")
        if w:
            try:
                w.restore()
            except Exception:
                pass
            w.show()
        self._n.mostrar_mini_seguro(False)
        return True

    def abrir_dados(self):
        os.startfile(str(paths.DADOS))
        return True

    # --------------------------------------------------------------- configurações
    def config(self):
        n = self._n
        from .ouvido import Ouvido
        return {
            "cfg": dict(n.cfg.dados),
            "vozes": n.voz.vozes() if n.voz else [],
            "voz_atual": n.voz.voz_padrao() if n.voz else "",
            "microfones": Ouvido.microfones(),
            "turbo": bool(n.ia and n.ia.turbo_disponivel()),
        }

    def salvar_config(self, novos):
        n = self._n
        antes = dict(n.cfg.dados)
        if "ignorar" in novos and isinstance(novos["ignorar"], str):
            novos["ignorar"] = [x.strip() for x in novos["ignorar"].splitlines() if x.strip()]
        if "microfone" in novos and novos["microfone"] in ("", "padrao", None):
            novos["microfone"] = None
        elif "microfone" in novos:
            try:
                novos["microfone"] = int(novos["microfone"])
            except (TypeError, ValueError):
                novos["microfone"] = None
        n.cfg.atualizar(novos)
        if novos.get("microfone", antes["microfone"]) != antes["microfone"] and n.ouvido:
            n.ouvido.reiniciar_microfone()
        if "iniciar_com_windows" in novos and novos["iniciar_com_windows"] != antes["iniciar_com_windows"]:
            threading.Thread(target=sistema.iniciar_com_windows, args=(bool(novos["iniciar_com_windows"]),),
                             daemon=True).start()
        if "atalho" in novos and novos["atalho"] != antes["atalho"]:
            try:
                import keyboard
                keyboard.clear_all_hotkeys()
                keyboard.add_hotkey(n.cfg["atalho"], n.ouvir_agora, suppress=False)
            except Exception:
                log.exception("atalho")
        return True

    def testar_voz(self, voz_id):
        if self._n.voz:
            t = self._n.cfg["tratamento"]
            self._n.voz.falar(f"Olá, {t}. Eu sou a Mantiqueira, e esta é a minha voz.", voz_id or None)
        return True

    def gravar_voz(self):
        threading.Thread(target=self._n.gravar_voz_personalizada, daemon=True).start()
        return True

    def usar_arquivo_voz(self):
        import webview
        from .voz import VOZ_PERSONALIZADA_WAV
        w = self._n.janelas.get("main")
        r = w.create_file_dialog(webview.OPEN_DIALOG, file_types=("Áudio WAV (*.wav)",)) if w else None
        if not r:
            return False
        shutil.copyfile(r[0], VOZ_PERSONALIZADA_WAV)
        if self._n.voz:
            self._n.voz.voz_personalizada_atualizada()
        self._n.cfg.atualizar({"voz": "xtts:personalizada"})
        self._n.aviso_gravacao = "Voz carregada do arquivo. Clique em Testar para ouvir."
        return True
