"""Curiosidades e frases motivacionais para quando o usuário quiser relaxar a cabeça.
Escolhe ao acaso sem repetir as últimas."""
import random

CURIOSIDADES = {
    "madeira e marcenaria": [
        "A madeira continua se movimentando depois de cortada: ela incha e encolhe com a umidade do ar, principalmente no sentido da largura das tábuas, quase nada no comprimento. Por isso tampos largos precisam de fixações que deixem a madeira trabalhar.",
        "O MDF é feito de fibras de madeira prensadas com resina. Ele não tem veios, por isso usina e pinta muito bem, mas segura parafuso pior pela borda do que pela face.",
        "O pau-brasil, árvore que deu nome ao país, era explorado para tirar um corante vermelho usado em tecidos na Europa.",
        "A marcenaria japonesa tradicional tem encaixes tão precisos que móveis e templos inteiros são montados quase sem pregos nem parafusos.",
        "A cadeira de balanço moderna ficou popular nos Estados Unidos no século dezoito, e o designer Michael Thonet tornou famosas as cadeiras de balanço de madeira curvada a vapor no século dezenove.",
        "A técnica de curvar madeira com vapor funciona porque o calor e a umidade amolecem a lignina, a 'cola natural' que mantém as fibras unidas.",
        "O compensado é estável porque as lâminas são coladas com os veios cruzados, uma camada contra a outra; assim uma segura o movimento da outra.",
        "A Cadeira Nº 14 da Thonet, de 1859, foi uma das primeiras cadeiras fabricadas em grande escala e era vendida desmontada, em poucas peças.",
        "Madeiras como o ipê são tão densas que afundam na água.",
        "A balsa, usada em aeromodelismo, é uma das madeiras mais leves que existem, mas mesmo assim é classificada botanicamente como madeira dura.",
    ],
    "engenharia e metal": [
        "O aço inox não enferruja facilmente porque tem cromo: ele forma uma camada finíssima de óxido na superfície que se regenera sozinha quando é riscada.",
        "No corte a laser de aço carbono com oxigênio, boa parte da energia vem da própria queima do ferro com o oxigênio; o laser 'acende' a reação.",
        "O alumínio já foi mais caro que o ouro. No século dezenove, Napoleão Terceiro teria servido os convidados mais importantes em pratos de alumínio.",
        "A Torre Eiffel cresce alguns centímetros no verão por causa da dilatação do ferro com o calor.",
        "O fator K da chapa metálica indica onde fica a linha neutra dentro da espessura na dobra: ela não muda de comprimento quando a chapa é dobrada.",
        "As primeiras máquinas CNC surgiram por volta de 1950, ligadas a pesquisas do MIT, e usavam fita perfurada para receber o programa.",
        "O concreto armado foi patenteado no século dezenove por um jardineiro francês, Joseph Monier, que queria vasos mais resistentes.",
        "Pontes de aço têm juntas de dilatação justamente para não trincarem quando esquentam e esfriam.",
        "O primeiro programa de CAD com interface gráfica, o Sketchpad, foi criado por Ivan Sutherland em 1963.",
        "Uma folha de papel A4 tem proporção raiz de dois: cortada ao meio, as duas metades mantêm exatamente a mesma proporção.",
    ],
    "ciência": [
        "A luz do Sol leva cerca de oito minutos e vinte segundos para chegar à Terra.",
        "Um raio pode esquentar o ar ao seu redor a temperaturas mais altas do que a superfície do Sol.",
        "O coração humano bate cerca de cem mil vezes por dia.",
        "Os polvos têm três corações e sangue azulado, por causa de uma proteína com cobre chamada hemocianina.",
        "O mel bem armazenado praticamente não estraga: já foram achados potes de mel em tumbas egípcias.",
        "A água é uma das poucas substâncias que ficam menos densas quando congelam; por isso o gelo boia.",
        "Há mais estrelas no universo observável do que grãos de areia em todas as praias da Terra, segundo as estimativas dos astrônomos.",
        "O corpo humano adulto tem duzentos e seis ossos; um bebê nasce com cerca de trezentos, que vão se fundindo com o crescimento.",
        "O som viaja cerca de quatro vezes mais rápido na água do que no ar.",
        "As bananas são levemente radioativas, por causa do potássio que têm. Nada perigoso: é uma quantidade minúscula.",
        "A Lua se afasta da Terra cerca de quatro centímetros por ano.",
        "Os diamantes e o grafite do lápis são feitos do mesmo elemento, o carbono; o que muda é como os átomos estão arrumados.",
    ],
    "história": [
        "A Grande Muralha da China não é visível a olho nu do espaço, ao contrário do que muita gente pensa.",
        "Os antigos romanos usavam um concreto feito com cinza vulcânica que fica mais resistente com o tempo em contato com a água do mar.",
        "A imprensa de tipos móveis de Gutenberg, por volta de 1450, ajudou a espalhar livros pela Europa como nunca antes.",
        "Brasília foi construída em pouco mais de três anos e inaugurada em 1960.",
        "O primeiro voo de Santos Dumont com o 14-Bis, em Paris, aconteceu em 1906, diante de uma comissão que registrou o feito.",
        "A Serra da Mantiqueira tem esse nome de origem tupi, que costuma ser traduzido como 'serra que chora', por causa das muitas nascentes.",
        "O relógio de pulso ficou popular entre homens depois que aviadores e soldados passaram a usá-lo, no começo do século vinte; Santos Dumont foi um dos primeiros a usar um.",
        "As pirâmides de Gizé eram revestidas com calcário branco polido, que as deixava brilhando ao sol.",
        "O primeiro e-mail foi enviado em 1971 por Ray Tomlinson, que escolheu o símbolo arroba para separar o nome do computador.",
    ],
    "natureza": [
        "As abelhas se comunicam com uma 'dança' que indica a direção e a distância das flores.",
        "Algumas árvores, como os eucaliptos, crescem tão rápido que podem passar de dez metros em poucos anos.",
        "O beija-flor é a única ave capaz de voar para trás de forma sustentada.",
        "Estima-se que existam cerca de vinte quatrilhões de formigas na Terra, segundo um estudo de 2022.",
        "Os gatos passam cerca de dois terços da vida dormindo.",
        "A Amazônia abriga uma das maiores biodiversidades do planeta, com milhares de espécies de árvores diferentes.",
        "O bambu é uma gramínea, não uma árvore, e algumas espécies crescem quase um metro em um único dia.",
        "Os golfinhos dormem com metade do cérebro de cada vez, para continuar respirando e atentos.",
    ],
    "design e arte": [
        "A proporção áurea, cerca de 1,618, aparece em muitos estudos de design e arquitetura, embora seu uso em obras antigas às vezes seja exagerado pelas lendas.",
        "A escola Bauhaus, fundada na Alemanha em 1919, uniu arte, artesanato e indústria e influenciou o design de móveis até hoje.",
        "O designer brasileiro Sergio Rodrigues criou a Poltrona Mole em 1957, que ganhou um concurso internacional na Itália em 1961.",
        "A altura de assento mais comum em cadeiras de jantar fica perto de quarenta e cinco centímetros, para mesas de cerca de setenta e cinco.",
        "O azul foi uma das cores mais caras da pintura antiga: o azul ultramarino era feito moendo uma pedra, o lápis-lazúli.",
        "A cadeira Barcelona foi desenhada por Mies van der Rohe e Lilly Reich para a Exposição Internacional de 1929.",
    ],
    "tecnologia": [
        "O primeiro disco rígido comercial, da IBM, em 1956, guardava cerca de cinco milhões de caracteres e pesava perto de uma tonelada.",
        "Os primeiros computadores usavam válvulas e ocupavam salas inteiras; um celular de hoje tem milhões de vezes mais capacidade de processamento.",
        "A palavra 'robô' vem de uma peça de teatro tcheca de 1920 e tem origem numa palavra que significa trabalho forçado.",
        "O código QR foi criado em 1994 por uma empresa japonesa para rastrear peças de automóveis na fábrica.",
        "O mouse de computador foi apresentado ao público em 1968 por Douglas Engelbart, e o primeiro era de madeira.",
    ],
}

MOTIVACIONAIS = [
    "Projeto bom não nasce pronto: nasce na primeira versão e melhora a cada revisão. Continue revisando.",
    "Medir duas vezes e cortar uma vale para a vida também: pensa com calma, depois age com firmeza.",
    "Você não precisa resolver o dia inteiro agora. Resolve a próxima peça, depois a próxima.",
    "Todo móvel bonito começou como uma pilha de tábuas e uma ideia na cabeça de alguém. Hoje essa pessoa é você.",
    "Cansaço é sinal de que você está empurrando alguma coisa para frente. Respira, toma uma água e segue.",
    "Erro no desenho é barato; erro na produção é caro. Errar no projeto faz parte do caminho certo.",
    "Disciplina é fazer bem feito mesmo quando ninguém está olhando. E alguém sempre acaba vendo o resultado.",
    "Um passo de cada vez ainda é andar. Um parafuso de cada vez ainda é montar.",
    "Quem ensina a equipe multiplica o próprio trabalho. O seu esforço de hoje vira a autonomia deles amanhã.",
    "Problema difícil é só problema que ainda não foi dividido em partes menores.",
    "Pausa também é produtividade. Cinco minutos longe da tela podem resolver o que uma hora olhando não resolveu.",
    "O detalhe que ninguém pede é o que faz o cliente lembrar do seu trabalho.",
    "Hoje pode não ser o seu melhor dia, mas ainda pode ser um dia bem feito.",
    "Ferramenta afiada corta melhor. Mente descansada também.",
    "Você já resolveu muita coisa que um dia parecia impossível. Essa também vai.",
    "Constância vence talento que não aparece para trabalhar.",
    "Faça o simples bem feito antes de fazer o complicado.",
    "Uma família te esperando em casa é o melhor motivo para terminar o dia com a sensação de dever cumprido.",
    "Não compare o seu começo com o meio do caminho dos outros.",
    "Se o projeto travou, muda o ângulo de vista. No SolidWorks e na vida, às vezes basta girar a peça.",
    "Respira fundo: quatro segundos puxando o ar, quatro segurando, quatro soltando. Repete três vezes.",
    "O que é feito com cuidado dura. Isso vale para móveis e para relações.",
    "Planejar não é perder tempo; é ganhar tempo depois.",
    "Comemora as pequenas vitórias do dia. Elas são as que constroem as grandes.",
    "Você não está atrasado; você está no seu tempo. Só não pare.",
]


class Frases:
    def __init__(self, db):
        self.db = db

    def _usadas(self, chave):
        v = self.db.kv_get(chave, "")
        return v.split("|") if v else []

    def _marcar(self, chave, idx):
        u = self._usadas(chave)[-60:] + [str(idx)]
        self.db.kv_set(chave, "|".join(u))

    def curiosidade(self, tema=None):
        todas = []
        for t, lista in CURIOSIDADES.items():
            if tema and tema not in t:
                continue
            for i, c in enumerate(lista):
                todas.append((f"{t}:{i}", c))
        if not todas:
            todas = [(f"{t}:{i}", c) for t, lista in CURIOSIDADES.items() for i, c in enumerate(lista)]
        usadas = set(self._usadas("curios_usadas"))
        livres = [x for x in todas if x[0] not in usadas] or todas
        chave, texto = random.choice(livres)
        self._marcar("curios_usadas", chave)
        return texto

    def motivacao(self):
        usadas = set(self._usadas("motiv_usadas"))
        livres = [i for i in range(len(MOTIVACIONAIS)) if str(i) not in usadas] or list(range(len(MOTIVACIONAIS)))
        i = random.choice(livres)
        self._marcar("motiv_usadas", i)
        return MOTIVACIONAIS[i]


def tema_da_pergunta(p):
    p = p.lower()
    for chave, palavras in (("madeira", ("madeira", "marcenaria", "móve", "move")), ("engenharia", ("engenharia", "metal", "aço", "laser", "cnc")),
                            ("ciência", ("ciência", "ciencia", "espaço", "corpo")), ("história", ("história", "historia")),
                            ("natureza", ("natureza", "animal", "bicho", "planta")), ("design", ("design", "arte")),
                            ("tecnologia", ("tecnologia", "computador"))):
        if any(w in p for w in palavras):
            return chave
    return None
