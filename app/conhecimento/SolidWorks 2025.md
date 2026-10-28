# SolidWorks 2025 (português)

## Atalhos de teclado
### Vistas e zoom
Ctrl+1 vista frontal. Ctrl+2 vista posterior. Ctrl+3 vista esquerda. Ctrl+4 vista direita. Ctrl+5 vista superior. Ctrl+6 vista inferior. Ctrl+7 vista isométrica. Ctrl+8 normal a (olhar de frente para a face ou plano selecionado).
Barra de espaço abre o seletor de orientação da vista.
F faz o zoom para ajustar (mostrar a peça inteira). Z afasta o zoom, Shift+Z aproxima.
Roda do mouse: girar a roda aproxima e afasta; clicar e arrastar com a roda gira a vista; Ctrl + roda arrastando move (pan).
### Reconstruir e arquivos
Ctrl+B reconstruir (rebuild). Ctrl+Q forçar reconstrução de tudo.
Ctrl+N novo documento. Ctrl+O abrir. Ctrl+S salvar. Ctrl+Tab alterna entre documentos abertos. R abre os documentos recentes.
Ctrl+Z desfazer. Ctrl+Y refazer. Enter repete o último comando. Esc cancela/sai do comando.
### Menus rápidos
Tecla S abre a barra de atalhos (shortcut bar) com comandos do contexto (esboço, peça, montagem, desenho). Dá para personalizar clicando com o botão direito nela.
Gestos do mouse: segurar o botão direito e arrastar em uma direção chama o comando daquela direção.
Na montagem: Tab oculta o componente sob o mouse; Shift+Tab mostra de novo.

## Esboço
### Comandos de esboço
Linha, Retângulo de canto, Retângulo de centro, Círculo, Arco de 3 pontos, Arco tangente, Ranhura, Polígono, Spline, Linha de centro (construção).
Aparar entidades (trim): apaga pedaços de linhas; a opção "Aparar ao mais próximo" é a mais usada.
Estender entidades: prolonga até a próxima linha.
Converter entidades: copia arestas da peça para o esboço.
Equidistanciar entidades (offset): cria contorno paralelo a uma distância.
Espelhar entidades: espelha em relação a uma linha de centro.
Padrão linear/circular de esboço: repete entidades do esboço.
Filete de esboço e Chanfro de esboço: arredondam/chanfram cantos do esboço.
### Cotas e relações
Cota inteligente (Smart Dimension) cota distâncias, diâmetros e ângulos. Dá para digitar contas na caixa da cota (ex.: 1200/2) e usar equações iniciando com "=".
Adicionar relação: Horizontal, Vertical, Coincidente, Colinear, Paralela, Perpendicular, Tangente, Concêntrica, Igual, Fixa, Ponto médio, Simétrica.
Esboço azul = subdefinido (falta cota/relação). Preto = totalmente definido. Vermelho/amarelo = definido em excesso ou com erro.
Ferramentas > Esboço > Reparar esboço ajuda a achar linhas sobrepostas ou abertas.

## Recursos de peça
Ressalto/base extrudado: dá espessura a um esboço (extrusão). Corte extrudado: remove material. Condições finais: Cego, Passante por tudo, Até o próximo, Até a superfície, Plano médio.
Ressalto/base revolucionado e Corte revolucionado: giram um esboço em torno de uma linha de centro.
Ressalto/base varrido e Corte varrido: perfil percorrendo um caminho.
Ressalto/base por loft e Corte por loft: transição entre dois ou mais perfis.
Filete: arredonda arestas. Chanfro: chanfra arestas.
Casca: deixa a peça oca com parede de espessura definida. Nervura: reforço a partir de um esboço aberto. Inclinação: ângulo de saída.
Assistente de perfuração (Hole Wizard): furos padronizados, roscados, escareados e rebaixados.
Padrão linear, Padrão circular, Padrão orientado por curva, Padrão orientado por esboço, Espelhar: repetem recursos ou corpos.
Geometria de referência: Plano, Eixo, Sistema de coordenadas, Ponto.
Combinar (somar, subtrair, comum) e Dividir trabalham com vários corpos.
Mover/copiar corpos: Inserir > Recursos > Mover/copiar.

## Chapa metálica
Flange-base/aba: cria a primeira chapa a partir de um esboço (define espessura, raio de dobra e fator K).
Flange de aresta: dobra uma aba a partir de uma aresta. Flange de meia-esquadria: abas ao longo de várias arestas com cantos em esquadria.
Bainha: dobra a borda sobre si mesma. Dobra esboçada: dobra ao longo de uma linha de esboço. Jog: dobra dupla em degrau.
Cantos: Canto fechado, Alívio de canto, Quebrar canto (chanfro/filete no canto).
Desdobrar e Dobrar: abrem e fecham dobras para fazer cortes que atravessam a dobra.
Planificar: mostra a peça aberta (padrão plano). Converter em chapa metálica: transforma um sólido em chapa.
Tabela de calibre/dobras: define espessuras e raios padronizados; Fator K comum entre 0,33 e 0,5 (confira com a sua dobradeira).
### Exportar DXF da chapa planificada
Na árvore, clique com o botão direito em "Padrão plano" (Flat-Pattern) > Exportar para DXF/DWG. Marque "Geometria" e, se quiser, "Linhas de dobra". Também funciona por Arquivo > Salvar como > DXF.
Para várias peças: o Task Scheduler (Agendador de tarefas) do SolidWorks exporta em lote (confira se está instalado).

## Montagem
Inserir componentes: coloca peças/submontagens. O primeiro componente fica fixo (f) por padrão; botão direito > Flutuar para soltar.
Posicionamento (Mate): Coincidente, Paralela, Perpendicular, Tangente, Concêntrica, Travar, Distância, Ângulo. Posicionamentos avançados: Simétrico, Largura, Limite de distância/ângulo. Mecânicos: Engrenagem, Came, Dobradiça, Ranhura.
Mover componente e Girar componente. Detecção de interferência: Ferramentas > Avaliar > Detecção de interferência.
Vista explodida: Inserir > Vista explodida (ou aba Configurações). Recolher/explodir com botão direito.
Padrão de componentes e Espelhar componentes. Pasta inteligente de fixadores: Toolbox (se instalado).
Lista de materiais é feita no desenho (Inserir > Tabelas > Lista de materiais).

## Desenho (detalhamento)
Vista do modelo (insere as vistas da peça), Vista projetada, Vista auxiliar, Vista de seção (corte), Vista de detalhe (ampliação), Vista interrompida (quebra), Vista de recorte.
Itens do modelo: puxa as cotas da peça para o desenho. Cota inteligente também funciona no desenho.
Nota (texto), Balão e Balão automático, Símbolo de acabamento, Símbolo de solda, Linha de centro e Marca de centro.
Tabelas: Lista de materiais (BOM), Tabela de furos, Tabela de revisões, Tabela de dobras (chapa).
Formato de folha/legenda: botão direito na folha > Editar formato da folha. Propriedades personalizadas do arquivo preenchem a legenda.
Exportar PDF: Arquivo > Salvar como > PDF. Exportar DWG/DXF: Arquivo > Salvar como > DWG/DXF.

## Configurações, equações e propriedades
Configurações (aba do ConfigurationManager): várias versões da mesma peça (tamanhos diferentes). Tabela de projeto (Design Table) controla configurações pelo Excel: Inserir > Tabelas > Tabela de projeto.
Equações: Ferramentas > Equações. Variáveis globais (ex.: "largura" = 1200) usadas nas cotas com "=".
Propriedades personalizadas: Arquivo > Propriedades (código, material, descrição). Aparecem na lista de materiais e na legenda.
Material: botão direito em "Material" na árvore > Editar material (define densidade para calcular a massa).

## Medir e avaliar
Medir: Ferramentas > Avaliar > Medir (distâncias, ângulos, raios, área).
Propriedades de massa: Ferramentas > Avaliar > Propriedades de massa (peso, volume, centro de massa). Precisa do material aplicado.
Verificar geometria, Análise de inclinação e Análise de espessura também estão em Avaliar.

## Problemas comuns
Recurso com erro (vermelho na árvore): clique com o botão direito > "O que está errado?". Geralmente é esboço aberto, referência perdida ou cota impossível.
"Esboço aberto" em extrusão: use Ferramentas > Esboço > Reparar esboço ou procure linhas sobrepostas.
Peça pesada/lenta: suprimir recursos de detalhe (filetes, padrões), usar modo simplificado/Large Assembly na montagem, desligar RealView.
Arquivo de outra versão: o SolidWorks abre arquivos de versões anteriores, mas não abre de versões mais novas.
