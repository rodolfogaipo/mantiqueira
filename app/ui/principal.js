/* Mantiqueira — tela principal */
(function(){
  var palco = $('palco');
  function escalar(){
    var s = Math.min(window.innerWidth / 1440, window.innerHeight / 900);
    var x = (window.innerWidth - 1440*s) / 2, y = (window.innerHeight - 900*s) / 2;
    palco.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')';
  }
  window.addEventListener('resize', escalar); escalar();

  $('tkO').setAttribute('d', marcacoes(300,300,280,2,10,5,14));
  $('tkI').setAttribute('d', marcacoes(300,300,158,6,30,4,10));
  $('arcA').setAttribute('d', arco(300,300,186,120,165));

  /* espectro de voz */
  var eq = $('eq'), barras = [], i;
  for (i = 0; i < 56; i++){
    var b = document.createElement('div');
    var k = Math.abs(Math.sin(i*.55)*Math.cos(i*.17)), c = 1 - Math.abs(i-27.5)/28;
    b.style.height = Math.round(4 + 24*k*(.35+.65*c)) + 'px';
    b.style.background = (i % 9 === 4) ? 'var(--al)' : 'var(--p)';
    eq.appendChild(b); barras.push(b);
  }

  /* relógio */
  var DIAS = ['DOM','SEG','TER','QUA','QUI','SEX','SÁB'];
  function relogio(){
    var d = new Date();
    $('hm').textContent = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
    $('sec').textContent = ':' + String(d.getSeconds()).padStart(2,'0');
    $('data').textContent = DIAS[d.getDay()] + ' ' + String(d.getDate()).padStart(2,'0') + '.' + String(d.getMonth()+1).padStart(2,'0') + '.' + d.getFullYear();
  }
  relogio(); setInterval(relogio, 1000);

  /* holograma 3D: modelo de CAD (pérgola) ou um "documento" para os demais programas */
  var hF = $('hF'), hS = $('hS'), hB = $('hB'), rot = $('rot');
  var formaCad = true;
  function desenhar(ang){
    var ca = Math.cos(ang), sa = Math.sin(ang), ce = Math.cos(.42), se = Math.sin(.42), S = 62, cx = 170, cy = 158;
    function P(x,y,z){ var xr = x*ca - y*sa, yr = x*sa + y*ca; return (cx + S*xr).toFixed(1) + ' ' + (cy - S*z*ce + S*yr*se*.9).toFixed(1); }
    function L(a,b){ return 'M' + P(a[0],a[1],a[2]) + 'L' + P(b[0],b[1],b[2]); }
    var f = '', s = '', bb = '', j;
    if (formaCad){
      var W = 1.25, D = 1.0, H = 1.3, C = [[-W,-D],[W,-D],[W,D],[-W,D]];
      C.forEach(function(q){ f += L([q[0],q[1],0],[q[0],q[1],H]); });
      for (j = 0; j < 4; j++){ var a = C[j], e = C[(j+1)%4]; f += L([a[0],a[1],H],[e[0],e[1],H]); bb += L([a[0],a[1],0],[e[0],e[1],0]); }
      f += L([-W,-D,H-.12],[W,-D,H-.12]) + L([-W,D,H-.12],[W,D,H-.12]);
      for (j = 1; j < 16; j++){ var y = -D + 2*D*j/16; s += L([-W,y,H+.04],[W,y,H+.04]); }
    } else {
      var w = .85, h = 1.1, z0 = .55;
      var R = [[-w,0,z0-h/2+.6],[w,0,z0-h/2+.6],[w,0,z0+h/2+.6],[-w,0,z0+h/2+.6]];
      for (j = 0; j < 4; j++){ f += L(R[j], R[(j+1)%4]); }
      for (j = 1; j < 9; j++){ var zz = z0+h/2+.6 - j*h/9.5, ww = (j % 3 === 0) ? w*.4 : w*.75; s += L([-w*.8,0,zz],[-w*.8 + 2*ww,0,zz]); }
      var CC = [[-1.1,-1.1],[1.1,-1.1],[1.1,1.1],[-1.1,1.1]];
      for (j = 0; j < 4; j++){ var a2 = CC[j], e2 = CC[(j+1)%4]; bb += L([a2[0],a2[1],0],[e2[0],e2[1],0]); }
    }
    hF.setAttribute('d', f); hS.setAttribute('d', s); hB.setAttribute('d', bb);
    rot.textContent = 'ROT ' + String(Math.round(((ang*180/Math.PI) % 360 + 360) % 360)).padStart(3,'0') + '°';
  }
  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var estadoAtual = 'carregando', t0 = null, nivel = 0;
  function quadro(t){
    if (t0 === null) t0 = t;
    desenhar(.6 + (t - t0) / 2400);
    var alvo = estadoAtual === 'gravando' ? 1 : (estadoAtual === 'falando' ? .8 : (estadoAtual === 'pensando' || estadoAtual === 'transcrevendo' ? .35 : .08));
    nivel += (alvo - nivel) * .15;
    for (var j = 0; j < barras.length; j++){
      var v = nivel * (.35 + .65 * Math.abs(Math.sin(t/180 + j*.7) * Math.cos(t/330 + j*.23)));
      barras[j].style.transform = 'scaleY(' + Math.max(.12, v).toFixed(2) + ')';
    }
    requestAnimationFrame(quadro);
  }
  desenhar(.6); if (!reduz) requestAnimationFrame(quadro);

  /* ---------------------------------------------------------------- estado */
  var ultimo = null;
  function segs(pct, warn){
    var on = Math.round(20 * Math.max(0, Math.min(1, pct))), h = '';
    for (var j = 0; j < 20; j++) h += '<span class="' + (j < on ? (warn ? 'warn' : 'on') : '') + '"></span>';
    return h;
  }
  function falta(iso){
    var ms = new Date(iso).getTime() - Date.now();
    if (ms <= 0) return 'AGORA';
    var m = Math.floor(ms / 60000), hh = Math.floor(m / 60), mm = m % 60;
    if (hh >= 24) return 'EM ' + Math.floor(hh / 24) + ' DIA(S)';
    return 'T-' + String(hh).padStart(2,'0') + ':' + String(mm).padStart(2,'0');
  }
  var REP = {diario:'TODO DIA', semanal:'TODA SEMANA', dias_uteis:'DIAS ÚTEIS'};

  function render(e){
    ultimo = e;
    aplicarTema(e.tema);
    estadoAtual = e.estado;
    palco.classList.toggle('rapido', e.estado === 'pensando' || e.estado === 'transcrevendo');
    $('stCpu').textContent = e.cpu + '%';
    $('stRam').textContent = e.ram;
    $('stGpu').textContent = e.gpu;
    $('stModo').textContent = e.modo_ia + (e.dispositivo && e.dispositivo !== '—' ? ' · ' + e.dispositivo : '');
    $('coreTxt').textContent = e.pronto ? rotuloEstado(e) : 'CARREGANDO';
    $('coreSub').textContent = e.latencia ? ('ÚLTIMA RESPOSTA ' + String(e.latencia).replace('.', ',') + 's') : ' ';
    $('boot').hidden = !e.boot;
    $('boot').textContent = e.boot || '';

    /* arco medidor: percentual de subsistemas ok */
    var ok = (e.sub || []).filter(function(s){ return !s.alerta || s.nome === 'VISÃO'; }).length;
    var pct = (e.sub && e.sub.length) ? ok / e.sub.length : 0;
    $('arcM').setAttribute('d', arco(300,300,200,-40,-40 + 260*pct));

    /* agenda */
    var ag = e.agenda || [];
    $('agN').textContent = String(ag.length).padStart(2,'0');
    if (!ag.length){
      $('agenda').innerHTML = '<div class="vazio">Nenhum lembrete marcado.<br>Diga <b>"Mantiqueira, me lembra às 11 de enviar o DXF"</b> ou digite abaixo.</div>';
    } else {
      $('agenda').innerHTML = ag.map(function(l, k){
        var barra = k === 0 ? '<div class="barra"><span style="width:120px;background:var(--al)"></span><span style="width:100px;background:var(--pd)"></span></div>' : '';
        var sub = falta(l.quando) + (l.repetir ? ' · ' + (REP[l.repetir] || '') : '');
        return '<div class="ag' + (k === 0 ? ' prox' : '') + '"><div class="t' + (k === 0 ? ' aglow' : '') + '">' + esc(l.hora) +
               '<span class="dia">' + esc(l.dia) + '</span></div><div style="min-width:0"><div class="n">' + esc(l.texto) + '</div>' +
               barra + '<div class="s">' + esc(sub) + '</div></div></div>';
      }).join('');
    }

    /* subsistemas */
    $('sys').innerHTML = (e.sub || []).map(function(s){
      return '<div class="sys"><span>' + esc(s.nome) + '</span><div class="segs">' + segs(s.pct, s.alerta) +
             '</div><span style="color:var(--hi);text-align:right">' + esc(s.val) + '</span></div>';
    }).join('');

    /* foco */
    var f = e.foco;
    if (f){
      formaCad = !!f.cad;
      $('holoTipo').textContent = f.cad ? 'MODELO 3D' : 'DOCUMENTO';
      $('fApp').textContent = f.app;
      $('fArq').textContent = f.arquivo || '—';
      $('fInfo').textContent = 'HOJE: ' + f.tempo.toUpperCase() + (f.nao_salvo ? ' · ALTERAÇÕES NÃO SALVAS' : '');
    } else {
      $('fApp').textContent = '—'; $('fArq').textContent = ' ';
      $('fInfo').textContent = 'AGUARDANDO ATIVIDADE';
    }
    $('rec').hidden = !(e.sub || []).some(function(s){ return s.nome === 'VISÃO' && s.val === 'REC'; });

    /* pendências */
    var pd = e.pendencias || [];
    $('pendBox').hidden = !pd.length;
    $('linhaPend').style.display = pd.length ? '' : 'none';
    if (pd.length){
      $('pendTxt').textContent = pd[0].texto;
      $('pendN').textContent = pd.length > 1 ? '+' + (pd.length - 1) : '';
      $('pAbrir').hidden = !pd[0].arquivo;
    }

    /* registro */
    var rg = e.registro || [];
    $('reg').innerHTML = rg.length ? rg.map(function(r){
      return '<div><span class="mu">' + esc(r.hora) + '</span> › ' + esc(r.app.toUpperCase()) + ' · ' + esc(r.nome) + '</div>';
    }).join('') : '<div class="mu">Ainda sem atividade hoje.</div>';

    /* conversa */
    var u = e.ultima || {};
    $('uLine').textContent = u.usuario ? 'VOCÊ › ' + u.usuario : (e.pronto ? 'Diga "' + e.palavra + '" ou aperte ' + e.atalho + ' para falar.' : ' ');
    $('aLine').textContent = u.assistente ? '“' + u.assistente + '”' : (e.estado === 'pensando' ? '…' : ' ');
    $('bMic').classList.toggle('ativo', e.estado === 'gravando');

    /* alerta */
    var a = e.alerta;
    $('alerta').hidden = !a;
    if (a){ $('alHora').textContent = a.hora; $('alTxt').textContent = a.texto; }

    $('rodD').textContent = 'ATIVAÇÃO "' + e.palavra + '"' + (e.ativacao ? '' : ' (DESLIGADA)') + ' · ' + e.atalho;
    if (e.erros && e.erros.length) $('rodE').textContent = '■ AVISO: ' + e.erros[e.erros.length - 1];
    if ($('cAviso') && e.aviso_gravacao) $('cAviso').textContent = e.aviso_gravacao;
  }

  function atualizar(){
    chamar('estado').then(render).catch(function(){}).then(function(){ setTimeout(atualizar, 700); });
  }
  atualizar();

  /* ---------------------------------------------------------------- ações */
  $('cmdf').addEventListener('submit', function(ev){
    ev.preventDefault();
    var t = $('cmd').value.trim();
    if (!t) return;
    $('cmd').value = '';
    $('uLine').textContent = 'VOCÊ › ' + t;
    $('aLine').textContent = '…';
    chamar('enviar', t);
  });
  $('bMic').addEventListener('click', function(){ chamar('ouvir'); });
  $('alOk').addEventListener('click', function(){ if (ultimo && ultimo.alerta) chamar('lembrete', ultimo.alerta.id, 'concluir'); $('alerta').hidden = true; });
  $('alAdiar').addEventListener('click', function(){ if (ultimo && ultimo.alerta) chamar('lembrete', ultimo.alerta.id, 'adiar'); $('alerta').hidden = true; });
  function pend(acao){ if (ultimo && ultimo.pendencias && ultimo.pendencias[0]) chamar('pendencia', ultimo.pendencias[0].id, acao); }
  $('pAbrir').addEventListener('click', function(){ pend('abrir'); });
  $('pAdiar').addEventListener('click', function(){ pend('adiar'); });
  $('pOk').addEventListener('click', function(){ pend('resolver'); });

  document.querySelectorAll('[data-fechar]').forEach(function(b){
    b.addEventListener('click', function(){ $(b.getAttribute('data-fechar')).hidden = true; });
  });
  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape'){ $('ovHist').hidden = true; $('ovCfg').hidden = true; }
  });

  /* histórico */
  $('bHist').addEventListener('click', function(){
    $('ovHist').hidden = false;
    chamar('historico').then(function(lista){
      $('histLista').innerHTML = (lista || []).map(function(m){
        return '<div class="m ' + (m.papel === 'usuario' ? 'u' : 'a') + '"><div class="q">' +
               (m.papel === 'usuario' ? 'VOCÊ' : 'MANTIQUEIRA') + ' · ' + esc(m.quando.slice(8,10) + '/' + m.quando.slice(5,7) + ' ' + m.quando.slice(11,16)) +
               '</div>' + esc(m.texto) + '</div>';
      }).join('') || '<div class="vazio">Nenhuma conversa ainda.</div>';
      var h = $('histLista'); h.parentNode.scrollTop = h.parentNode.scrollHeight;
    });
  });

  /* configurações */
  var temaEscolhido = 'Azul';
  function pintarTemas(){
    $('cTemas').innerHTML = Object.keys(TEMAS).map(function(n){
      return '<button type="button" class="tm" data-t="' + n + '" aria-pressed="' + (n === temaEscolhido) + '"><i style="background:' + TEMAS[n].p + '"></i>' + n + '</button>';
    }).join('');
    $('cTemas').querySelectorAll('.tm').forEach(function(b){
      b.addEventListener('click', function(){ temaEscolhido = b.getAttribute('data-t'); temaAtual = null; aplicarTema(temaEscolhido); pintarTemas(); });
    });
  }
  $('bCfg').addEventListener('click', function(){
    $('ovCfg').hidden = false; $('cOk').textContent = '';
    chamar('config').then(function(c){
      var g = c.cfg;
      $('cNome').value = g.nome || ''; $('cTrat').value = g.tratamento || '';
      $('cVoz').innerHTML = (c.vozes || []).map(function(v){ return '<option value="' + esc(v.id) + '">' + esc(v.nome) + '</option>'; }).join('') || '<option value="">(nenhuma voz encontrada)</option>';
      $('cVoz').value = c.voz_atual || '';
      $('cMic').innerHTML = '<option value="padrao">Padrão do Windows</option>' + (c.microfones || []).map(function(m){ return '<option value="' + m.id + '">' + esc(m.nome) + '</option>'; }).join('');
      $('cMic').value = g.microfone == null ? 'padrao' : String(g.microfone);
      $('cModo').value = g.modo_ia || 'normal';
      $('cModo').disabled = !c.turbo;
      $('cAtiv').checked = !!g.ativacao_por_voz; $('cFalar').checked = !!g.responder_falando;
      $('cOlhos').checked = !!g.olhos_ativos; $('cIni').checked = !!g.iniciar_com_windows;
      $('cAtalho').value = g.atalho || 'ctrl+space';
      $('cIgn').value = (g.ignorar || []).join('\n');
      temaEscolhido = g.tema || 'Azul'; pintarTemas();
    });
  });
  $('cTestar').addEventListener('click', function(){ chamar('testar_voz', $('cVoz').value); });
  $('cGravar').addEventListener('click', function(){ $('cAviso').textContent = 'Preparando…'; chamar('gravar_voz'); });
  $('cArqVoz').addEventListener('click', function(){ chamar('usar_arquivo_voz'); });
  $('cDados').addEventListener('click', function(){ chamar('abrir_dados'); });
  $('cSalvar').addEventListener('click', function(){
    chamar('salvar_config', {
      nome: $('cNome').value.trim() || 'Rodolfo', tratamento: $('cTrat').value.trim() || 'senhor',
      voz: $('cVoz').value, microfone: $('cMic').value, modo_ia: $('cModo').value,
      ativacao_por_voz: $('cAtiv').checked, responder_falando: $('cFalar').checked,
      olhos_ativos: $('cOlhos').checked, iniciar_com_windows: $('cIni').checked,
      atalho: $('cAtalho').value.trim() || 'ctrl+space', ignorar: $('cIgn').value, tema: temaEscolhido
    }).then(function(){ $('cOk').textContent = 'SALVO'; });
  });
})();
