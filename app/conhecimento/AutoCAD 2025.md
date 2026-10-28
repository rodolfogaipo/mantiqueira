# AutoCAD 2025 (inglês)
Termos: linha (LINE), polilinha (PLINE), círculo (CIRCLE), mover (MOVE), copiar (COPY), girar (ROTATE), espelhar (MIRROR), equidistante/paralela (OFFSET), aparar/cortar (TRIM), estender (EXTEND), arredondar/concordância (FILLET), chanfro (CHAMFER), explodir (EXPLODE), unir (JOIN), cota (DIM), camada (LAYER), bloco (BLOCK), hachura (HATCH), imprimir (PLOT), medir distância (DIST), área (AREA).
Os comandos são digitados na linha de comando em inglês. Atalho = letras abreviadas + Enter. Espaço também funciona como Enter. Enter vazio repete o último comando.

## Desenho (draw)
LINE (L) linha. PLINE (PL) polilinha. CIRCLE (C) círculo. ARC (A) arco. RECTANG (REC) retângulo. POLYGON (POL) polígono. ELLIPSE (EL) elipse. SPLINE (SPL) curva spline. XLINE (XL) linha de construção infinita. POINT (PO) ponto.
HATCH (H) hachura. TEXT (DT) texto de uma linha. MTEXT (T ou MT) texto de várias linhas. MLEADER (MLD) chamada com seta.
BLOCK (B) criar bloco. INSERT (I) inserir bloco. BEDIT (BE) editar bloco. WBLOCK (W) salvar bloco em arquivo.

## Edição (modify)
MOVE (M) mover. COPY (CO ou CP) copiar. ROTATE (RO) girar. SCALE (SC) escala. MIRROR (MI) espelhar. OFFSET (O) paralela/equidistante. ARRAY (AR) matriz (retangular, polar, por caminho).
TRIM (TR) aparar. EXTEND (EX) estender. FILLET (F) concordância/arredondar (raio 0 junta cantos). CHAMFER (CHA) chanfro.
STRETCH (S) esticar (selecionar com janela cruzada). LENGTHEN (LEN) alongar. BREAK (BR) quebrar. JOIN (J) unir. EXPLODE (X) explodir. ERASE (E) apagar. ALIGN (AL) alinhar.
MATCHPROP (MA) copiar propriedades de um objeto para outro.
OVERKILL apaga linhas duplicadas/sobrepostas (muito útil antes de mandar DXF para corte).
PEDIT (PE) editar polilinha; opção Join transforma linhas em polilinha fechada.

## Cotas (dimension)
DIM cota inteligente. DIMLINEAR (DLI) linear. DIMALIGNED (DAL) alinhada. DIMRADIUS (DRA) raio. DIMDIAMETER (DDI) diâmetro. DIMANGULAR (DAN) ângulo. DIMCONTINUE (DCO) continuar. DIMBASELINE (DBA) linha de base.
DIMSTYLE (D) estilos de cota (tamanho de texto, setas, unidades).

## Precisão e modos
F3 liga/desliga OSNAP (pontos de snap). OSNAP (OS) escolhe quais pontos (Endpoint, Midpoint, Center, Intersection, Perpendicular...).
F8 ORTHO (só horizontal/vertical). F10 POLAR. F11 rastreamento de snap. F12 entrada dinâmica. F9 snap de grade. F7 grade.
Coordenadas: @100,0 relativo; @100<45 polar (distância<ângulo).
UNITS (UN) unidades. Para trabalhar em milímetros use o template acadiso.dwt.

## Consulta e medidas
DIST (DI) distância. AREA (AA) área. LIST (LI) informações do objeto. MEASUREGEOM (MEA) medir. ID coordenada de um ponto.
QSELECT seleção rápida por tipo/propriedade. SELECTSIMILAR seleciona objetos parecidos.
Ctrl+1 abre a paleta de Propriedades.

## Camadas e organização
LAYER (LA) gerenciador de camadas. LAYISO isola camada. LAYUNISO desfaz. LAYOFF desliga a camada do objeto. LAYON liga todas.
PURGE (PU) limpa blocos, camadas e estilos não usados. AUDIT e RECOVER corrigem arquivos com erro.
XREF (XR) referências externas. IMAGE anexar imagem.

## Zoom e tela
Z + Enter + E (ZOOM Extents) mostra tudo. Duplo clique na roda do mouse também faz zoom extents.
REGEN (RE) redesenha a tela. Ctrl+0 tela limpa.

## Layout e impressão
LAYOUT, MVIEW (MV) janelas de vista no layout. Escala da viewport pela barra de status.
PLOT (Ctrl+P) imprimir/gerar PDF (impressora "DWG To PDF.pc3"). PUBLISH várias folhas em PDF.

## Arquivos para corte (laser, router)
Antes de exportar: OVERKILL, PEDIT/JOIN para fechar contornos, apagar cotas e textos, conferir escala 1:1 em mm.
SAVEAS escolhendo DXF (versão R2013 ou anterior costuma ser a mais compatível com máquinas). DXFOUT também exporta.

## Atalhos gerais
Ctrl+N novo. Ctrl+O abrir. Ctrl+S salvar. Ctrl+Shift+S salvar como. Ctrl+Z desfazer. Ctrl+Y refazer. Ctrl+C / Ctrl+V copiar e colar entre desenhos. Ctrl+Shift+V cola como bloco. Esc cancela.
