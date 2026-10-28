/* Mantiqueira — hologramas 3D (three.js, offline).
   Mostra a peça real do SolidWorks (quando disponível) ou uma ilustração do que está em uso. */
var Holograma = (function(){
  var T = window.THREE;

  function Holo(canvas, rotulo){
    this.canvas = canvas;
    this.rotulo = rotulo;
    this.cor = new T.Color('#5aa0ff');
    this.renderer = new T.WebGLRenderer({canvas: canvas, alpha: true, antialias: true});
    this.renderer.setPixelRatio(2);
    this.renderer.setSize(canvas.clientWidth || 340, canvas.clientHeight || 200, false);
    this.cena = new T.Scene();
    this.camera = new T.PerspectiveCamera(32, (canvas.clientWidth || 340) / (canvas.clientHeight || 200), 0.1, 100);
    this.camera.position.set(0, 0.95, 3.95);
    this.camera.lookAt(0, -0.12, 0);
    this.raiz = new T.Group();
    this.cena.add(this.raiz);
    this.mats = [];
    this.chave = null;
    this.anim = null;
    this.t0 = performance.now();
    this.ang = 0.6;
    var self = this;
    function quadro(t){
      var dt = Math.min(0.05, (t - (self.tAnt || t)) / 1000); self.tAnt = t;
      self.ang += dt * 0.55;
      self.raiz.rotation.y = self.ang;
      if (self.anim) self.anim((t - self.t0) / 1000, dt);
      self.renderer.render(self.cena, self.camera);
      if (self.rotulo) self.rotulo.textContent = 'ROT ' + String(Math.round((self.ang * 180 / Math.PI) % 360)).padStart(3, '0') + '°';
      requestAnimationFrame(quadro);
    }
    requestAnimationFrame(quadro);
  }

  /* ---------------------------------------------------------- materiais e montagem */
  Holo.prototype.matLinha = function(op){
    var m = new T.LineBasicMaterial({color: this.cor.clone(), transparent: true, opacity: op == null ? 0.95 : op,
                                     blending: T.AdditiveBlending, depthWrite: false});
    this.mats.push(m); return m;
  };
  Holo.prototype.matFace = function(op){
    var m = new T.MeshBasicMaterial({color: this.cor.clone(), transparent: true, opacity: op == null ? 0.07 : op,
                                     side: T.DoubleSide, blending: T.AdditiveBlending, depthWrite: false});
    this.mats.push(m); return m;
  };
  /* sólido holográfico: arestas + face translúcida */
  Holo.prototype.solido = function(geo, angulo, opFace){
    var g = new T.Group();
    g.add(new T.LineSegments(new T.EdgesGeometry(geo, angulo == null ? 20 : angulo), this.matLinha()));
    g.add(new T.Mesh(geo, this.matFace(opFace)));
    return g;
  };
  Holo.prototype.arame = function(geo, op){
    return new T.LineSegments(new T.WireframeGeometry(geo), this.matLinha(op == null ? 0.5 : op));
  };
  Holo.prototype.linhas = function(pontos, op){
    var g = new T.BufferGeometry().setFromPoints(pontos.map(function(p){ return new T.Vector3(p[0], p[1], p[2]); }));
    return new T.LineSegments(g, this.matLinha(op));
  };
  Holo.prototype.setCor = function(hex){
    this.cor.set(hex);
    var c = this.cor;
    this.mats.forEach(function(m){ m.color.copy(c); });
  };
  Holo.prototype.limpar = function(){
    var r = this.raiz;
    while (r.children.length){
      var o = r.children.pop();
      o.traverse(function(x){ if (x.geometry) x.geometry.dispose(); });
    }
    this.mats.forEach(function(m){ m.dispose(); });
    this.mats = [];
    this.anim = null;
  };
  Holo.prototype.base = function(raio){
    var anel = new T.Mesh(new T.RingGeometry(raio * 0.98, raio, 64), this.matFace(0.35));
    anel.rotation.x = -Math.PI / 2; anel.position.y = -0.62;
    var anel2 = new T.LineSegments(new T.EdgesGeometry(new T.CircleGeometry(raio * 0.7, 48)), this.matLinha(0.3));
    anel2.rotation.x = -Math.PI / 2; anel2.position.y = -0.62;
    var g = new T.Group(); g.add(anel); g.add(anel2);
    return g;
  };

  /* ---------------------------------------------------------- troca de cena */
  Holo.prototype.mostrar = function(chave, tipo, url){
    if (chave === this.chave) return;
    this.chave = chave;
    var self = this;
    if (tipo === 'real' && url){
      fetch(url).then(function(r){ if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
        .then(function(buf){ if (self.chave === chave) self.real(new Float32Array(buf)); })
        .catch(function(){ if (self.chave === chave) self.ilustracao('peca'); });
      return;
    }
    this.ilustracao(tipo);
  };

  Holo.prototype.real = function(pos){
    this.limpar();
    var geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(pos, 3));
    geo.computeBoundingBox();
    var bb = geo.boundingBox, c = new T.Vector3(), tam = new T.Vector3();
    bb.getCenter(c); bb.getSize(tam);
    var esc = 2.1 / Math.max(tam.x, tam.y, tam.z, 1e-6);
    geo.translate(-c.x, -c.y, -c.z); geo.scale(esc, esc, esc);
    var g = this.solido(geo, 28, 0.05);
    this.raiz.add(g);
    this.raiz.add(this.base(1.25));
    var h = tam.y * esc;
    g.position.y = -0.62 + h / 2 + 0.02;
    this.anim = function(t){ g.position.y = -0.6 + h / 2 + Math.sin(t * 1.4) * 0.03; };
  };

  /* ---------------------------------------------------------- ilustrações */
  Holo.prototype.ilustracao = function(tipo){
    this.limpar();
    var f = ILUS[tipo] || ILUS.logo;
    f.call(this);
  };

  function engrenagem(dentes, rExt, rInt, furo){
    var s = new T.Shape(), n = dentes * 4;
    for (var i = 0; i <= n; i++){
      var a = i / n * Math.PI * 2, r = (Math.floor(i / 2) % 2) ? rInt : rExt;
      if (i === 0) s.moveTo(Math.cos(a) * r, Math.sin(a) * r); else s.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    }
    var h = new T.Path(); h.absarc(0, 0, furo, 0, Math.PI * 2, true); s.holes.push(h);
    return s;
  }
  function caixa(w, h, d){ return new T.BoxGeometry(w, h, d); }
  function pos(o, x, y, z){ o.position.set(x, y, z); return o; }

  var ILUS = {
    logo: function(){
      var s = new T.Shape(); s.moveTo(-1, -0.45); s.lineTo(-0.45, 0.2); s.lineTo(-0.2, -0.05); s.lineTo(0.25, 0.55);
      s.lineTo(1, -0.45); s.lineTo(-1, -0.45);
      var g = this.solido(new T.ExtrudeGeometry(s, {depth: 0.25, bevelEnabled: false}));
      g.position.set(0, -0.1, -0.12); this.raiz.add(g);
      var anel = this.solido(new T.TorusGeometry(1.15, 0.015, 6, 64)); anel.rotation.x = Math.PI / 2; anel.position.y = -0.55;
      this.raiz.add(anel);
    },
    peca: function(){
      var e = this.solido(new T.ExtrudeGeometry(engrenagem(14, 0.62, 0.52, 0.18), {depth: 0.22, bevelEnabled: false, curveSegments: 12}));
      e.position.set(-0.15, 0.05, -0.11); this.raiz.add(e);
      var sup = this.solido(caixa(1.5, 0.1, 0.5)); pos(sup, 0.1, -0.55, 0); this.raiz.add(sup);
      var ab = this.solido(caixa(0.1, 0.7, 0.5)); pos(ab, 0.8, -0.2, 0); this.raiz.add(ab);
      var self = this;
      this.anim = function(t){ e.rotation.z = t * 0.6; };
    },
    chapa: function(){
      var s = new T.Shape(), L = 0.8, H = 0.7, e = 0.06;
      s.moveTo(-L, H); s.lineTo(-L, 0); s.lineTo(L, 0); s.lineTo(L, H); s.lineTo(L - e, H); s.lineTo(L - e, e);
      s.lineTo(-L + e, e); s.lineTo(-L + e, H); s.lineTo(-L, H);
      var g = this.solido(new T.ExtrudeGeometry(s, {depth: 1.0, bevelEnabled: false}));
      g.position.set(0, -0.5, -0.5); this.raiz.add(g);
      for (var i = -2; i <= 2; i++){
        var furo = this.solido(new T.CylinderGeometry(0.06, 0.06, 0.08, 16)); pos(furo, i * 0.28, -0.47, 0); this.raiz.add(furo);
      }
      this.raiz.add(this.base(1.2));
    },
    montagem: function(){
      var b = this.solido(caixa(1.8, 0.12, 0.9)); pos(b, 0, -0.55, 0); this.raiz.add(b);
      var e1 = this.solido(new T.ExtrudeGeometry(engrenagem(12, 0.45, 0.37, 0.08), {depth: 0.12, bevelEnabled: false}));
      var e2 = this.solido(new T.ExtrudeGeometry(engrenagem(8, 0.3, 0.23, 0.06), {depth: 0.12, bevelEnabled: false}));
      pos(e1, -0.35, 0.05, 0); pos(e2, 0.38, 0.05, 0); this.raiz.add(e1); this.raiz.add(e2);
      [-0.35, 0.38].forEach(function(x){
        var p = this.solido(caixa(0.12, 0.62, 0.12)); pos(p, x, -0.2, -0.12); this.raiz.add(p);
      }, this);
      this.anim = function(t){ e1.rotation.z = t * 0.5; e2.rotation.z = -t * 0.5 * 12 / 8 + 0.2; };
    },
    desenho: function(){
      var folha = this.solido(new T.PlaneGeometry(1.9, 1.3)); pos(folha, 0, 0.05, 0); this.raiz.add(folha);
      var L = [], i;
      L.push([-0.88, -0.55, 0], [0.88, -0.55, 0], [0.88, -0.55, 0], [0.88, 0.65, 0], [0.88, 0.65, 0], [-0.88, 0.65, 0], [-0.88, 0.65, 0], [-0.88, -0.55, 0]);
      L.push([0.3, -0.55, 0], [0.3, -0.35, 0], [0.3, -0.35, 0], [0.88, -0.35, 0]);
      L.push([-0.6, -0.1, 0], [0.0, -0.1, 0], [0.0, -0.1, 0], [0.0, 0.4, 0], [0.0, 0.4, 0], [-0.6, 0.4, 0], [-0.6, 0.4, 0], [-0.6, -0.1, 0]);
      L.push([-0.6, -0.22, 0], [0.0, -0.22, 0], [-0.6, -0.18, 0], [-0.6, -0.26, 0], [0.0, -0.18, 0], [0.0, -0.26, 0]);
      for (i = 0; i < 24; i++){ var a = i / 24 * Math.PI * 2, b = (i + 1) / 24 * Math.PI * 2;
        L.push([0.45 + Math.cos(a) * 0.22, 0.15 + Math.sin(a) * 0.22, 0], [0.45 + Math.cos(b) * 0.22, 0.15 + Math.sin(b) * 0.22, 0]); }
      L.push([0.15, 0.15, 0], [0.75, 0.15, 0], [0.45, -0.15, 0], [0.45, 0.45, 0]);
      var d = this.linhas(L, 0.9); d.position.set(0, 0.05, 0.01); this.raiz.add(d);
      this.raiz.rotation.x = 0;
      this.anim = function(t){ folha.rotation.x = d.rotation.x = -0.25 + Math.sin(t) * 0.05; };
    },
    cad2d: function(){
      var grade = [], i;
      for (i = -5; i <= 5; i++){ grade.push([i * 0.2, -0.6, -1], [i * 0.2, -0.6, 1], [-1, -0.6, i * 0.2], [1, -0.6, i * 0.2]); }
      this.raiz.add(this.linhas(grade, 0.25));
      var p = [];
      p.push([-0.7, -0.6, -0.4], [0.5, -0.6, -0.4], [0.5, -0.6, -0.4], [0.5, -0.6, 0.5], [0.5, -0.6, 0.5], [-0.7, -0.6, 0.5], [-0.7, -0.6, 0.5], [-0.7, -0.6, -0.4]);
      for (i = 0; i < 32; i++){ var a = i / 32 * Math.PI * 2, b = (i + 1) / 32 * Math.PI * 2;
        p.push([-0.1 + Math.cos(a) * 0.25, -0.6, 0.05 + Math.sin(a) * 0.25], [-0.1 + Math.cos(b) * 0.25, -0.6, 0.05 + Math.sin(b) * 0.25]); }
      var desenho = this.linhas(p, 1); this.raiz.add(desenho);
      var cursor = this.solido(new T.ConeGeometry(0.06, 0.25, 4)); cursor.rotation.x = Math.PI; this.raiz.add(cursor);
      this.anim = function(t){ var a = t * 0.9; cursor.position.set(-0.1 + Math.cos(a) * 0.25, -0.45, 0.05 + Math.sin(a) * 0.25); };
    },
    movel: function(){
      var add = function(g, x, y, z){ this.raiz.add(pos(this.solido(g), x, y, z)); }.bind(this);
      add(caixa(1.5, 0.22, 0.75), 0, -0.25, 0);            // assento
      add(caixa(1.5, 0.6, 0.18), 0, 0.15, -0.3);          // encosto
      add(caixa(0.18, 0.42, 0.75), -0.84, -0.12, 0);      // braço
      add(caixa(0.18, 0.42, 0.75), 0.84, -0.12, 0);
      [[-0.8, -0.3], [0.8, -0.3], [-0.8, 0.3], [0.8, 0.3]].forEach(function(p){ add(new T.CylinderGeometry(0.035, 0.025, 0.25, 8), p[0], -0.48, p[1]); });
      add(caixa(0.5, 0.12, 0.45), -0.35, -0.08, 0.05);   // almofadas
      add(caixa(0.5, 0.12, 0.45), 0.35, -0.08, 0.05);
    },
    cnc: function(){
      var mesa = this.solido(caixa(1.9, 0.08, 1.2)); pos(mesa, 0, -0.6, 0); this.raiz.add(mesa);
      var placa = this.solido(caixa(1.4, 0.06, 0.8)); pos(placa, 0, -0.53, 0); this.raiz.add(placa);
      for (var i = 0; i < 7; i++){ var r = this.solido(caixa(0.12, 0.04 + (i % 3) * 0.03, 0.5)); pos(r, -0.55 + i * 0.18, -0.48, 0); this.raiz.add(r); }
      var portico = new T.Group();
      portico.add(pos(this.solido(caixa(0.1, 0.9, 0.1)), 0, -0.15, -0.6));
      portico.add(pos(this.solido(caixa(0.1, 0.9, 0.1)), 0, -0.15, 0.6));
      portico.add(pos(this.solido(caixa(0.14, 0.12, 1.3)), 0, 0.3, 0));
      var spindle = this.solido(new T.CylinderGeometry(0.11, 0.11, 0.45, 16)); pos(spindle, 0, 0.05, 0); portico.add(spindle);
      var fresa = this.solido(new T.ConeGeometry(0.04, 0.16, 8)); fresa.rotation.x = Math.PI; pos(fresa, 0, -0.25, 0); portico.add(fresa);
      this.raiz.add(portico);
      this.anim = function(t){ portico.position.x = Math.sin(t * 0.7) * 0.6; spindle.position.z = fresa.position.z = Math.sin(t * 1.3) * 0.3; };
    },
    laser: function(){
      var chapa = this.solido(caixa(1.8, 0.04, 1.1)); pos(chapa, 0, -0.55, 0); this.raiz.add(chapa);
      var corte = [], i;
      for (i = 0; i < 40; i++){ var a = i / 40 * Math.PI * 2, b = (i + 1) / 40 * Math.PI * 2;
        corte.push([Math.cos(a) * 0.4, -0.52, Math.sin(a) * 0.3], [Math.cos(b) * 0.4, -0.52, Math.sin(b) * 0.3]); }
      this.raiz.add(this.linhas(corte, 1));
      var cab = new T.Group();
      cab.add(pos(this.solido(new T.CylinderGeometry(0.1, 0.1, 0.35, 16)), 0, 0.15, 0));
      cab.add(pos(this.solido(new T.ConeGeometry(0.1, 0.22, 16)), 0, -0.13, 0));
      cab.children[1].rotation.x = Math.PI;
      var feixe = this.linhas([[0, -0.24, 0], [0, -0.52, 0]], 1); cab.add(feixe);
      this.raiz.add(cab);
      var n = 60, faisca = new Float32Array(n * 3), vel = [];
      for (i = 0; i < n; i++){ vel.push([0, 0, 0, 0]); }
      var gp = new T.BufferGeometry(); gp.setAttribute('position', new T.BufferAttribute(faisca, 3));
      var pm = new T.PointsMaterial({color: '#ffb020', size: 0.035, transparent: true, blending: T.AdditiveBlending, depthWrite: false});
      this.mats.push(pm);
      var pts = new T.Points(gp, pm); this.raiz.add(pts);
      this.anim = function(t, dt){
        var a = t * 0.8, x = Math.cos(a) * 0.4, z = Math.sin(a) * 0.3;
        cab.position.set(x, 0, z);
        for (var k = 0; k < n; k++){
          var v = vel[k];
          if (v[3] <= 0){ v[0] = (Math.random() - 0.5) * 0.9; v[1] = Math.random() * 0.6; v[2] = (Math.random() - 0.5) * 0.9; v[3] = 0.3 + Math.random() * 0.5;
            faisca[k * 3] = x; faisca[k * 3 + 1] = -0.52; faisca[k * 3 + 2] = z; }
          v[1] -= 2.5 * dt; v[3] -= dt;
          faisca[k * 3] += v[0] * dt; faisca[k * 3 + 1] = Math.max(-0.53, faisca[k * 3 + 1] + v[1] * dt); faisca[k * 3 + 2] += v[2] * dt;
        }
        gp.attributes.position.needsUpdate = true;
      };
    },
    planilha: function(){
      var g = [], i;
      for (i = 0; i <= 6; i++){ g.push([-0.9, -0.6, -0.6 + i * 0.2], [0.9, -0.6, -0.6 + i * 0.2]); }
      for (i = 0; i <= 6; i++){ g.push([-0.9 + i * 0.3, -0.6, -0.6], [-0.9 + i * 0.3, -0.6, 0.6]); }
      this.raiz.add(this.linhas(g, 0.35));
      var barras = [];
      for (i = 0; i < 5; i++){
        var b = this.solido(caixa(0.2, 1, 0.2)); pos(b, -0.6 + i * 0.3, -0.6, 0); this.raiz.add(b); barras.push(b);
      }
      this.anim = function(t){
        barras.forEach(function(b, k){ var h = 0.25 + (k + 1) * 0.16 + Math.sin(t * 1.5 + k) * 0.08; b.scale.y = h; b.position.y = -0.6 + h / 2; });
      };
    },
    documento: function(){
      var fs = [];
      for (var i = 0; i < 3; i++){
        var f = new T.Group();
        f.add(this.solido(new T.PlaneGeometry(1.0, 1.35)));
        var L = [];
        for (var k = 0; k < 9; k++){ var w = (k % 4 === 3) ? 0.4 : 0.75; L.push([-0.38, 0.5 - k * 0.12, 0.01], [-0.38 + w, 0.5 - k * 0.12, 0.01]); }
        f.add(this.linhas(L, 0.8));
        f.position.set(i * 0.12 - 0.12, 0.05 + i * 0.04, -i * 0.12);
        f.rotation.z = (i - 1) * 0.06;
        this.raiz.add(f); fs.push(f);
      }
      this.anim = function(t){ fs.forEach(function(f, k){ f.position.y = 0.05 + k * 0.04 + Math.sin(t + k) * 0.03; }); };
    },
    globo: function(){
      var s = this.arame(new T.SphereGeometry(0.8, 18, 12), 0.45); this.raiz.add(s);
      var anel = this.solido(new T.TorusGeometry(1.05, 0.012, 6, 64)); anel.rotation.x = Math.PI / 2.4; this.raiz.add(anel);
      var sat = this.solido(new T.SphereGeometry(0.06, 8, 6)); this.raiz.add(sat);
      this.anim = function(t){ var a = t * 1.2; sat.position.set(Math.cos(a) * 1.05, Math.sin(a) * 1.05 * Math.cos(Math.PI / 2.4), Math.sin(a) * 1.05 * Math.sin(Math.PI / 2.4) * -1); };
    },
    pasta: function(){
      var fundo = this.solido(caixa(1.4, 1.0, 0.05)); pos(fundo, 0, -0.05, -0.1); this.raiz.add(fundo);
      var aba = this.solido(caixa(0.5, 0.12, 0.05)); pos(aba, -0.45, 0.5, -0.1); this.raiz.add(aba);
      var folhas = this.solido(caixa(1.25, 0.85, 0.03)); pos(folhas, 0, -0.02, -0.05); this.raiz.add(folhas);
      var frente = new T.Group(); var fr = this.solido(caixa(1.4, 0.9, 0.05)); pos(fr, 0, 0.45, 0); frente.add(fr);
      frente.position.set(0, -0.55, 0.02); this.raiz.add(frente);
      this.anim = function(t){ frente.rotation.x = 0.15 + (Math.sin(t * 1.1) * 0.5 + 0.5) * 0.45; };
    },
    mensagem: function(){
      var env = this.solido(caixa(1.4, 0.9, 0.06)); this.raiz.add(env);
      this.raiz.add(this.linhas([[-0.7, 0.45, 0.04], [0, -0.05, 0.04], [0, -0.05, 0.04], [0.7, 0.45, 0.04]], 1));
      this.anim = function(t){ env.position.y = Math.sin(t * 1.3) * 0.05; };
    },
    familia: function(){
      /* pai e filho brincando de jogar a bola */
      var self = this;
      function membro(r, L, x, y, z, rx, rz){
        var m = self.solido(new T.CapsuleGeometry(r, L, 3, 8), 30, 0.06); m.position.set(x, y, z); m.rotation.set(rx || 0, 0, rz || 0); return m;
      }
      function braco(lado, angulo){
        var ombro = new T.Group(); ombro.position.set(lado * 0.27, 1.22, 0);
        var b = membro(0.055, 0.42, 0, -0.27, 0); ombro.add(b);
        ombro.rotation.set(angulo, 0, lado * 0.12);
        return ombro;
      }
      function pessoa(esc, angBracos){
        var p = new T.Group();
        p.add(membro(0.085, 0.55, -0.09, 0.33, 0));           // pernas
        p.add(membro(0.085, 0.55, 0.09, 0.33, 0));
        p.add(membro(0.17, 0.42, 0, 0.98, 0));                // tronco
        var pesc = membro(0.05, 0.05, 0, 1.33, 0); p.add(pesc);
        var cab = self.solido(new T.SphereGeometry(0.16, 12, 9), 30, 0.06); cab.position.set(0, 1.52, 0); p.add(cab);
        p.bE = braco(-1, angBracos); p.bD = braco(1, angBracos);
        p.add(p.bE); p.add(p.bD);
        p.scale.setScalar(esc);
        return p;
      }
      var pai = pessoa(0.8, 1.1); pai.position.set(-0.75, -0.62, 0); pai.rotation.y = Math.PI / 2; this.raiz.add(pai);
      var filho = pessoa(0.45, 1.6); filho.position.set(0.7, -0.62, 0); filho.rotation.y = -Math.PI / 2; this.raiz.add(filho);
      var bola = this.solido(new T.SphereGeometry(0.085, 10, 8), 30, 0.12); this.raiz.add(bola);
      this.raiz.add(this.base(1.3));
      var de = new T.Vector3(-0.42, 0.3, 0), ate = new T.Vector3(0.5, 0.0, 0);
      this.anim = function(t){
        var ciclo = (t * 0.42) % 2, ida = ciclo < 1, u = ida ? ciclo : ciclo - 1;
        var a = ida ? de : ate, b = ida ? ate : de;
        bola.position.lerpVectors(a, b, u); bola.position.y += Math.sin(u * Math.PI) * 0.5;
        bola.rotation.z = t * 4;
        var pegaPai = Math.max(0, 1 - Math.min(Math.abs(ciclo), Math.abs(2 - ciclo)) * 4);
        var pegaFilho = Math.max(0, 1 - Math.abs(ciclo - 1) * 4);
        pai.bE.rotation.x = pai.bD.rotation.x = 1.0 + pegaPai * 0.5;
        filho.bE.rotation.x = filho.bD.rotation.x = 1.3 + pegaFilho * 0.9;
        filho.position.y = -0.62 + Math.abs(Math.sin(t * 2.4)) * 0.045;   // o pequeno pula de alegria
      };
    }
  };

  return {criar: function(canvas, rotulo){ return new Holo(canvas, rotulo); }, tipos: Object.keys(ILUS)};
})();
