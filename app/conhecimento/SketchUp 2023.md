# SketchUp 2023 (inglês)
Termos: linha (Line), retângulo (Rectangle), círculo (Circle), arco (Arc), empurrar/puxar (Push/Pull), mover (Move), girar (Rotate), escala (Scale), equidistante/offset (Offset), borracha (Eraser), pintar/material (Paint Bucket), trena/medir (Tape Measure), orbitar (Orbit), grupo (Group), componente (Component), camada (Tag).
Atalhos padrão do SketchUp. Podem ter sido mudados em Window > Preferences > Shortcuts.

## Atalhos de ferramentas
Espaço: Select (selecionar). L: Line (linha). R: Rectangle (retângulo). C: Circle (círculo). A: Arc (arco de 2 pontos). P: Push/Pull (empurrar/puxar, dar volume). M: Move (mover; com Ctrl copia). Q: Rotate (girar). S: Scale (escala). F: Offset (equidistante). E: Eraser (borracha; com Shift oculta, com Ctrl suaviza arestas). B: Paint Bucket (pintar material). T: Tape Measure (trena e linhas guia). O: Orbit (orbitar). H: Pan. Z: Zoom. Shift+Z: Zoom Extents (mostrar tudo). G: Make Component (criar componente).
Ctrl+A selecionar tudo. Ctrl+Z desfazer. Ctrl+Y refazer. Ctrl+S salvar.

## Truques de precisão
Depois de começar uma linha, digite o comprimento (ex.: 1200) e Enter. No retângulo digite 1200;600 e Enter.
Na Push/Pull digite a espessura e Enter. Duplo clique na Push/Pull repete a última distância.
Na Move com Ctrl (cópia) digite x5 para 5 cópias na mesma distância, ou /5 para dividir o espaço em 5.
Setas do teclado travam eixos: seta direita = vermelho, esquerda = verde, cima = azul. Shift trava a direção atual.

## Grupos e componentes
Make Group: botão direito > Make Group. Make Component: G. Use grupo para peças únicas e componente para peças repetidas (editar uma muda todas).
Duplo clique entra para editar o grupo/componente; Esc sai.
Botão direito > Make Unique: separa uma cópia de componente das outras.
Tags (antigas Layers): controlam visibilidade. Outliner mostra a hierarquia.

## Ferramentas úteis
Follow Me: extrusão ao longo de um caminho (molduras, perfis, tubos). Selecione o caminho, ative Follow Me, clique no perfil.
Intersect Faces: botão direito > Intersect Faces > With Model (cria arestas onde objetos se cruzam).
Solid Tools (Pro): Union, Subtract, Trim, Intersect, Split — funcionam com grupos/componentes sólidos (fechados).
Espelhar (mirror): selecione o grupo/componente, botão direito > Flip Along (inverter ao longo) > escolha o eixo vermelho, verde ou azul. Para espelhar uma cópia, copie antes com Move + Ctrl. Outra forma: ferramenta Scale (S) digitando -1.
Suavizar arestas: Soften/Smooth Edges. Inverter face: botão direito > Reverse Faces (face azul = verso, branca = frente).
Esconder/ocultar: botão direito > Hide; mostrar de novo: Edit > Unhide > All.
Dimension (cotas), Text, 3D Text, Protractor (transferidor), Section Plane (plano de corte).

## Exportar e importar
File > Import: DWG/DXF (Pro), imagens, 3DS, SKP.
File > Export > 2D Graphic (imagem, PDF, DWG 2D na versão Pro) e 3D Model (DWG, DXF, OBJ, STL, 3DS... na versão Pro).
Para salvar em versão antiga: File > Save As e escolha a versão.

## Problemas comuns
Face que não fecha: alguma aresta não está no mesmo plano ou há uma linha faltando; desenhe a aresta faltante com a Line.
Modelo pesado: use componentes, apague geometria escondida (Window > Model Info > Statistics > Purge Unused), desligue sombras.
Zoom estranho/câmera cortando: Camera > Field of View ou Zoom Extents (Shift+Z).
