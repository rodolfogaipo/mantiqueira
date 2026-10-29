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
            if "cnp" in s["url"].lower():
                chaves += ["cnp", "cnps", "origus", "syntex"]
            if any(re.search(r"\b" + re.escape(textutil.sem_acento(c.lower())) + r"\b", p) for c in chaves if len(c) >= 3):
                return s
        return None

    # ------------------------------------------------------------------ janela
    def _viva(self):
        if self.janela is None:
            return False
        try:
            self.janela.get_current_url()
            return True
        except Exception:
            self.janela = None
            return False

    def _janela(self, url, visivel):
        import webview
        if not self._viva():
            # nasce visível (minimizada quando é só para ler): janela criada escondida às vezes nem carrega a página
            w = webview.create_window("Mantiqueira — sistema da empresa", url=url, width=1200, height=800,
                                      minimized=not visivel)
            self.janela = w

            def ao_pedir_fechar():
                if getattr(self.n, "saindo", False):
                    return True
                threading.Thread(target=self.esconder, daemon=True).start()   # o X só esconde: o login continua valendo
                return False

            def ao_fechar():
                if self.janela is w:
                    self.janela = None
            w.events.closing += ao_pedir_fechar
            w.events.closed += ao_fechar
            fim = time.time() + 25
            while time.time() < fim:
                try:
                    if w.get_current_url():
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            if not visivel:
                time.sleep(2)
                self.esconder()
        else:
            try:
                if (self.janela.get_current_url() or "").split("#")[0] != url:
                    self.janela.load_url(url)
            except Exception:
                self.janela.load_url(url)
            if visivel:
                self.janela.show()
        return self.janela

    def abrir_para_login(self, sistema):
        with self.lock:
            w = self._janela(sistema["url"], True)
        try:
            w.restore()
            w.show()
        except Exception:
            pass
        self.cache.pop(sistema["nome"], None)
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
                try:
                    url_atual = w.get_current_url()
                except Exception:
                    url_atual = None
                log.info("sistema %s sem resposta; endereço atual: %s", nome, url_atual)
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

    # ------------------------------------------------------------------ teste (botão TESTAR)
    def testar(self, nome):
        s = next((x for x in self.lista() if x["nome"] == nome), None)
        if not s:
            return "Sistema não encontrado."
        self.cache.pop(nome, None)
        try:
            d = self.ler(s, cache_seg=0)
        except Exception as e:
            return f"NÃO CONSEGUI LER ({e}). Clique em ENTRAR, faça o login, espere a lista aparecer e feche."
        if d.get("login"):
            return "PRECISA DE LOGIN: clique em ENTRAR e entre com seu usuário."
        if not d.get("linhas"):
            return "Entrei, mas não achei nenhuma tabela na página."
        return f"OK: li {len(d['linhas'])} registros em {d['paginas']} página(s) às {d['hora']}."

    def estado(self):
        """Avisos para o painel."""
        return [f"O sistema de {n} precisa de login (Configurações > Sistemas da empresa > ENTRAR)." for n in sorted(self.precisa_login)]

    # ------------------------------------------------------------------ aviso de CNP novo / data prevista
    def iniciar_vigia(self):
        threading.Thread(target=self._vigia, daemon=True, name="vigia-cnp").start()

    @staticmethod
    def _coluna(cab, *palavras):
        for i, c in enumerate(cab):
            cn = textutil.sem_acento((c or "").lower())
            if all(p in cn for p in palavras):
                return i
        return None

    @staticmethod
    def _data(txt):
        import datetime as dt
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", txt or "")
        if m:
            a = int(m.group(3))
            try:
                return dt.date(a + 2000 if a < 100 else a, int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", txt or "")
        if m:
            try:
                return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
        return None

    def _vigia(self):
        import datetime as dt
        time.sleep(150)
        while True:
            try:
                cfg = self.n.cfg
                h = dt.datetime.now().hour
                if cfg["avisar_cnp"] and 6 <= h < 20 and getattr(self.n, "pronto", False):
                    for s in self.lista():
                        if "cnp" in s["url"].lower() or "cnp" in s["nome"].lower():
                            self._conferir(s)
            except Exception:
                log.exception("vigia de CNPs")
            time.sleep(max(5, int(self.n.cfg["cnp_intervalo_min"] or 15)) * 60)

    def _conferir(self, s):
        import datetime as dt
        db = self.n.db
        d = self.ler(s, cache_seg=60)
        if d.get("login") or not d.get("linhas"):
            return
        cab, linhas = d["cab"], d["linhas"]
        i_id = self._coluna(cab, "id")
        if i_id is None or (cab[i_id] or "").strip().lower() not in ("id", "#", "código", "codigo", "cód", "cod"):
            i_id = next((i for i, c in enumerate(cab) if textutil.sem_acento((c or "").lower()).strip() in ("id", "#", "codigo", "cod")), None)
        i_prod = self._coluna(cab, "produto")
        i_ped = self._coluna(cab, "pedido")
        i_data = self._coluna(cab, "prev")
        if i_data is None:
            i_data = self._coluna(cab, "data")

        def chave(l):
            return (l[i_id] if i_id is not None and i_id < len(l) else " | ".join(l)).strip()

        def nome(l):
            prod = l[i_prod] if i_prod is not None and i_prod < len(l) else (l[1] if len(l) > 1 else l[0])
            ped = l[i_ped] if i_ped is not None and i_ped < len(l) and l[i_ped] else ""
            return prod + (f", pedido {ped}" if ped else "")
        k_vistos = f"cnp_vistos:{s['nome']}"
        antigos = db.kv_get(k_vistos)
        atuais = [chave(l) for l in linhas]
        db.kv_set(k_vistos, json.dumps(atuais[-3000:], ensure_ascii=False))
        trat = self.n.cfg["tratamento"]
        if antigos is not None:
            vistos = set(json.loads(antigos))
            novos = [l for l in linhas if chave(l) not in vistos]
            if 0 < len(novos) <= 15:
                if len(novos) == 1:
                    self.n.falar_aviso(f"{trat[:1].upper() + trat[1:]}, entrou um CNP novo no sistema: {nome(novos[0])}.")
                else:
                    self.n.falar_aviso(f"{trat[:1].upper() + trat[1:]}, entraram {len(novos)} CNPs novos no sistema: "
                                       + "; ".join(nome(l) for l in novos[:4]) + ".")
        if i_data is None:
            return
        hoje = dt.date.today()
        k_av = f"cnp_datas_avisadas:{hoje}"
        avisados = set(json.loads(db.kv_get(k_av, "[]")))
        for quando, rotulo in ((hoje, "hoje"), (hoje + dt.timedelta(days=1), "amanhã")):
            if rotulo == "hoje" and dt.datetime.now().hour >= 12:
                continue
            lista = []
            for l in linhas:
                if i_data < len(l) and self._data(l[i_data]) == quando:
                    k = f"{chave(l)}:{rotulo}"
                    if k not in avisados:
                        avisados.add(k)
                        lista.append(nome(l))
            if len(lista) == 1:
                self.n.falar_aviso(f"{trat[:1].upper() + trat[1:]}, o CNP {lista[0]} tem data prevista para {rotulo}.")
            elif lista:
                extra = f", e mais {len(lista) - 4}" if len(lista) > 4 else ""
                self.n.falar_aviso(f"{trat[:1].upper() + trat[1:]}, {len(lista)} CNPs têm data prevista para {rotulo}: "
                                   + "; ".join(lista[:4]) + extra + ".")
        db.kv_set(k_av, json.dumps(sorted(avisados), ensure_ascii=False))

    def contexto(self, pergunta):
        """(sistema, texto) para a IA. Em caso de erro/login, o texto explica o problema."""
        s = self.qual(pergunta)
        if not s:
            return None, ""
        try:
            d = self.ler(s)
        except Exception as e:
            log.exception("sistema web")
            return s, f"[Sistema {s['nome']}: não consegui acessar agora ({e}).]"
        if d.get("login"):
            return s, f"[Sistema {s['nome']}: precisa fazer login.]"
        return s, self.formatar(s, d, pergunta)

    def formatar(self, s, d, pergunta):
        cab, linhas = d["cab"], d["linhas"]
        termos = [t for t in re.findall(r"[0-9a-z]{2,}", textutil.sem_acento(pergunta.lower()))
                  if t not in {"quais", "qual", "tem", "do", "da", "de", "no", "na", "os", "as", "cnp", "cnps", "me", "fala",
                               "quantos", "quantas", "sistema", "lista", "estao", "esta", "que", "um", "uma", "com", "origus",
                               "programa", "olha", "ve", "veja", "consulta", "mantiqueira", "dia", "data", "previsto",
                               "prevista", "quando", "para", "pra", "ela", "ele", "isso", "em", "e", "o", "a"}]

        def fmt(l):
            return " | ".join(f"{cab[i] if i < len(cab) and cab[i] else 'col' + str(i + 1)}={v}" for i, v in enumerate(l) if v)
        escolhidas = linhas
        if termos:
            pont = [(sum(1 for t in termos if t in textutil.sem_acento(" ".join(l).lower())), i, l) for i, l in enumerate(linhas)]
            boas = [x for x in pont if x[0] > 0]
            if boas:
                escolhidas = [l for _, _, l in sorted(boas, key=lambda x: (-x[0], x[1]))]
        texto = [f"[DADOS DO SISTEMA DA EMPRESA: {s['nome']} — {len(linhas)} registros lidos às {d['hora']}]",
                 "Colunas: " + " | ".join(c for c in cab if c)]
        for l in escolhidas[:40]:
            texto.append(fmt(l))
        if len(escolhidas) > 40:
            texto.append(f"... e mais {len(escolhidas) - 40} registros.")
        return "\n".join(texto)
