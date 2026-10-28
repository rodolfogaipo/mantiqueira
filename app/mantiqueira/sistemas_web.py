"""Sistemas da empresa (páginas internas, ex.: CNPs do Órigus Syntex).
O Mantiqueira abre a página numa janela própria (invisível depois do primeiro login), lê as tabelas da
tela — passando as páginas — e usa os dados para responder. Só LÊ: nunca clica em salvar/excluir."""
import json
import re
import time
import logging
import threading
from . import textutil

log = logging.getLogger("web")

PADRAO = [{"nome": "CNPs", "url": "http://192.168.1.96:8080/cnp/cnps",
           "palavras": "cnp cnps"}]

# Lê tabelas HTML e também tabelas feitas com <div role="row">. Devolve {cab, linhas, proxima}.
JS_LER = r"""
(function(){
  function txt(e){ return (e.innerText || e.textContent || '').replace(/\s+/g,' ').trim(); }
  var tabelas = [];
  document.querySelectorAll('table').forEach(function(t){
    var cab = [], linhas = [];
    var ths = t.querySelectorAll('thead th, thead td');
    if (!ths.length){ var p = t.querySelector('tr'); if (p) ths = p.querySelectorAll('th'); }
    ths.forEach(function(h){ cab.push(txt(h)); });
    t.querySelectorAll('tbody tr').forEach(function(tr){
      var c = []; tr.querySelectorAll('td,th').forEach(function(td){ c.push(txt(td)); });
      if (c.join('').length) linhas.push(c);
    });
    if (linhas.length) tabelas.push({cab: cab, linhas: linhas});
  });
  if (!tabelas.length){
    var rows = document.querySelectorAll('[role=row]');
    var cab = [], linhas = [];
    rows.forEach(function(r){
      var hs = r.querySelectorAll('[role=columnheader]');
      if (hs.length){ cab = []; hs.forEach(function(h){ cab.push(txt(h)); }); return; }
      var c = []; r.querySelectorAll('[role=cell],[role=gridcell]').forEach(function(x){ c.push(txt(x)); });
      if (c.length) linhas.push(c);
    });
    if (linhas.length) tabelas.push({cab: cab, linhas: linhas});
  }
  var prox = null;
  var cands = document.querySelectorAll('button, a, li, [role=button]');
  for (var i = 0; i < cands.length; i++){
    var b = cands[i], r = ((b.getAttribute('aria-label') || '') + ' ' + (b.title || '') + ' ' + txt(b) + ' ' + b.className).toLowerCase();
    if (/(pr[oó]xim|next|seguinte|›|»|chevron_right|navigate_next)/.test(r) && !/(últim|ultim|last)/.test(r)){
      var desab = b.disabled || b.getAttribute('aria-disabled') === 'true' || /disabled/.test(b.className) ||
                  (b.parentElement && /disabled/.test(b.parentElement.className));
      if (!desab && b.offsetParent !== null){ b.setAttribute('data-mantiqueira-prox', '1'); prox = true; break; }
    }
  }
  var login = !!document.querySelector('input[type=password]');
  return JSON.stringify({tabelas: tabelas, proxima: !!prox, login: login, titulo: document.title, url: location.href});
})()
"""

# tenta escolher o maior "registros por página" (select nativo)
JS_MAIS_POR_PAGINA = r"""
(function(){
  var ok = false;
  document.querySelectorAll('select').forEach(function(s){
    var nums = Array.prototype.map.call(s.options, function(o){ return parseInt(o.value || o.text, 10) || 0; });
    var max = Math.max.apply(null, nums);
    if (max >= 25 && nums.length >= 2){
      for (var i = 0; i < s.options.length; i++){ if ((parseInt(s.options[i].value || s.options[i].text, 10) || 0) === max){ s.selectedIndex = i; } }
      s.dispatchEvent(new Event('change', {bubbles: true})); ok = true;
    }
  });
  return ok;
})()
"""

JS_PROXIMA = "(function(){var b=document.querySelector('[data-mantiqueira-prox]'); if(b){b.removeAttribute('data-mantiqueira-prox'); b.click(); return true;} return false;})()"


class SistemasWeb:
    def __init__(self, nucleo):
        self.n = nucleo
        self.janela = None
        self.lock = threading.Lock()
        self.cache = {}            # nome → (hora, dados)
        self.precisa_login = set()

    def lista(self):
        s = self.n.cfg.get("sistemas_web") or PADRAO
        return [x for x in s if x.get("url")]

    def qual(self, pergunta):
        """Sistema citado na pergunta (pelo nome ou palavras-chave)."""
        p = textutil.sem_acento(pergunta.lower())
        for s in self.lista():
            chaves = [s["nome"]] + (s.get("palavras") or "").split()
            if any(re.search(r"\b" + re.escape(textutil.sem_acento(c.lower())) + r"\b", p) for c in chaves if len(c) >= 3):
                return s
        return None

    # ------------------------------------------------------------------ janela
    def _janela(self, url, visivel):
        import webview
        if self.janela is None:
            self.janela = webview.create_window("Mantiqueira — sistema da empresa", url=url, width=1200, height=800,
                                                hidden=not visivel)
            fim = time.time() + 20
            while time.time() < fim:
                try:
                    if self.janela.get_current_url():
                        break
                except Exception:
                    pass
                time.sleep(0.5)
        else:
            self.janela.load_url(url)
            if visivel:
                self.janela.show()
        return self.janela

    def abrir_para_login(self, sistema):
        w = self._janela(sistema["url"], True)
        try:
            w.restore()
        except Exception:
            pass
        return True

    def esconder(self):
        if self.janela:
            try:
                self.janela.hide()
            except Exception:
                pass

    # ------------------------------------------------------------------ leitura
    def ler(self, sistema, max_paginas=25, cache_seg=180):
        nome = sistema["nome"]
        c = self.cache.get(nome)
        if c and time.time() - c[0] < cache_seg:
            return c[1]
        with self.lock:
            w = self._janela(sistema["url"], False)
            time.sleep(3)
            dados = self._eval(w, JS_LER)
            for _ in range(10):                    # páginas que carregam a tabela depois
                if dados and (dados["tabelas"] or dados["login"]):
                    break
                time.sleep(1)
                dados = self._eval(w, JS_LER)
            if not dados:
                raise RuntimeError("a página não respondeu")
            if dados["login"]:
                self.precisa_login.add(nome)
                return {"login": True}
            self.precisa_login.discard(nome)
            if self._eval(w, JS_MAIS_POR_PAGINA, json_=False):
                time.sleep(2.5)
                dados = self._eval(w, JS_LER) or dados
            cab = dados["tabelas"][0]["cab"] if dados["tabelas"] else []
            linhas = [l for t in dados["tabelas"][:1] for l in t["linhas"]]
            pag = 1
            while dados.get("proxima") and pag < max_paginas:
                if not self._eval(w, JS_PROXIMA, json_=False):
                    break
                time.sleep(1.6)
                novo = self._eval(w, JS_LER)
                if not novo or not novo["tabelas"]:
                    break
                novas = novo["tabelas"][0]["linhas"]
                if novas and novas[0] in linhas:
                    break                           # não mudou de página
                linhas += novas
                dados = novo
                pag += 1
            res = {"login": False, "cab": cab, "linhas": linhas, "paginas": pag, "hora": time.strftime("%H:%M")}
            self.cache[nome] = (time.time(), res)
            log.info("sistema %s: %d linhas em %d páginas", nome, len(linhas), pag)
            return res

    def _eval(self, w, js, json_=True):
        try:
            r = w.evaluate_js(js)
        except Exception:
            log.debug("evaluate_js", exc_info=True)
            return None
        if not json_:
            return r
        try:
            return json.loads(r) if isinstance(r, str) else r
        except Exception:
            return None

    def contexto(self, pergunta):
        s = self.qual(pergunta)
        if not s:
            return None, ""
        try:
            d = self.ler(s)
        except Exception as e:
            log.exception("sistema web")
            return s, f"[Sistema {s['nome']}: não consegui acessar agora ({e}).]"
        if d.get("login"):
            return s, f"[Sistema {s['nome']}: precisa fazer login. Diga ao usuário para abrir CONFIGURAÇÕES > SISTEMAS DA EMPRESA > ENTRAR e fazer o login uma vez.]"
        cab, linhas = d["cab"], d["linhas"]
        termos = [t for t in re.findall(r"[0-9a-z]{2,}", textutil.sem_acento(pergunta.lower()))
                  if t not in {"quais", "qual", "tem", "do", "da", "de", "no", "na", "os", "as", "cnp", "cnps", "me", "fala",
                               "quantos", "quantas", "sistema", "lista", "estao", "esta", "que", "um", "uma", "com"}]
        def fmt(l):
            return " | ".join(f"{cab[i] if i < len(cab) and cab[i] else 'col' + str(i + 1)}={v}" for i, v in enumerate(l) if v)
        escolhidas = linhas
        if termos:
            pont = [(sum(1 for t in termos if t in textutil.sem_acento(" ".join(l).lower())), i, l) for i, l in enumerate(linhas)]
            boas = [x for x in pont if x[0] > 0]
            if boas:
                escolhidas = [l for _, _, l in sorted(boas, key=lambda x: (-x[0], x[1]))]
        texto = [f"[Sistema da empresa: {s['nome']} — {len(linhas)} registros lidos às {d['hora']}]",
                 "Colunas: " + " | ".join(c for c in cab if c)]
        for l in escolhidas[:40]:
            texto.append(fmt(l))
        if len(escolhidas) > 40:
            texto.append(f"... e mais {len(escolhidas) - 40} registros.")
        return s, "\n".join(texto)
