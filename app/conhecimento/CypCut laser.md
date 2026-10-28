# CypCut (corte a laser, Friendess)
Funções do CypCut para máquinas de corte a laser de chapa. Os nomes podem variar com a versão e o idioma; atalhos não estão listados porque mudam entre versões — confira no programa.

## Importar e preparar o desenho
Importar: DXF, DWG, AI, PLT, NC. Antes de importar, no CAD: escala 1:1 em mm, contornos fechados, sem linhas duplicadas, sem cotas e textos.
Otimizar (Optimize): remove linhas duplicadas, junta linhas conectadas, apaga objetos muito pequenos e suaviza curvas. Rode sempre depois de importar.
Verificar contornos abertos: contornos abertos aparecem com cor diferente e não recebem entrada/compensação.
Interno/externo: o programa identifica contornos internos (furos) e externos (peça) para aplicar a entrada do lado certo.

## Parâmetros de corte
Camadas (layers): cada cor de camada tem seus parâmetros — velocidade de corte, potência do laser, frequência e ciclo de trabalho, tipo e pressão do gás (oxigênio, nitrogênio, ar), altura de corte (bico até a chapa), parâmetros de perfuração (pierce).
Perfuração em etapas é usada em chapas grossas para não espirrar material no bico.
Ajuste fino: se a parte de baixo ficar com rebarba, geralmente é velocidade alta, foco errado ou pressão de gás baixa (confira com a tabela do fabricante da fonte laser).

## Tecnologia de corte
Linha de entrada/saída (Lead-in/Lead-out): o laser fura fora do contorno e entra na linha, evitando marca na peça. Em furos a entrada fica por dentro.
Compensação de corte (Kerf): desloca o caminho metade da largura do feixe para a peça sair na medida certa.
Micro-junta (Micro joint): pequenas pontes não cortadas que seguram a peça na chapa.
Ponte (Bridge): liga peças próximas para cortar de uma vez.
Aresta comum (Common edge): peças encostadas compartilham a mesma linha de corte, economizando tempo e material.
Ponto de resfriamento (Cooling point) e Corte de cantos: evitam queimar cantos vivos.
Ordem de corte (Sort): define a sequência — normalmente furos internos antes do contorno externo, e de um lado para o outro da chapa.
Ponto inicial (Start point): onde cada contorno começa; evite começar em canto vivo.

## Operação
Simular: mostra o caminho e o tempo estimado antes de cortar.
Enquadrar (Frame): a cabeça percorre o contorno externo do trabalho sem laser para conferir se cabe na chapa.
Rodar a seco (Dry run): executa o programa sem ligar o laser.
Retomar do ponto de parada (Breakpoint/Resume): continua de onde parou depois de uma interrupção.
Voltar à origem e definir origem: a origem do trabalho deve bater com o canto da chapa na mesa.
Aninhamento (nesting) automático é feito no CypNest (programa separado) ou pela função de nesting da sua versão.
