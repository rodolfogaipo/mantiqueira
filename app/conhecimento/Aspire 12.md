# Vectric Aspire 12 (router CNC)
Os nomes podem aparecer em inglês ou português, dependendo do idioma escolhido na instalação. Confira atalhos no próprio programa (Help > Keyboard Shortcuts).

## Configurar o trabalho (Job Setup)
Ao criar o trabalho defina: tamanho do material (X, Y), espessura (Z), onde fica o zero Z (topo do material ou mesa), origem XY (canto ou centro), unidades (mm).
Editar depois: Edit > Job Setup (ou clicar duas vezes no tamanho do material). Errar o zero Z é a causa mais comum de cortar a mesa ou não atravessar.

## Desenho e edição de vetores
Criar: linha/polilinha, retângulo, círculo, elipse, polígono, estrela, arco, texto.
Importar vetores: File > Import > Import Vectors (DXF, DWG, EPS, AI, SVG, PDF).
Editar: Offset (contorno paralelo), Weld (soldar vetores sobrepostos), Subtract, Intersect, Trim (aparar), Join (unir vetores abertos), Close (fechar), Fillet (arredondar canto), Mirror, Align (alinhar), Distort, Array copy (cópias em matriz), Circular array.
Tecla N: alterna o modo de edição de nós (pontos do vetor). Tecla F9: centraliza o objeto no material (confira).
Vetores abertos não servem para perfil fechado nem bolsão: use Join/Close ou "Join open vectors" com tolerância.
Nesting (aninhamento): Edit > Nest Selected Objects — arruma as peças no material economizando chapa.

## Percursos de ferramenta (toolpaths)
Profile (perfil): corta por fora, por dentro ou em cima do vetor. Use Tabs (pontes) para a peça não soltar, Ramps (rampa de entrada) e Allowance (sobremetal) se for fazer acabamento.
Pocket (bolsão/cavidade): esvazia a área dentro do vetor até uma profundidade.
Drilling (furação): furos nos centros dos círculos.
V-Carve/Engrave: gravação com fresa em V, ótima para letras.
Fluting, Prism, Inlay (marchetaria) e Texture toolpaths.
3D Roughing (desbaste) e 3D Finishing (acabamento) para modelos 3D; Moulding Toolpath para molduras.
Biblioteca de ferramentas (Tool Database): diâmetro, passo (stepdown), sobreposição (stepover), rotação (spindle) e avanço (feed rate).
Preview Toolpaths: simula o corte. Reset Preview limpa a simulação.
Save Toolpath: escolha o pós-processador da sua máquina (ex.: G-code mm, Mach3 mm). Pós errado = máquina faz movimento errado.

## Modelagem 3D (Aspire)
Componentes 3D: Create Shape (forma a partir de vetor), Two Rail Sweep (perfil entre dois trilhos), Extrude & Weave, Moulding, Rotate/Spin, Sculpt (esculpir), Texture Area, Fade, Tilt.
Clip Art: biblioteca de modelos 3D prontos. Component Tree: organiza os componentes em níveis (Levels) e combina com Add, Subtract, Merge, Low/High.

## Dicas
Sempre simule antes de cortar. Confira se a profundidade de corte passante é um pouco maior que a espessura (ex.: +0,3 mm) usando sacrificial na mesa.
Para chapas grandes, mantenha as pontes (tabs) e corte as peças pequenas primeiro.
