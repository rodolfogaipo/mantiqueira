/* Mantiqueira — tela principal */
(function(){
  var palco = $('palco');
  /* O palco tem 900 de altura e largura variável: em telas mais largas que 16:10 ele estica para os lados. */
  function escalar(){
    var iw = window.innerWidth, ih = window.innerHeight, s, W, y = 0;
    if (iw / ih >= 1440 / 900){ s = ih / 900; W = Math.max(1440, Math.ceil(iw / s)); }
    else { s = iw / 1440; W = 1440; y = (ih - 900*s) / 2; }
    var dx = W - 1440, m = dx / 2;
    palco.style.width = W + 'px';
    palco.style.setProperty('--dx', dx + 'px');
    palco.style.transform = 'translate(0px,' + y + 'px) scale(' + s + ')';
    var f = $('fundo');
    f.setAttribute('width', W); f.setAttribute('viewBox', '0 0 ' + W + ' 900');
    $('hexRet').setAttribute('width', W); $('mascRet').setAttribute('width', W);
    $('ln1').setAttribute('d', 'M370 196 H' + (430+m) + ' L' + (470+m) + ' 236 H' + (528+m));
    $('ln2').setAttribute('d', 'M370 540 H' + (440+m) + ' L' + (478+m) + ' 502 H' + (540+m));
    $('ln3').setAttribute('d', 'M' + (1060+dx) + ' 210 H' + (1010+dx) + ' L' + (970+dx) + ' 250 H' + (912+m));
    $('linhaPend').setAttribute('d', 'M' + (1060+dx) + ' 520 H' + (1010+dx) + ' L' + (975+dx) + ' 545 H' + (898+m));
    [['pt1',528+m,236],['pt2',540+m,502],['pt3',912+m,250],['pt4',898+m,545]].forEach(function(p){ $(p[0]).setAttribute('cx', p[1]); $(p[0]).setAttribute('cy', p[2]); });
    $('cantoD').setAttribute('d', 'M' + (W-60) + ' 20 H' + (W-20) + ' V60 M' + (W-60) + ' 880 H' + (W-20) + ' V840');
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
    $('relHM').textContent = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
    $('sec').textContent = ':' + String(d.getSeconds()).padStart(2,'0');
    $('data').textContent = DIAS[d.getDay()] + ' ' + String(d.getDate()).padStart(2,'0') + '.' + String(d.getMonth()+1).padStart(2,'0') + '.' + d.getFullYear();
  }
  relogio(); setInterval(relogio, 1000);

  /* holograma 3D (three.js) */
  var holo = null;
  try { holo = Holograma.criar($('holoCanvas'), $('rot')); } catch (err) { console.log('holograma indisponível', err); }
  var NOME_HOLO = {real:'SUA PEÇA · 3D', peca:'PEÇA', chapa:'CHAPA METÁLICA', montagem:'MONTAGEM', desenho:'DESENHO 2D',
                   cad2d:'DESENHO CAD', movel:'MODELO 3D', cnc:'ROUTER CNC', laser:'CORTE A LASER', planilha:'PLANILHA',
                   documento:'DOCUMENTO', globo:'INTERNET', pasta:'ARQUIVOS', mensagem:'MENSAGENS', familia:'EM CASA',
                   logo:'MANTIQUEIRA', foto:'EM CASA'};
  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var estadoAtual = 'carregando', t0 = null, nivel = 0;
  function quadro(t){
    if (t0 === null) t0 = t;
    var alvo = estadoAtual === 'gravando' ? 1 : (estadoAtual === 'falando' ? .8 : (estadoAtual === 'pensando' || estadoAtual === 'transcrevendo' ? .35 : .08));
    nivel += (alvo - nivel) * .15;
    for (var j = 0; j < barras.length; j++){
      var v = nivel * (.35 + .65 * Math.abs(Math.sin(t/180 + j*.7) * Math.cos(t/330 + j*.23)));
      barras[j].style.transform = 'scaleY(' + Math.max(.12, v).toFixed(2) + ')';
    }
    requestAnimationFrame(quadro);
  }
  if (!reduz) requestAnimationFrame(quadro);

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
    if ($('ovCfg').hidden) aplicarTema(e.tema);
    estadoAtual = e.estado;
    palco.classList.toggle('rapido', e.estado === 'pensando' || e.estado === 'transcrevendo');
    $('stCpu').textContent = e.cpu + '%';
    $('stRam').textContent = e.ram;
    $('stGpu').textContent = e.gpu;
    $('stModo').textContent = e.modo_ia + (e.dispositivo && e.dispositivo !== '—' ? ' · ' + e.dispositivo : '');
    $('coreTxt').textContent = e.pronto ? rotuloEstado(e) : 'CARREGANDO';
    $('coreSub').textContent = e.latencia ? ('ÚLTIMA RESPOSTA ' + String(e.latencia).replace('.', ',') + 's') : ' ';
    var bp = e.boot_passos || [];
    $('boot').hidden = e.pronto || (!e.boot && !bp.length);
    if (bp.length){
      $('boot').innerHTML = bp.map(function(x){
        var st = x.ok === true ? '<span class="ok">✓ OK</span>' : (x.ok === false ? '<span class="al">✕ FALHOU</span>' : '<span class="pisca">…</span>');
        return '<div><span class="mu">▸</span> ' + esc(x.msg) + ' ' + st + '</div>';
      }).join('');
    } else {
      $('boot').textContent = e.boot || '';
    }

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
               barra + '<div class="s">' + esc(sub) + '</div><div class="agb">' +
               '<button type="button" class="mini-b" data-lid="' + l.id + '" data-acao="concluir">FEITO</button>' +
               '<button type="button" class="mini-b" data-lid="' + l.id + '" data-acao="cancelar">APAGAR</button></div></div></div>';
      }).join('');
    }

    /* subsistemas */
    $('sys').innerHTML = (e.sub || []).map(function(s){
      return '<div class="sys"><span>' + esc(s.nome) + '</span><div class="segs">' + segs(s.pct, s.alerta) +
             '</div><span style="color:var(--hi);text-align:right">' + esc(s.val) + '</span></div>';
    }).join('');

    /* foco */
    if (holo && e.holo){
      holo.setCor((TEMAS[e.tema] || TEMAS.Azul).p);
      holo.mostrar(e.holo.chave, e.holo.tipo, e.holo.url);
      $('holoTipo').textContent = NOME_HOLO[e.holo.tipo] || '';
    }
    var f = e.foco;
    if (f){
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
    $('pt4').style.display = pd.length ? '' : 'none';
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
    var av = e.avisos || [], avs = av.join('|');
    if ($('avisos').getAttribute('data-v') !== avs){
      $('avisos').setAttribute('data-v', avs);
      $('avisos').innerHTML = av.map(function(x){ return '<div title="' + esc(x) + '">■ ' + esc(x) + '</div>'; }).join('');
      $('avisos').hidden = !av.length;
    }
    var det = u.detalhe || '';
    if ($('dLine').getAttribute('data-v') !== det){ $('dLine').setAttribute('data-v', det); $('dLine').textContent = det; $('dLine').hidden = !det; }
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
    $('cmd').focus();
    $('uLine').textContent = 'VOCÊ › ' + t;
    $('aLine').textContent = '…';
    chamar('enviar', t);
  });
  $('bMic').addEventListener('click', function(){ chamar('ouvir'); });
  document.querySelector('svg.hsvg').addEventListener('click', function(){ chamar('parar_fala'); });
  /* caixa de texto: clicar em qualquer parte dela foca; começar a digitar em qualquer lugar também */
  $('cmdf').addEventListener('mousedown', function(ev){
    if (!ev.target.closest('button') && ev.target !== $('cmd')){ ev.preventDefault(); $('cmd').focus(); }
  });
  function algumPainelAberto(){ return !$('ovCfg').hidden || !$('ovHist').hidden || !$('ovCon').hidden; }
  document.addEventListener('keydown', function(ev){
    var alvo = document.activeElement, tag = alvo && alvo.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || algumPainelAberto()) return;
    if (ev.ctrlKey || ev.altKey || ev.metaKey) return;
    if (ev.key.length === 1 || ev.key === 'Backspace') $('cmd').focus();
  });
  window.addEventListener('focus', function(){ if (!algumPainelAberto()) $('cmd').focus(); });
  setTimeout(function(){ $('cmd').focus(); }, 300);
  $('agenda').addEventListener('click', function(ev){
    var b = ev.target.closest('[data-lid]');
    if (!b) return;
    b.closest('.ag').style.opacity = '.3';
    chamar('lembrete', Number(b.getAttribute('data-lid')), b.getAttribute('data-acao'));
  });
  $('alOk').addEventListener('click', function(){ if (ultimo && ultimo.alerta) chamar('lembrete', ultimo.alerta.id, 'concluir'); $('alerta').hidden = true; });
  $('alAdiar').addEventListener('click', function(){ if (ultimo && ultimo.alerta) chamar('lembrete', ultimo.alerta.id, 'adiar'); $('alerta').hidden = true; });
  function pend(acao){
    if (!(ultimo && ultimo.pendencias && ultimo.pendencias[0])) return;
    $('pendMsg').textContent = acao === 'abrir' ? 'PROCURANDO A JANELA…' : '';
    chamar('pendencia', ultimo.pendencias[0].id, acao).then(function(ok){
      if (acao === 'abrir') $('pendMsg').textContent = ok ? 'PRONTO — JANELA NA FRENTE' : 'NÃO ACHEI ESSE ARQUIVO ABERTO NEM NO MAPA';
      else { $('pendMsg').textContent = acao === 'adiar' ? 'TE LEMBRO DAQUI A 1 HORA' : 'MARCADA COMO RESOLVIDA'; }
      setTimeout(function(){ $('pendMsg').textContent = ''; }, 4000);
    });
  }
  $('pAbrir').addEventListener('click', function(){ pend('abrir'); });
  $('pAdiar').addEventListener('click', function(){ pend('adiar'); });
  $('pOk').addEventListener('click', function(){ pend('resolver'); });

  document.querySelectorAll('[data-fechar]').forEach(function(b){
    b.addEventListener('click', function(){ $(b.getAttribute('data-fechar')).hidden = true; });
  });
  document.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape'){
      if (!algumPainelAberto()) { chamar('parar_fala'); return; }
      $('ovHist').hidden = true; $('ovCfg').hidden = true; $('ovCon').hidden = true;
    }
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

  /* base de conhecimento */
  var conTimer = null;
  function pintarCon(){
    chamar('conhecimento').then(function(c){
      var docs = (c.docs || []), meus = docs.filter(function(d){ return d.origem === 'usuario'; }),
          guias = docs.filter(function(d){ return d.origem === 'guia'; });
      $('conStatus').textContent = c.status || '';
      chamar('indice_resumo').then(function(l){
        $('idxLista').innerHTML = (l && l.length) ? l.map(function(x){ return '<div>' + esc(x) + '</div>'; }).join('')
          : '<div class="mu">O mapa começa a ser feito uns 40 segundos depois de abrir o Mantiqueira.</div>';
      });
      $('conN').textContent = meus.length ? String(meus.length).padStart(2, '0') : '';
      $('conDocs').innerHTML = meus.length ? meus.map(function(d){
        var info = (d.paginas ? d.paginas + ' PÁG · ' : '') + d.trechos + ' TRECHOS';
        return '<div class="doc"><span class="dn" title="' + esc(d.nome) + '">' + esc(d.nome) + '</span><span class="di">' + info +
               '</span><button type="button" class="mini-b" data-doc="' + d.id + '">REMOVER</button></div>';
      }).join('') : '<div class="vazio">Nenhum documento ainda. Clique em <b>ADICIONAR ARQUIVOS</b>.</div>';
      $('conGuias').innerHTML = guias.map(function(d){
        return '<div class="doc"><span class="dn">' + esc(d.nome) + '</span><span class="di">' + d.trechos + ' TRECHOS</span><span class="di">EMBUTIDO</span></div>';
      }).join('');
    });
  }
  $('bCon').addEventListener('click', function(){
    $('ovCon').hidden = false; pintarCon();
    clearInterval(conTimer);
    conTimer = setInterval(function(){ if ($('ovCon').hidden) clearInterval(conTimer); else pintarCon(); }, 1500);
  });
  $('idxAtualizar').addEventListener('click', function(){ chamar('indice_atualizar'); $('idxLista').innerHTML = '<div class="mu">Atualizando o mapa em segundo plano…</div>'; });
  $('conAdd').addEventListener('click', function(){ chamar('conhecimento_adicionar').then(pintarCon); });
  $('conDocs').addEventListener('click', function(ev){
    var b = ev.target.closest('[data-doc]');
    if (!b) return;
    if (b.getAttribute('data-ok') !== '1'){ b.setAttribute('data-ok', '1'); b.textContent = 'CONFIRMAR?'; return; }
    chamar('conhecimento_remover', Number(b.getAttribute('data-doc'))).then(pintarCon);
  });

  /* configurações */
  var temaEscolhido = 'Azul';
  function pintarTemas(){
    $('cTemas').innerHTML = Object.keys(TEMAS).map(function(n){
      return '<button type="button" class="tm" data-t="' + n + '" aria-pressed="' + (n === temaEscolhido) + '"><i style="background:' + TEMAS[n].p + '"></i>' + n + '</button>';
    }).join('');
    $('cTemas').querySelectorAll('.tm').forEach(function(b){
      b.addEventListener('click', function(){ temaEscolhido = b.getAttribute('data-t'); temaAtual = null; aplicarTema(temaEscolhido); pintarTemas(); chamar('salvar_config', {tema: temaEscolhido}); });
    });
  }
  $('bCfg').addEventListener('click', function(){
    $('ovCfg').hidden = false; $('cOk').textContent = '';
    chamar('config').then(function(c){
      var g = c.cfg;
      $('cNome').value = g.nome || ''; $('cTrat').value = g.tratamento || '';
      $('cVoz').innerHTML = (c.vozes || []).map(function(v){ return '<option value="' + esc(v.id) + '">' + esc(v.nome) + '</option>'; }).join('') || '<option value="">(nenhuma voz encontrada)</option>';
      $('cVoz').value = c.voz_atual || '';
      $('cVoz').setAttribute('data-mudou', '');
      $('cMic').innerHTML = '<option value="padrao">Padrão do Windows</option>' + (c.microfones || []).map(function(m){ return '<option value="' + m.id + '">' + esc(m.nome) + '</option>'; }).join('');
      $('cMic').value = g.microfone == null ? 'padrao' : String(g.microfone);
      $('cModo').value = g.modo_ia || 'normal';
      $('cModo').disabled = !c.turbo;
      $('cAtiv').checked = !!g.ativacao_por_voz; $('cFalar').checked = !!g.responder_falando;
      $('cHolo').checked = g.holo_real !== false; $('cX').checked = g.x_esconde !== false;
      $('cOlhos').checked = !!g.olhos_ativos; $('cIni').checked = !!g.iniciar_com_windows;
      $('cAtalho').value = g.atalho || 'ctrl+shift+space';
      $('cAtalhoB').value = g.atalho_barra || 'ctrl+space';
      $('cFotoOk').textContent = c.foto ? 'FOTO ESCOLHIDA' : 'NENHUMA FOTO AINDA';
      $('cSomL').checked = g.som_lembrete !== false; $('cSomB').checked = g.som_bip !== false; $('cCnp').checked = g.avisar_cnp !== false;
      $('cVol').value = g.voz_volume || 1; $('cVel').value = g.voz_velocidade || 1;
      $('cSil').value = (g.silencio_horarios || []).join('\n');
      $('cSisRes').textContent = '';
      pintarApel();
      pintarSis(g.sistemas_web || []);
      $('cIgn').value = (g.ignorar || []).join('\n');
      temaEscolhido = g.tema || 'Azul'; pintarTemas();
    });
  });
  function pintarSis(lista){
    $('cSis').innerHTML = lista.map(function(s, i){
      return '<div class="sis" data-i="' + i + '"><input class="n" type="text" aria-label="Nome do sistema" value="' + esc(s.nome) + '">' +
             '<input class="u" type="text" aria-label="Endereço do sistema" value="' + esc(s.url) + '">' +
             '<input class="p" type="hidden" value="' + esc(s.palavras || '') + '">' +
             '<button type="button" class="chip" data-entrar="' + esc(s.nome) + '">ENTRAR</button>' +
             '<button type="button" class="chip" data-testar="' + esc(s.nome) + '">TESTAR</button>' +
             '<button type="button" class="chip" data-tirar="' + i + '" aria-label="Remover">✕</button></div>';
    }).join('') || '<small class="mu">Nenhum sistema cadastrado.</small>';
  }
  function lerSis(){
    return Array.prototype.map.call(document.querySelectorAll('#cSis .sis'), function(d){
      return {nome: d.querySelector('.n').value.trim(), url: d.querySelector('.u').value.trim(), palavras: d.querySelector('.p').value};
    }).filter(function(s){ return s.nome && s.url; });
  }
  $('cSis').addEventListener('click', function(ev){
    var b = ev.target.closest('button');
    if (!b) return;
    if (b.hasAttribute('data-entrar')){
      chamar('sistemas_salvar', lerSis()).then(function(){ chamar('sistema_entrar', b.getAttribute('data-entrar')); });
    } else if (b.hasAttribute('data-testar')){
      $('cSisRes').textContent = 'TESTANDO ' + b.getAttribute('data-testar') + '… (pode levar até 1 minuto)';
      chamar('sistemas_salvar', lerSis()).then(function(){ return chamar('sistema_testar', b.getAttribute('data-testar')); })
        .then(function(r){ $('cSisRes').textContent = r; });
    } else if (b.hasAttribute('data-tirar')){
      var l = lerSis(); l.splice(Number(b.getAttribute('data-tirar')), 1); pintarSis(l);
    }
  });
  function pintarApel(){
    chamar('apelidos_lista').then(function(l){
      $('cApel').innerHTML = (l || []).map(function(a){
        return '<div class="apel"><span title="' + esc(a.caminho) + '"><b>' + esc(a.apelido) + '</b> → ' + esc(a.caminho) + '</span>' +
               '<button type="button" class="chip" data-apagar="' + esc(a.apelido) + '" aria-label="Apagar apelido">✕</button></div>';
      }).join('') || '<small class="mu">Nenhum apelido ainda.</small>';
    });
  }
  $('cApel').addEventListener('click', function(ev){
    var b = ev.target.closest('[data-apagar]');
    if (b) chamar('apelido_apagar', b.getAttribute('data-apagar')).then(pintarApel);
  });
  $('cSisAdd').addEventListener('click', function(){ var l = lerSis(); l.push({nome: 'Novo', url: 'http://', palavras: ''}); pintarSis(l); });
  $('cFoto').addEventListener('click', function(){
    $('cFotoOk').textContent = 'ESCOLHENDO…';
    chamar('escolher_foto').then(function(ok){ $('cFotoOk').textContent = ok ? 'FOTO ESCOLHIDA — APARECE QUANDO O PC FICA PARADO' : 'NENHUMA FOTO ESCOLHIDA'; });
  });
  $('cTestar').addEventListener('click', function(){ chamar('testar_voz', $('cVoz').value); });
  $('cVoz').addEventListener('change', function(){ $('cVoz').setAttribute('data-mudou', '1'); });
  $('cGravar').addEventListener('click', function(){ $('cAviso').textContent = 'Preparando…'; chamar('gravar_voz'); });
  $('cArqVoz').addEventListener('click', function(){ chamar('usar_arquivo_voz'); });
  $('cDados').addEventListener('click', function(){ chamar('abrir_dados'); });
  $('cTesteAviso').addEventListener('click', function(){ chamar('testar_aviso').then(function(){ $('cOk').textContent = 'AVISO EM 20 SEGUNDOS — PODE MINIMIZAR'; }); });
  $('cSair').addEventListener('click', function(){
    var b = $('cSair');
    if (b.getAttribute('data-ok') !== '1'){ b.setAttribute('data-ok', '1'); b.textContent = 'CLIQUE DE NOVO PARA ENCERRAR'; return; }
    chamar('encerrar');
  });
  $('cSalvar').addEventListener('click', function(){
    chamar('salvar_config', {
      nome: $('cNome').value.trim() || 'Rodolfo', tratamento: $('cTrat').value.trim() || 'senhor',
      voz: $('cVoz').getAttribute('data-mudou') ? $('cVoz').value : undefined, microfone: $('cMic').value, modo_ia: $('cModo').value,
      ativacao_por_voz: $('cAtiv').checked, responder_falando: $('cFalar').checked,
      olhos_ativos: $('cOlhos').checked, iniciar_com_windows: $('cIni').checked,
      holo_real: $('cHolo').checked, x_esconde: $('cX').checked,
      atalho: $('cAtalho').value.trim() || 'ctrl+shift+space', atalho_barra: $('cAtalhoB').value.trim() || 'ctrl+space',
      sistemas_web: lerSis(), som_lembrete: $('cSomL').checked, som_bip: $('cSomB').checked, avisar_cnp: $('cCnp').checked,
      voz_volume: Number($('cVol').value), voz_velocidade: Number($('cVel').value), silencio_horarios: $('cSil').value, ignorar: $('cIgn').value, tema: temaEscolhido
    }).then(function(){ $('cOk').textContent = 'SALVO'; });
  });
})();
