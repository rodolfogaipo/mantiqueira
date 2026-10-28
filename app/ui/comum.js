/* Mantiqueira — funções compartilhadas pelas telas */
var TEMAS = {
  Azul:{p:'#5aa0ff',p2:'#2f6dff',p3:'#0f2a5c',pd:'#0c1f44',hi:'#eef4ff',tx:'#c6dbff',mu:'#7f9fd6',al:'#ffb020',bg1:'#0a1e4f',bg2:'#030a1c',gl:'90,160,255',agl:'255,176,32'},
  Ciano:{p:'#5fe6ff',p2:'#2fb8e0',p3:'#0d3a52',pd:'#0e3346',hi:'#effdff',tx:'#bff4ff',mu:'#5fb9d4',al:'#ff9d2e',bg1:'#062033',bg2:'#020b14',gl:'80,230,255',agl:'255,157,46'},
  Ouro:{p:'#ffc04d',p2:'#c98a26',p3:'#4a3310',pd:'#2a1c08',hi:'#fff4dc',tx:'#f3dcb4',mu:'#b9925c',al:'#ff5a46',bg1:'#211505',bg2:'#0a0603',gl:'255,192,77',agl:'255,90,70'},
  Esmeralda:{p:'#3dffa8',p2:'#1fae74',p3:'#11402d',pd:'#082a1d',hi:'#e2fff2',tx:'#bfeedb',mu:'#6fb596',al:'#ffbf47',bg1:'#032419',bg2:'#010a07',gl:'61,255,168',agl:'255,191,71'},
  Vermelho:{p:'#ff5546',p2:'#c42c22',p3:'#4a1411',pd:'#2a0907',hi:'#ffe4de',tx:'#f2c6bd',mu:'#c07c72',al:'#ffc04d',bg1:'#240605',bg2:'#0a0202',gl:'255,85,70',agl:'255,192,77'},
  Gelo:{p:'#e9f0f7',p2:'#93a6ba',p3:'#2b3542',pd:'#161c24',hi:'#ffffff',tx:'#dfe7ef',mu:'#93a3b5',al:'#ff8a3d',bg1:'#141b24',bg2:'#05070a',gl:'220,232,245',agl:'255,138,61'},
  Violeta:{p:'#b993ff',p2:'#7d5bd0',p3:'#2e2152',pd:'#1a1230',hi:'#f2ebff',tx:'#d9ccf5',mu:'#9a88c4',al:'#ff7ab8',bg1:'#170f2e',bg2:'#06040d',gl:'185,147,255',agl:'255,122,184'}
};
var temaAtual = null;
function aplicarTema(nome){
  var c = TEMAS[nome] || TEMAS.Azul;
  if (temaAtual === nome) return;
  temaAtual = nome;
  var r = document.documentElement;
  for (var k in c) r.style.setProperty('--' + k, c[k]);
}
aplicarTema('Azul');

function esc(t){
  return String(t == null ? '' : t).replace(/[&<>"']/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}
function $(id){ return document.getElementById(id); }

/* Ponte com o Python. Fora do programa (pré-visualização no navegador) usa dados de exemplo. */
var API = null;
var pronto = new Promise(function(res){
  function ok(){ API = window.pywebview.api; res(true); }
  if (window.pywebview && window.pywebview.api) ok();
  else window.addEventListener('pywebviewready', ok);
  setTimeout(function(){ if (!API) { API = EXEMPLO; res(false); } }, 2500);
});
function chamar(nome){
  var args = Array.prototype.slice.call(arguments, 1);
  return pronto.then(function(){ return API[nome].apply(API, args); });
}

/* Dados de exemplo, só para ver a tela fora do programa */
var EXEMPLO = {
  estado: function(){
    var agora = new Date();
    function em(min){ return new Date(agora.getTime() + min*60000).toISOString(); }
    return Promise.resolve({
      pronto:true, boot:'', estado:'ocioso', tema:'Azul', nome:'Rodolfo', cpu:23, ram:'9.1/16G', gpu:'4.2/6G',
      modo_ia:'NORMAL', dispositivo:'GPU', latencia:1.1, ativacao:true, palavra:'MANTIQUEIRA', atalho:'CTRL+ESPAÇO',
      sub:[{nome:'OUVIDO',pct:1,val:'ATIVO'},{nome:'NÚCLEO IA',pct:1,val:'NORMAL'},{nome:'VOZ',pct:1,val:'NATURAL'},
           {nome:'VISÃO',pct:1,val:'REC',alerta:true},{nome:'RAM',pct:.57,val:'9.1G'},{nome:'VRAM',pct:.7,val:'4.2G'}],
      agenda:[{id:1,quando:em(31),hora:'09:30',dia:'HOJE',texto:'Ligar para o fornecedor de alumínio (exemplo)'},
              {id:2,quando:em(121),hora:'11:00',dia:'HOJE',texto:'Enviar DXF da pérgola (exemplo)'},
              {id:3,quando:em(301),hora:'14:00',dia:'HOJE',texto:'Reunião equipe P&D (exemplo)',repetir:'semanal'}],
      foco:{app:'SolidWorks',arquivo:'Pergola_Lamelas_v3.SLDASM',nao_salvo:true,tempo:'47 minutos',cad:true},
      pendencias:[{id:1,texto:'Orcamento_Cliente.xlsx foi aberto 3 vezes desde ontem e continua sem salvar. (exemplo)',arquivo:'Orcamento_Cliente.xlsx'}],
      registro:[{hora:'08:12',app:'SolidWorks',nome:'Pergola_Lamelas_v3.SLDASM'},{hora:'07:58',app:'Excel',nome:'Orcamento_Cliente.xlsx'},{hora:'07:41',app:'Explorador',nome:'Projetos'}],
      ultima:{usuario:'Em qual arquivo eu estava ontem no fim da tarde?',assistente:'Das 16 e 20 às 17 e 40, na montagem Pergola_Lamelas_v3. Deseja que eu a abra?'},
      alerta:null, aviso_gravacao:'', erros:[]
    });
  },
  enviar: function(){ return Promise.resolve(true); }, ouvir: function(){ return Promise.resolve(true); },
  historico: function(){ return Promise.resolve([{quando:'2026-10-28 08:58:00',papel:'usuario',texto:'Exemplo de pergunta'},{quando:'2026-10-28 08:58:02',papel:'assistente',texto:'Exemplo de resposta.'}]); },
  config: function(){ return Promise.resolve({cfg:{nome:'Rodolfo',tratamento:'senhor',tema:'Azul',voz:'',microfone:null,ativacao_por_voz:true,responder_falando:true,olhos_ativos:true,modo_ia:'normal',iniciar_com_windows:false,atalho:'ctrl+space',ignorar:['banco','senha']},vozes:[{id:'xtts:Damien Black',nome:'Natural 1 — Damien Black'},{id:'piper:faber',nome:'Rápida — Faber'}],voz_atual:'xtts:Damien Black',microfones:[{id:1,nome:'Microfone USB (exemplo)'}],turbo:true}); },
  salvar_config: function(){ return Promise.resolve(true); }, testar_voz: function(){ return Promise.resolve(true); },
  gravar_voz: function(){ return Promise.resolve(true); }, usar_arquivo_voz: function(){ return Promise.resolve(false); },
  lembrete: function(){ return Promise.resolve(true); }, pendencia: function(){ return Promise.resolve(true); },
  fechar_alerta: function(){ return Promise.resolve(true); }, esconder_mini: function(){ return Promise.resolve(true); },
  mostrar_principal: function(){ return Promise.resolve(true); }, abrir_dados: function(){ return Promise.resolve(true); },
  conhecimento: function(){ return Promise.resolve({status:'Aprendido: Catalogo_Chapas_2026.pdf.', docs:[
    {id:9,nome:'Catalogo_Chapas_2026.pdf (exemplo)',origem:'usuario',paginas:48,trechos:131},
    {id:8,nome:'Tabela_dobra_aco_carbono.pdf (exemplo)',origem:'usuario',paginas:3,trechos:7},
    {id:1,nome:'SolidWorks 2025',origem:'guia',trechos:13},{id:2,nome:'AutoCAD 2025',origem:'guia',trechos:11},
    {id:3,nome:'SketchUp 2023',origem:'guia',trechos:7},{id:4,nome:'3ds Max 2025',origem:'guia',trechos:7},
    {id:5,nome:'Aspire 12',origem:'guia',trechos:6},{id:6,nome:'CypCut laser',origem:'guia',trechos:5},
    {id:7,nome:'Office Excel Word PowerPoint',origem:'guia',trechos:6}]}); },
  conhecimento_adicionar: function(){ return Promise.resolve(false); }, conhecimento_remover: function(){ return Promise.resolve(true); }
};

var ROTULO_ESTADO = {carregando:'CARREGANDO', ocioso:'ESCUTANDO', gravando:'OUVINDO VOCÊ', transcrevendo:'ENTENDENDO',
                     pensando:'PENSANDO', falando:'FALANDO'};
function rotuloEstado(e){
  if (e.estado === 'ocioso' && !e.ativacao) return 'PRONTA';
  return ROTULO_ESTADO[e.estado] || 'PRONTA';
}

/* marcações em volta de um círculo */
function marcacoes(cx, cy, r, passo, cada, curta, longa){
  var d = '';
  for (var a = 0; a < 360; a += passo){
    var t = (a - 90) * Math.PI / 180, L = a % cada === 0 ? longa : curta;
    d += 'M' + (cx + r*Math.cos(t)).toFixed(1) + ' ' + (cy + r*Math.sin(t)).toFixed(1) +
         'L' + (cx + (r-L)*Math.cos(t)).toFixed(1) + ' ' + (cy + (r-L)*Math.sin(t)).toFixed(1);
  }
  return d;
}
function arco(cx, cy, r, a0, a1){
  function p(a){ var t = (a - 90) * Math.PI / 180; return (cx + r*Math.cos(t)).toFixed(1) + ' ' + (cy + r*Math.sin(t)).toFixed(1); }
  return 'M' + p(a0) + ' A' + r + ' ' + r + ' 0 ' + ((a1 - a0) > 180 ? 1 : 0) + ' 1 ' + p(a1);
}
