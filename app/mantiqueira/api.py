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

    def enviar(self, texto, origem="texto"):
        origem = origem if origem in ("texto", "barra") else "texto"
        if origem == "barra":
            self._n.esconder_barra()
        self._n.processar_texto_async(texto, origem)
        return True

    def parar_fala(self):
        self._n.parar_fala()
        return True

    def esconder_barra(self):
        self._n.esconder_barra()
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
        if acao == "abrir" and p["arquivo"]:
            return self._ir_para(p["arquivo"])
        if acao == "adiar":
            db.pendencia_status(p["id"], "adiada", adiar_min=60)
        else:
            db.pendencia_status(p["id"], "resolvida")
        return True

    def _ir_para(self, arquivo):
        """Traz para frente a janela que já tem o arquivo aberto; se não houver, abre o arquivo."""
        import ctypes
        from . import leitor
        tronco = os.path.splitext(os.path.basename(arquivo))[0].lower()
        u = ctypes.windll.user32
        for hwnd, _proc, titulo in leitor.janelas_abertas():
            if tronco and tronco in titulo.lower() and not titulo.startswith("Mantiqueira"):
                if u.IsIconic(hwnd):
                    u.ShowWindow(hwnd, 9)
                u.keybd_event(0x12, 0, 0, 0)
                u.keybd_event(0x12, 0, 2, 0)
                u.SetForegroundWindow(hwnd)
                return True
        caminho = None
        if self._n.olhos:
            try:
                caminho = self._n.olhos.recentes.achar(arquivo)
            except Exception:
                caminho = None
        if not caminho and self._n.indice:
            caminho = self._n.indice.achar(arquivo)
        if caminho:
            os.startfile(caminho)
            return True
        return False

    # --------------------------------------------------------------- foto do holograma e sistemas
    def escolher_foto(self):
        import webview
        w = self._n.janelas.get("main")
        tipo = getattr(getattr(webview, "FileDialog", None), "OPEN", None) or webview.OPEN_DIALOG
        r = w.create_file_dialog(tipo, file_types=("Imagens (*.jpg;*.jpeg;*.png;*.webp;*.bmp)", "Todos os arquivos (*.*)")) if w else None
        if not r or not self._n.holo:
            return False
        try:
            self._n.holo.definir_foto(r[0])
            return True
        except Exception:
            log.exception("foto")
            return False

    def sistemas_lista(self):
        return list(self._n.cfg["sistemas_web"])

    def sistemas_salvar(self, lista):
        limpa = []
        for s in lista or []:
            nome, url = str(s.get("nome", "")).strip(), str(s.get("url", "")).strip()
            if nome and url.startswith(("http://", "https://")):
                limpa.append({"nome": nome, "url": url, "palavras": str(s.get("palavras", "")).strip()})
        self._n.cfg.atualizar({"sistemas_web": limpa})
        return True

    def sistema_entrar(self, nome):
        sw = self._n.sistemas
        if not sw:
            return False
        for s in self._n.cfg["sistemas_web"]:
            if s["nome"] == nome:
                sw.abrir_para_login(s)
                return True
        return False

    def indice_resumo(self):
        return self._n.indice.resumo() if self._n.indice else {}

    def indice_atualizar(self):
        if self._n.indice:
            self._n.indice.atualizar_agora()
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
            "foto": bool(n.holo and n.holo.foto_versao),
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
        if "sistemas_web" in novos:
            novos["sistemas_web"] = [{"nome": str(x.get("nome", "")).strip(), "url": str(x.get("url", "")).strip(),
                                      "palavras": str(x.get("palavras", "")).strip()} for x in novos["sistemas_web"] or []
                                     if str(x.get("nome", "")).strip() and len(str(x.get("url", "")).strip()) > 10
                                     and str(x.get("url", "")).strip().startswith(("http://", "https://"))]
        n.cfg.atualizar(novos)
        if novos.get("microfone", antes["microfone"]) != antes["microfone"] and n.ouvido:
            n.ouvido.reiniciar_microfone()
        if "iniciar_com_windows" in novos and novos["iniciar_com_windows"] != antes["iniciar_com_windows"]:
            threading.Thread(target=sistema.iniciar_com_windows, args=(bool(novos["iniciar_com_windows"]),),
                             daemon=True).start()
        if any(k in novos and novos[k] != antes.get(k) for k in ("atalho", "atalho_barra")):
            try:
                import keyboard
                keyboard.clear_all_hotkeys()
                keyboard.add_hotkey(n.cfg["atalho"], n.ouvir_agora, suppress=False)
                keyboard.add_hotkey(n.cfg["atalho_barra"], n.alternar_barra, suppress=False)
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
