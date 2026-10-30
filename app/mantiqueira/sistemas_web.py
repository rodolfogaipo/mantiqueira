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
  // monta a grade da tabela respeitando células mescladas (rowspan/colspan) e ignorando tabelas dentro de células
  function grade(t){
    var rows = Array.prototype.slice.call(t.rows), ocup = {}, saida = [];
    rows.forEach(function(tr, r){
      var out = [], novos = [], c = 0;
      function pula(){ while (ocup[r + '_' + c] !== undefined){ out[c] = ocup[r + '_' + c]; c++; } }
      var cells = Array.prototype.slice.call(tr.cells), soTh = cells.length > 0;
      cells.forEach(function(cel){
        pula();
        var x = txt(cel), rs = Math.max(1, cel.rowSpan || 1), cs = Math.max(1, cel.colSpan || 1);
        if (cel.tagName !== 'TH') soTh = false;
        for (var dr = 0; dr < rs; dr++) for (var dc = 0; dc < cs; dc++){
          if (dr > 0) ocup[(r + dr) + '_' + (c + dc)] = (dc === 0 ? x : '');
        }
        for (var k = 0; k < cs; k++){ out[c + k] = (k === 0 ? x : ''); }
        novos.push(c);
        c += cs;
      });
      pula();
      for (var i = 0; i < out.length; i++) if (out[i] === undefined) out[i] = '';
      var cab = (tr.parentElement && tr.parentElement.tagName === 'THEAD') || soTh;
      saida.push({c: out, novos: novos, cab: cab, cont: r > 0 && ocup[r + '_0'] !== undefined});
    });
    var cab = [], regs = [];
    saida.forEach(function(l){
      if (l.cab){ if (l.c.filter(function(x){ return x; }).length >= cab.filter(function(x){ return x; }).length) cab = l.c; return; }
      if (!l.c.join('').length) return;
      if (l.cont && regs.length){                       // continuação de um registro com células mescladas
        var ant = regs[regs.length - 1];
        l.novos.forEach(function(i){ if (l.c[i]) ant[i] = ant[i] ? ant[i] + ' ; ' + l.c[i] : l.c[i]; });
      } else regs.push(l.c.slice());
    });
    return {cab: cab, linhas: regs, nlinhas: rows.length};
  }
  var tabelas = [];
  document.querySelectorAll('table').forEach(function(t){
    if (t.parentElement && t.parentElement.closest('td, th')) return;   // tabela dentro de célula: faz parte da outra
    var g = grade(t);
    if (g.linhas.length) tabelas.push(g);
  });
  tabelas.sort(function(a, b){ return b.linhas.length - a.linhas.length; });
  if (!tabelas.length){
    var rows = document.querySelectorAll('[role=row]');
    var cab = [], linhas = [];
    rows.forEach(function(r){
      var hs = r.querySelectorAll('[role=columnheader]');
      if (hs.length){ cab = []; hs.forEach(function(h){ cab.push(txt(h)); }); return; }
      var c = []; r.querySelectorAll('[role=cell],[role=gridcell]').forEach(function(x){ c.push(txt(x)); });
      if (c.length) linhas.push(c);
    });
    if (linhas.length) tabelas.push({cab: cab, linhas: linhas, nlinhas: rows.length});
  }
  var prox = null;
  function livre(b){
    return !(b.disabled || b.getAttribute('aria-disabled') === 'true' || /disabled/.test(b.className) ||
             (b.parentElement && /disabled/.test(b.parentElement.className))) && b.offsetParent !== null;
  }
  // 1º: o botão "próxima página" de paginadores conhecidos (Angular Material, Bootstrap, DataTables…)
  var esp = document.querySelectorAll('.mat-paginator-navigation-next, .mat-mdc-paginator-navigation-next, ' +
    '[aria-label*="róxima" i], [aria-label*="next page" i], [aria-label="Next" i], .paginate_button.next, .page-item.next a, li.next a');
  for (var j = 0; j < esp.length; j++){
    if (livre(esp[j])){ esp[j].setAttribute('data-mantiqueira-prox', '1'); prox = true; break; }
    else { prox = false; break; }                      // achou o paginador e o botão está desligado: última página
  }
  var cands = prox === null ? document.querySelectorAll('button, a, li, [role=button]') : [];
  for (var i = 0; i < cands.length; i++){
    if (cands[i].closest('nav, aside, header, mat-sidenav, .sidebar, .sidenav, .menu, mat-nav-list')) continue;
    var b = cands[i], r = ((b.getAttribute('aria-label') || '') + ' ' + (b.title || '') + ' ' + txt(b) + ' ' + b.className).toLowerCase();
    if (/(pr[oó]xim|next|seguinte|›|»|chevron_right|navigate_next)/.test(r) && !/(últim|ultim|last)/.test(r)){
      var desab = b.disabled || b.getAttribute('aria-disabled') === 'true' || /disabled/.test(b.className) ||
                  (b.parentElement && /disabled/.test(b.parentElement.className));
      if (!desab && b.offsetParent !== null){ b.setAttribute('data-mantiqueira-prox', '1'); prox = true; break; }
    }
  }
  var login = false;
  document.querySelectorAll('input[type=password]').forEach(function(x){ if (x.offsetParent !== null) login = true; });
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

# Lê TODOS os registros direto da fonte da tabela, quando a página usa DataTables (como o Órigus):
# pede ao próprio sistema a lista completa, com a mesma sessão, sem mexer em filtros nem em páginas.
# Cada célula sai com o texto exatamente como aparece na tela (usando as regras de exibição da própria tabela).
JS_DATATABLES = r"""
(async function(){
  var $ = window.jQuery;
  if (!$ || !$.fn || !$.fn.dataTable) return JSON.stringify({erro: 'sem DataTables'});
  var tabs = $.fn.dataTable.tables();
  if (!tabs.length) return JSON.stringify({erro: 'nenhuma tabela DataTables'});
  var melhor = null;
  for (var i = 0; i < tabs.length; i++){ var dti = $(tabs[i]).DataTable(); if (!melhor || dti.columns().count() > melhor.columns().count()) melhor = dti; }
  var dt = melhor, st = dt.settings()[0];
  function texto(h){ var d = document.createElement('div'); d.innerHTML = String(h == null ? '' : h).replace(/<br\s*\/?>/gi, ' '); return (d.innerText || d.textContent || '').replace(/\s+/g, ' ').trim(); }
  var cab = st.aoColumns.map(function(c){ return texto(c.sTitle); });
  var dados = [], total = null;
  if (st.oFeatures.bServerSide){
    var url = dt.ajax.url() || (st.ajax && st.ajax.url) || st.sAjaxSource;
    var base = dt.ajax.params() || {};
    var tipo = (st.ajax && st.ajax.type) || 'GET';
    var pedido = $.extend(true, {}, base);
    pedido.start = 0; pedido.length = 100000; pedido.draw = (pedido.draw || 1) + 1000;
    if (pedido.search) pedido.search.value = '';
    (pedido.columns || []).forEach(function(c){ if (c.search) c.search.value = ''; });
    var r = await $.ajax({url: url, data: pedido, type: tipo, dataType: 'json'});
    var src = st.sAjaxDataProp !== undefined ? st.sAjaxDataProp : 'data';
    dados = (src ? (r[src] || r.data || r.aaData) : r) || [];
    total = r.recordsTotal || r.iTotalRecords || null;
    if (total && dados.length < total){
      // o servidor limitou o tamanho: busca o resto em blocos
      var passo = dados.length || 100, ini = dados.length;
      while (ini < total && ini < 20000){
        var p2 = $.extend(true, {}, pedido); p2.start = ini; p2.length = passo; p2.draw += 1;
        var r2 = await $.ajax({url: url, data: p2, type: tipo, dataType: 'json'});
        var d2 = (src ? (r2[src] || r2.data || r2.aaData) : r2) || [];
        if (!d2.length) break;
        dados = dados.concat(d2); ini += d2.length;
      }
    }
  } else {
    dados = dt.rows().data().toArray();
    total = dados.length;
  }
  var linhas = dados.map(function(row, ri){
    return st.aoColumns.map(function(c, ci){
      try { var v = c.fnGetData(row, 'display', {settings: st, row: ri, col: ci});
            if (v === row || (v && typeof v === 'object')) v = c.sDefaultContent || '';
            var t = texto(v); return t === '[object Object]' ? '' : t; }
      catch (e) { try { return texto(row[c.mData]); } catch (e2) { return ''; } }
    });
  });
  return JSON.stringify({cab: cab, linhas: linhas, total: total, servidor: !!st.oFeatures.bServerSide});
})()
"""

# diagnóstico da página (vai para o log)
JS_DIAG = r"""
(function(){
  var o = {url: location.href, w: innerWidth, h: innerHeight, pronto: document.readyState, visivel: document.visibilityState};
  o.tabelas = Array.prototype.map.call(document.querySelectorAll('table'), function(t){ return t.rows.length; }).slice(0, 8);
  o.tr = document.querySelectorAll('tr').length;
  o.matrow = document.querySelectorAll('mat-row, tr.mat-row, tr.mat-mdc-row, [role=row]').length;
  o.virtual = document.querySelectorAll('cdk-virtual-scroll-viewport').length;
  var pag = document.querySelector('.mat-paginator-range-label, .mat-mdc-paginator-range-label, .dataTables_info, .pagination-info');
  o.paginador = pag ? (pag.innerText || '').trim() : '';
  o.filtros = [];
  document.querySelectorAll('input').forEach(function(i){ if (i.value && i.type !== 'password' && i.type !== 'hidden') o.filtros.push((i.placeholder || i.name || i.id || '?') + '=' + i.value); });
  return JSON.stringify(o);
})()
"""

# limpa os filtros da tela (botão "Limpar")
JS_LIMPAR = r"""
(function(){
  var bs = document.querySelectorAll('button, a, [role=button]');
  for (var i = 0; i < bs.length; i++){
    var t = (bs[i].innerText || '').replace(/\s+/g, ' ').trim().toLowerCase();
    if (/(^|\s)limpar( filtros)?$/.test(t) && bs[i].offsetParent !== null && !bs[i].disabled){ bs[i].click(); return true; }
  }
  return false;
})()
"""

# abre o seletor "registros por página" (mat-select ou parecido) — depois JS_TAMANHO_MAIOR escolhe o maior
JS_TAMANHO_ABRIR = r"""
(function(){
  var sels = document.querySelectorAll('mat-select, .mat-select, .mat-mdc-select, [role=combobox], [role=listbox]');
  for (var i = 0; i < sels.length; i++){
    var t = (sels[i].innerText || '').trim();
    if (/^\d{1,3}$/.test(t) && sels[i].offsetParent !== null){ sels[i].click(); return t; }
  }
  return '';
})()
"""
JS_TAMANHO_MAIOR = r"""
(function(){
  var ops = document.querySelectorAll('mat-option, .mat-option, .mat-mdc-option, [role=option]'), melhor = null, max = 0;
  ops.forEach(function(o){ var n = parseInt((o.innerText || '').trim(), 10); if (n > max){ max = n; melhor = o; } });
  if (melhor){ melhor.click(); return max; }
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}));
  return 0;
})()
"""

# rola a tabela (ou a página) um pouco para baixo; devolve true se andou
JS_ROLAR = r"""
(function(){
  var t = document.querySelector('cdk-virtual-scroll-viewport') || document.querySelector('table');
  var el = t;
  while (el && el !== document.body){
    var cs = getComputedStyle(el);
    if (el.scrollHeight > el.clientHeight + 5 && /(auto|scroll)/.test(cs.overflowY)){
      var antes = el.scrollTop; el.scrollTop = antes + el.clientHeight * 0.7; return el.scrollTop !== antes;
    }
    el = el.parentElement;
  }
  var y = window.scrollY; window.scrollBy(0, Math.max(300, innerHeight * 0.7));
  var s = document.scrollingElement; if (s && window.scrollY === y){ var a = s.scrollTop; s.scrollTop = a + innerHeight * 0.7; return s.scrollTop !== a; }
  return window.scrollY !== y;
})()
"""
JS_TOPO = "(function(){window.scrollTo(0,0); var v=document.querySelector('cdk-virtual-scroll-viewport'); if(v) v.scrollTop=0; document.querySelectorAll('*').forEach(function(e){ if(e.scrollTop>0) e.scrollTop=0; }); return true;})()"

JS_PROXIMA = "(function(){var b=document.querySelector('[data-mantiqueira-prox]'); if(b){b.removeAttribute('data-mantiqueira-prox'); b.click(); return true;} return false;})()"


class SistemasWeb:
    def __init__(self, nucleo):
        self.n = nucleo
        self.janela = None
        self.lock = threading.Lock()
        self.cache = {}            # nome → (hora, dados)
        self._login_aberto = False
        self.aviso_login = ""
        self.ultimos = {}          # nome → últimos dados lidos (para reconhecer produtos citados sem "CNP")
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
    # ------------------------------------------------------------------ navegador próprio (Edge/Chrome do Windows)
    # O sistema é lido por um navegador separado, sem janela (modo "headless"), controlado pelo Playwright.
    # O login é feito uma vez numa janela desse mesmo navegador e fica guardado no perfil dados/navegador_sistemas.
    def _abrir_navegador(self, pw, sem_janela):
        from . import paths
        perfil = paths.DADOS / "navegador_sistemas"
        perfil.mkdir(parents=True, exist_ok=True)
        opcoes = dict(user_data_dir=str(perfil), headless=sem_janela, locale="pt-BR", ignore_https_errors=True,
                      args=["--disable-features=Translate", "--no-first-run", "--no-default-browser-check"])
        if sem_janela:
            opcoes["viewport"] = {"width": 1600, "height": 2000}
        else:
            opcoes["no_viewport"] = True
            opcoes["args"] = opcoes["args"] + ["--start-maximized"]
        erro = None
        for canal in ("msedge", "chrome", None):
            try:
                if canal is None:
                    return pw.chromium.launch_persistent_context(**opcoes)
                return pw.chromium.launch_persistent_context(channel=canal, **opcoes)
            except Exception as e:
                erro = e
                log.info("navegador %s indisponível: %s", canal, str(e).splitlines()[0][:200])
        raise RuntimeError(f"não encontrei o Edge nem o Chrome neste computador ({erro})")

    def _avaliar(self, page, js, json_=True):
        try:
            r = page.evaluate(js)
        except Exception as e:
            log.info("script na página falhou: %s", str(e).splitlines()[0][:200])
            return None
        if not json_:
            return r
        try:
            return json.loads(r) if isinstance(r, str) else r
        except Exception:
            return None

    def abrir_para_login(self, sistema):
        """Abre uma janela do navegador no sistema para o usuário entrar. Fecha sozinha quando a lista aparece."""
        if self._login_aberto:
            return True
        threading.Thread(target=self._login, args=(sistema,), daemon=True, name="login-sistema").start()
        return True

    def _login(self, sistema):
        from playwright.sync_api import sync_playwright
        if not self.lock.acquire(timeout=120):
            log.info("login: o navegador está ocupado lendo o sistema")
            return
        self._login_aberto = True
        try:
            with sync_playwright() as pw:
                ctx = self._abrir_navegador(pw, sem_janela=False)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.goto(sistema["url"], wait_until="domcontentloaded", timeout=30000)
                    vista = 0
                    fim = time.time() + 900                 # até 15 minutos para fazer o login
                    while time.time() < fim:
                        if page.is_closed() or not ctx.pages:
                            break
                        d = self._avaliar(page, JS_LER)
                        if d and d.get("tabelas") and not d.get("login"):
                            vista += 1
                            if vista >= 3:                  # lista apareceu: login feito
                                log.info("login no sistema %s confirmado", sistema["nome"])
                                self.precisa_login.discard(sistema["nome"])
                                self.cache.pop(sistema["nome"], None)
                                self.aviso_login = f"Login no sistema de {sistema['nome']} feito. Pode me perguntar."
                                try:
                                    self.n.falar_aviso(f"Pronto, o login no sistema de {sistema['nome']} está feito. "
                                                       f"Já pode me perguntar sobre os {sistema['nome']}.")
                                except Exception:
                                    pass
                                time.sleep(1.5)
                                break
                        else:
                            vista = 0
                        time.sleep(1)
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
        except Exception:
            log.exception("janela de login do sistema")
        finally:
            self._login_aberto = False
            self.lock.release()

    def esconder(self):
        pass                                             # o navegador de leitura não tem janela

    def _coletar(self, page, chaves, linhas, cab_ref):
        """Lê a página atual inteira, rolando a tabela (tabelas que só desenham as linhas visíveis)."""
        self._avaliar(page, JS_TOPO, json_=False)
        time.sleep(0.4)
        ultimo = None
        for _ in range(80):
            d = self._avaliar(page, JS_LER)
            if d and d["tabelas"]:
                t = d["tabelas"][0]
                if not cab_ref and t["cab"]:
                    cab_ref.extend(t["cab"])
                for l in t["linhas"]:
                    k = " | ".join(l[:3])
                    if k not in chaves:
                        chaves.add(k)
                        linhas.append(l)
                ultimo = d
            if not self._avaliar(page, JS_ROLAR, json_=False):
                break
            time.sleep(0.5)
        return ultimo

    def ler(self, sistema, max_paginas=60, cache_seg=180):
        nome = sistema["nome"]
        c = self.cache.get(nome)
        if c and time.time() - c[0] < cache_seg:
            return c[1]
        if self._login_aberto:
            raise RuntimeError("a janela de login ainda está aberta; termine o login e feche a janela")
        if not self.lock.acquire(timeout=90):
            raise RuntimeError("o sistema ainda está sendo lido; pergunte de novo em instantes")
        try:
            from playwright.sync_api import sync_playwright
            inicio = time.time()
            apis = []
            with sync_playwright() as pw:
                ctx = self._abrir_navegador(pw, sem_janela=True)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    page.set_default_timeout(20000)

                    def resposta(r):
                        try:
                            if r.request.resource_type in ("xhr", "fetch") and len(apis) < 15:
                                apis.append(f"{r.status} {r.request.method} {r.url[:160]}")
                        except Exception:
                            pass
                    page.on("response", resposta)
                    page.goto(sistema["url"], wait_until="domcontentloaded", timeout=30000)
                    dados = None
                    for _ in range(25):                   # espera a tabela (ou a tela de login) aparecer
                        dados = self._avaliar(page, JS_LER)
                        if dados and dados["tabelas"]:
                            break
                        time.sleep(1)
                    log.info("sistema %s: diagnóstico %s", nome, self._avaliar(page, JS_DIAG, json_=False))
                    if not dados:
                        raise RuntimeError("a página não respondeu")
                    if not dados["tabelas"]:
                        if dados["login"]:
                            self.precisa_login.add(nome)
                            return {"login": True}
                        raise RuntimeError("a página abriu, mas não mostrou a lista")
                    self.precisa_login.discard(nome)
                    # 1º caminho (o certo): a lista completa direto da fonte da tabela, sem mexer em nada na tela
                    api = self._avaliar(page, JS_DATATABLES)
                    if api and api.get("linhas"):
                        cab, linhas = api["cab"], api["linhas"]
                        pag = 1
                        log.info("sistema %s: lidos %d registros direto da tabela (total informado: %s)", nome,
                                 len(linhas), api.get("total"))
                        res = {"login": False, "cab": cab, "linhas": linhas, "paginas": 1, "hora": time.strftime("%H:%M"),
                               "total": api.get("total")}
                        self.cache[nome] = (time.time(), res)
                        self.ultimos[nome] = res
                        log.info("sistema %s: colunas %s", nome, " | ".join(cab))
                        for l in linhas[:2]:
                            log.info("sistema %s: exemplo %s", nome, " | ".join(l)[:400])
                        return res
                    log.info("sistema %s: leitura direta indisponível (%s); lendo a tela", nome, (api or {}).get("erro"))
                    # 2º caminho: ler a tela página por página (sem mexer em filtros nem em seletores)
                    if False and self._avaliar(page, JS_LIMPAR, json_=False):
                        log.info("sistema %s: filtros limpos", nome)
                        time.sleep(3)
                    # (não mexe em seletores: um "Criado por" com números já filtrou a lista por engano)
                    log.info("sistema %s: depois de preparar %s", nome, self._avaliar(page, JS_DIAG, json_=False))
                    cab, linhas, chaves = [], [], set()
                    ultimo = self._coletar(page, chaves, linhas, cab)
                    pag = 1
                    while ultimo and ultimo.get("proxima") and pag < max_paginas and time.time() - inicio < 150:
                        antes = len(linhas)
                        if not self._avaliar(page, JS_PROXIMA, json_=False):
                            break
                        time.sleep(1.8)
                        ultimo = self._coletar(page, chaves, linhas, cab)
                        if len(linhas) == antes:
                            break                       # não mudou de página
                        pag += 1
                finally:
                    try:
                        ctx.close()
                    except Exception:
                        pass
            if apis:
                log.info("sistema %s: chamadas da página: %s", nome, " ; ".join(apis))
            res = {"login": False, "cab": cab, "linhas": linhas, "paginas": pag, "hora": time.strftime("%H:%M")}
            self.cache[nome] = (time.time(), res)
            self.ultimos[nome] = res
            log.info("sistema %s: %d linhas em %d páginas (%.0f s)", nome, len(linhas), pag, time.time() - inicio)
            log.info("sistema %s: colunas %s", nome, " | ".join(cab))
            for l in linhas[:2]:
                log.info("sistema %s: exemplo %s", nome, " | ".join(l)[:400])
            return res
        finally:
            self.lock.release()

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
        m = self._mapa(cab)
        i_id, i_prod, i_ped, i_data = m.get("id"), m.get("produto"), m.get("pedido"), m.get("prevista")

        def chave(l):
            return (l[i_id] if i_id is not None and i_id < len(l) else " | ".join(l)).strip()

        def nome(l):
            prod = l[i_prod] if i_prod is not None and i_prod < len(l) else (l[1] if len(l) > 1 else l[0])
            prod = re.split(r"\s+similar:", prod, flags=re.I)[0].strip()
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

    # ------------------------------------------------------------------ respostas exatas (sem a IA)
    CAMPOS = [  # chave, palavras do cabeçalho, como falar
        ("id", ("id",), "número"),
        ("produto", ("produto",), "produto"),
        ("pedido", ("pedido",), "pedido"),
        ("linha", ("linha",), "linha"),
        ("carga", ("carga",), "carga"),
        ("qtd", ("qtd", "quantidade", "pecas"), "quantidade de peças"),
        ("prevista", ("prevista", "previsao"), "data prevista"),
        ("aprovacao", ("aprovacao", "gerencia"), "aprovação da gerência"),
        ("setores", ("setores", "setor"), "setores"),
        ("status", ("status", "situacao"), "status"),
        ("criado_por", ("criado por", "criado", "responsavel"), "criado por"),
        ("criacao", ("data criacao", "criacao", "cadastro"), "data de criação"),
    ]
    PERGUNTA_CAMPO = [
        ("prevista", r"previst|previs|prazo|entrega|fica pronto|vai ficar pronto|data prevista"),
        ("aprovacao", r"aprova|gerencia"),
        ("setores", r"setor|setores|pendente|tubular|pintura|montagem|embalagem|atelie|engenharia"),
        ("status", r"status|situacao|como esta|andamento"),
        ("criado_por", r"quem criou|quem cadastrou|criado por|cadastrado por|quem fez"),
        ("criacao", r"quando (foi )?(criad|cadastrad|entrou|gerad|feit)|data de criacao|data da criacao|criad[oa] em|cadastrad[oa] em|"
                    r"gerad[oa]|criad[oa]|cadastrad[oa]"),
        ("pedido", r"\bpedido\b"),
        ("qtd", r"quantas pecas|qtd|quantidade"),
        ("linha", r"\blinha\b"),
        ("carga", r"\bcarga\b"),
    ]

    def citado_sem_nome(self, pergunta):
        """Pergunta sobre um produto que está no sistema, sem dizer 'CNP' ('quando a banqueta miches foi criada?')."""
        p = textutil.sem_acento(pergunta.lower())
        if not re.search(r"criad|gerad|cadastrad|previs|prazo|entrega|aprova|pedido|setor|status|situacao|pronto|pronta|"
                         r"quantas pecas|quem criou|andamento|data", p):
            return None
        palavras = [w for w in re.findall(r"[a-z0-9]{4,}", p) if w not in {"quando", "qual", "quais", "data", "pedido", "criado",
                    "criada", "gerado", "gerada", "prevista", "previsto", "foi", "esta", "sistema", "status", "setor", "setores",
                    "aprovacao", "gerencia", "pronto", "pronta", "entrega", "prazo", "cadastrado", "cadastrada", "dele", "dela"}]
        if not palavras:
            return None
        for s in self.lista():
            d = self.ultimos.get(s["nome"]) or (self.cache.get(s["nome"]) or (0, None))[1]
            if not d or not d.get("linhas"):
                continue
            m = self._mapa(d["cab"])
            i = m.get("produto")
            if i is None:
                continue
            for l in d["linhas"]:
                prod = textutil.sem_acento((l[i] if i < len(l) else "").lower())
                if sum(1 for w in palavras if re.search(r"\b" + re.escape(w), prod)) >= min(2, len(palavras)):
                    return s
            if re.search(r"\bpedido\s*\d{4,}", p):
                return s
        # ainda sem dados guardados: perguntas típicas de CNP vão para o sistema de CNPs
        if re.search(r"foi (criad|gerad|cadastrad)|data prevista|previsao de entrega|aprovacao da gerencia|quem criou|"
                     r"status geral|setores? (da|do)", p):
            return next((s for s in self.lista() if "cnp" in (s["url"] + s["nome"]).lower()), None)
        return None

    def _mapa(self, cab):
        mapa = {}
        cabn = [textutil.sem_acento((c or "").lower()).strip() for c in cab]
        for chave, palavras, _ in self.CAMPOS:
            for p in palavras:                          # primeiro: cabeçalho exatamente igual; depois: contém
                for i, c in enumerate(cabn):
                    if i not in mapa.values() and (c == p):
                        mapa[chave] = i
                        break
                if chave in mapa:
                    break
            if chave not in mapa:
                for p in palavras:
                    for i, c in enumerate(cabn):
                        if i not in mapa.values() and p in c and not (chave == "criacao" and "por" in c) \
                                and not (chave == "criado_por" and "data" in c):
                            mapa[chave] = i
                            break
                    if chave in mapa:
                        break
        return mapa

    def responder(self, s, d, pergunta):
        """Resposta montada direto da tabela, para não haver erro. None = deixa a IA responder com os dados."""
        import datetime as dt
        cab, linhas = d["cab"], d["linhas"]
        m = self._mapa(cab)
        if "produto" not in m:
            return None
        p = textutil.sem_acento(pergunta.lower())

        def v(l, k):
            i = m.get(k)
            x = (l[i].strip() if i is not None and i < len(l) else "")
            return "" if x in ("-", "—") else x

        def nome(l):
            prod = v(l, "produto")
            prod = re.split(r"\s+similar:", prod, flags=re.I)[0].strip()
            return f"CNP {v(l, 'id')}, {prod}" if v(l, "id") else prod

        def ficha(l):
            partes = [nome(l)]
            for k, _, fala in self.CAMPOS[2:]:
                x = v(l, k)
                if x and x != "-":
                    partes.append(f"{fala}: {x}")
            return "; ".join(partes)
        self.n.detalhe_texto = ""
        campo = next((k for k, rx in self.PERGUNTA_CAMPO if re.search(rx, p) and k in m), None)
        # data citada (ontem, hoje, 28/10…) → filtrar pela coluna de data
        alvo_data = None
        if re.search(r"\bontem\b", p):
            alvo_data = dt.date.today() - dt.timedelta(days=1)
        elif re.search(r"\banteontem\b", p):
            alvo_data = dt.date.today() - dt.timedelta(days=2)
        elif re.search(r"\bhoje\b", p):
            alvo_data = dt.date.today()
        elif re.search(r"\bamanha\b", p):
            alvo_data = dt.date.today() + dt.timedelta(days=1)
        else:
            md = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", p)
            if md:
                ano = int(md.group(3)) if md.group(3) else dt.date.today().year
                ano = ano + 2000 if ano < 100 else ano
                try:
                    alvo_data = dt.date(ano, int(md.group(2)), int(md.group(1)))
                except ValueError:
                    alvo_data = None
        ignorar = {"cnp", "cnps", "origus", "syntex", "sistema", "programa", "qual", "quais", "quanto", "quantos", "quantas",
                   "data", "dia", "prevista", "previsto", "previsao", "da", "do", "de", "na", "no", "o", "a", "os", "as", "e",
                   "tem", "que", "ta", "esta", "estao", "me", "fala", "diz", "pra", "para", "qual", "quando", "foi", "foram",
                   "ontem", "hoje", "amanha", "anteontem", "um", "uma", "mantiqueira", "senhor", "aprovacao", "gerencia",
                   "aprovado", "aprovados", "aprovada", "aprovadas", "criado", "criados", "criada", "criadas", "cadastrado",
                   "cadastrados", "status", "pedido", "setor", "setores", "lista", "listar", "mostra", "olha", "ve", "veja",
                   "consulta", "fica", "pronto", "pronta", "entrega", "prazo", "quem", "criou", "por", "favor", "todos",
                   "todas", "novo", "novos", "nova", "novas", "agora", "ai", "la", "em", "com", "pecas", "qtd", "quantidade",
                   "linha", "carga", "situacao", "andamento", "como", "pendente", "pendentes", "ultimo", "ultimos",
                   "teve", "tiveram", "houve", "ha", "existe", "existem", "algum", "alguma", "alguns", "algumas", "sao",
                   "sobre", "saber", "quero", "preciso", "ver", "informacao", "informacoes", "registro", "registros",
                   "nele", "nela", "dele", "dela", "isso", "esse", "essa", "deu", "tudo"}
        termos = [t for t in re.findall(r"[a-z0-9]{2,}", p) if t not in ignorar and not re.fullmatch(r"\d{1,2}|\d{4}", t)]
        escolhidas = linhas
        if termos:
            def pontos(l):
                alvo = textutil.sem_acento(" ".join([v(l, "produto"), v(l, "id"), v(l, "pedido"), v(l, "linha")]).lower())
                return sum(1 for t in termos if re.search(r"\b" + re.escape(t), alvo))
            pont = [(pontos(l), l) for l in linhas]
            melhor = max((x[0] for x in pont), default=0)
            if melhor == 0 and alvo_data:
                termos = []
            elif melhor == 0:
                return (f"Li {len(linhas)} CNPs no sistema e não encontrei nenhum com \"{' '.join(termos)}\", "
                        f"{self.n.cfg['tratamento']}.")
            # o nome do produto (sem o "Similar") tem prioridade
            escolhidas = [l for pt, l in pont if pt == melhor] if termos else linhas
            exatas = [] if not termos else [l for l in escolhidas if all(re.search(r"\b" + re.escape(t), textutil.sem_acento(nome(l).lower()))
                                                   for t in termos)]
            escolhidas = exatas or escolhidas
        if alvo_data:
            col = campo if campo in ("prevista", "aprovacao", "criacao") else ("criacao" if "criacao" in m else "prevista")
            escolhidas = [l for l in escolhidas if self._data(v(l, col)) == alvo_data]
            rot = {"criacao": "criados", "aprovacao": "aprovados pela gerência", "prevista": "com data prevista para"}[col]
            rot1 = {"criacao": "criado", "aprovacao": "aprovado pela gerência", "prevista": "com data prevista para"}[col]
            quando = alvo_data.strftime("%d/%m/%Y")
            if not escolhidas:
                return f"Nenhum CNP {rot1} {quando}, {self.n.cfg['tratamento']}. Li {len(linhas)} CNPs no sistema."
            self.n.detalhe_texto = "\n".join(ficha(l) for l in escolhidas[:30])
            if len(escolhidas) == 1:
                return f"Um CNP {rot1} {quando}: {ficha(escolhidas[0])}."
            return (f"{len(escolhidas)} CNPs {rot} {quando}: " + "; ".join(nome(l) for l in escolhidas[:6])
                    + ". A lista completa está na tela.")
        if termos:
            self.n.detalhe_texto = "\n".join(ficha(l) for l in escolhidas[:20])
            if campo:
                fala = next(f for k, _, f in self.CAMPOS if k == campo)
                if len(escolhidas) == 1:
                    return f"{nome(escolhidas[0])}: {fala} {v(escolhidas[0], campo) or 'não preenchido'}."
                return f"Encontrei {len(escolhidas)}: " + "; ".join(f"{nome(l)}, {fala} {v(l, campo) or 'não preenchido'}"
                                                              for l in escolhidas[:5]) + "."
            if len(escolhidas) == 1:
                return ficha(escolhidas[0]) + "."
            return f"Encontrei {len(escolhidas)} CNPs: " + "; ".join(nome(l) for l in escolhidas[:6]) + ". Os detalhes estão na tela."
        if re.search(r"\b(quais|quantos|lista|listar|mostra|todos)\b", p):
            self.n.detalhe_texto = "\n".join(ficha(l) for l in linhas[:60])
            prim = "; ".join(f"{nome(l)}, previsto {v(l, 'prevista') or 'sem data'}" for l in linhas[:5])
            return f"Há {len(linhas)} CNPs no sistema. Os primeiros: {prim}. A lista está na tela."
        return None

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
