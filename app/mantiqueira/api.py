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

    def testar_aviso(self):
        import datetime as dt
        self._n.db.lembrete_novo(agora() + dt.timedelta(seconds=20), "Teste de aviso do Mantiqueira", "teste")
        return True

    def fechar_alerta(self):
        if self._n.alerta:
            self._n.db.lembrete_status(int(self._n.alerta["id"]), "visto")
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

    def encerrar(self):
        self._n.saindo = True
        w = self._n.janelas.get("main")
        threading.Thread(target=lambda: w and w.destroy(), daemon=True).start()
        return True

    def abrir_dados(self):
        os.startfile(str(paths.DADOS))
        return True

    # --------------------------------------------------------------- base de conhecimento
    def conhecimento(self):
        base = self._n.conhecimento
        if not base:
            return {"docs": [], "status": "Carregando…"}
        return {"docs": base.listar(), "status": base.status}

    def conhecimento_adicionar(self):
        import webview
        w = self._n.janelas.get("main")
        if not w:
            return False
        tipo = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        r = w.create_file_dialog(tipo, allow_multiple=True,
                                 file_types=("Documentos (*.pdf;*.txt;*.md;*.docx)", "Todos os arquivos (*.*)"))
        if not r:
            return False
        if self._n.conhecimento:
            self._n.conhecimento.status = f"Lendo {len(r)} arquivo(s)…"
        threading.Thread(target=self._n.adicionar_documentos, args=(list(r),), daemon=True).start()
        return True

    def conhecimento_remover(self, doc_id):
        return bool(self._n.conhecimento and self._n.conhecimento.remover(int(doc_id)))

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
            self._n.voz.falar(f"Olá, {t}. Eu sou o Mantiqueira, e esta é a minha voz.", voz_id or None)
        return True

    def gravar_voz(self):
        threading.Thread(target=self._n.gravar_voz_personalizada, daemon=True).start()
        return True

    def usar_arquivo_voz(self):
        """Usa um áudio (do celular, WhatsApp, gravador…) como base da voz natural."""
        import webview
        from .voz import VOZ_PERSONALIZADA_WAV, preparar_audio_voz
        w = self._n.janelas.get("main")
        tipo = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        r = w.create_file_dialog(tipo, file_types=(
            "Áudio (*.wav;*.mp3;*.ogg;*.opus;*.m4a;*.aac;*.wma;*.flac;*.mp4)", "Todos os arquivos (*.*)")) if w else None
        if not r:
            return False

        def tarefa():
            self._n.aviso_gravacao = "Preparando o áudio…"
            try:
                seg = preparar_audio_voz(r[0], VOZ_PERSONALIZADA_WAV)
            except Exception as e:
                log.exception("áudio da voz")
                self._n.aviso_gravacao = f"Não consegui usar esse áudio: {e}"
                return
            if self._n.voz:
                self._n.voz.voz_personalizada_atualizada()
            self._n.cfg.atualizar({"voz": "xtts:personalizada"})
            aviso = " (curto: o ideal é 20 a 30 segundos)" if seg < 12 else ""
            self._n.aviso_gravacao = f"Voz pronta a partir de {seg:.0f} s de áudio{aviso}. Clique em TESTAR."
        threading.Thread(target=tarefa, daemon=True).start()
        return True
