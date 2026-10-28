"""Preferências do usuário, guardadas em dados/config.json."""
import json
import threading
import logging
from . import paths

log = logging.getLogger("config")

PADRAO = {
    "nome": "Rodolfo",
    "tratamento": "senhor",
    "tema": "Azul",
    "voz": "",                      # vazio = escolher a primeira voz natural disponível
    "microfone": None,              # None = microfone padrão do Windows
    "ativacao_por_voz": True,
    "palavras_ativacao": ["mantiqueira"],
    "atalho": "ctrl+space",
    "responder_falando": True,
    "olhos_ativos": True,
    "modo_ia": "normal",            # normal | turbo | auto
    "iniciar_com_windows": False,
    "ignorar": [
        "banco", "bank", "senha", "password", "keepass", "bitwarden", "1password",
        "inprivate", "anônima", "anonima", "incognito", "nubank", "itaú", "itau",
        "bradesco", "santander", "sicoob", "sicredi", "caixa econômica", "banco do brasil",
        "internet banking", "pix",
    ],
}


class Config:
    def __init__(self):
        self.arquivo = paths.DADOS / "config.json"
        self._lock = threading.Lock()
        self.dados = dict(PADRAO)
        try:
            if self.arquivo.exists():
                salvo = json.loads(self.arquivo.read_text(encoding="utf-8"))
                self.dados.update({k: v for k, v in salvo.items() if k in PADRAO})
        except Exception:
            log.exception("config.json inválido; usando padrão")
        self.salvar()

    def __getitem__(self, k):
        return self.dados.get(k, PADRAO.get(k))

    def get(self, k, padrao=None):
        return self.dados.get(k, padrao)

    def atualizar(self, novos: dict):
        with self._lock:
            for k, v in novos.items():
                if k in PADRAO:
                    self.dados[k] = v
        self.salvar()

    def salvar(self):
        with self._lock:
            tmp = self.arquivo.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.arquivo)
