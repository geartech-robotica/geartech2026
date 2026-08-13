#!/usr/bin/env python3
"""
BIBLIOTECA DE NAVEGACAO v8 - EV3 / ev3dev2
Torneio Brasil de Robotica (TBR) - Middle 2026

=====================================================================
CONTROLE DE VERSAO
=====================================================================
v2 (base) - primeira versao completa: segue-linha de 3 estados,
    giroscopio, encoder, ancoragem, esqueleto de missao.

v3 - consolida os ajustes de bancada feitos em cima da v2:
    - LIM_BRANCO: 50 -> 58 (verde oscilava 44-51 com a luz ambiente
      e cruzava o limiar antigo)
    - angulo() criada: inverte o sinal do giroscopio, que conta ao
      contrario do steering do ev3dev2 neste robo (confirmado a mao
      na bancada). Todas as funcoes de giro passaram a usar angulo()
      em vez de giro.angle direto.
    - BIAS_RETO = -3 adicionado: compensa desvio mecanico para a
      direita que o robo tem mesmo com steering=0.
    - centralizar_na_via() passou a ser chamada automaticamente no
      inicio de seguir_linha_por_cm() e seguir_linha_ate_cruzamento()
      (corrigia o "tortinho no comeco" quando o robo nao comecava
      centralizado)
    - medir_distancia_ate_via() adicionada: mede base->via pelo
      encoder em vez de fita metrica
    - limpeza: removido cabecalho de secao duplicado

v4 - medicao da Viagem 1:
    - Medicao 1 (base -> via) testada no tapete: 0cm, sem giro (a
      base fica colada na via, robo ja nasce em cima dela)
    - medir_ate_cruzamento() adicionada: mede via->primeiro cruzamento
      seguindo a linha de verdade (com correcoes) em vez de andar
      cego, e reporta a distancia percorrida pelo encoder

v5 - investigando robo andando de re durante medir_ate_cruzamento():
    - POLARIDADE_ESQ / POLARIDADE_DIR adicionadas, forcando 'normal'
      nos dois motores [causa descartada na v7 - ver abaixo]

v6 - correcao de bug de compatibilidade:
    - testar_steering_parcial() usava f-string, exige Python 3.6+.
      EV3 roda Python 3.5 (Debian Stretch). Trocado por .format().

v7 - tentativa de correcao via polaridade:
    - Removida a atribuicao forcada de polarity da v5 (hipotese:
      sobrescreveu um 'inversed' pre-existente)
    - TESTADO E DESCARTADO: cat .../polarity confirmou 'normal'/'normal'
      ja era o valor real. Nao era isso.

v8 (atual) - causa raiz isolada e corrigida empiricamente:
    - Teste definitivo: motor A e motor D testados INDIVIDUALMENTE,
      via LargeMotor(...).on(15) puro (sem MoveSteering, sem nenhum
      codigo nosso no meio). Os DOIS foram para tras, isolados, cada
      um sozinho. Prova que o problema e do proprio motor/firmware
      reagindo errado a velocidade positiva BAIXA (15) - nao e
      polaridade, nao e steering, nao e logica de segue-linha.
    - Em paralelo, velocidade positiva ALTA (30, no andar_cm) sempre
      foi para frente, confirmado com fita metrica. A inversao parece
      depender da MAGNITUDE da velocidade, no nivel mais baixo da
      biblioteca (Motor.on -> speed_sp). Nao temos explicacao teorica
      completa do motivo (possivel peculiaridade do firmware/driver
      desta imagem antiga de ev3dev), mas o padrao e repetivel.
    - CORRECAO APLICADA: VEL_LINHA (15->-15) e VEL_ANCORAGEM (10->-10)
      negadas. VEL_NAVEGACAO (30, usada no andar_cm) e VEL_GIRO (15,
      mas usada so com steering extremo +-100 dentro do girar_para,
      que e corrigido por giroscopio em malha fechada e portanto
      tolerante a essa inversao) foram deixadas como estavam, por
      terem prova direta de funcionar.
    - PENDENTE DE TESTE: buscar_linha_girando() usa steering extremo
      (+-100) MAS com VEL_ANCORAGEM (agora negativa) e SEM malha
      fechada de giroscopio - diferente do girar_para, pode buscar
      para o lado errado. Testar separadamente antes de confiar nela.
=====================================================================

GEOMETRIA DA VIA (medida no tapete oficial):
    cinza | BRANCO | PRETO | BRANCO | cinza
             2cm      2cm     2cm
           <------- 4cm ------->  (centro a centro)

Os dois sensores ficam a 4cm um do outro, cada um centrado sobre uma
linha branca. Deriva maxima antes da correcao disparar: ~1cm.

LEITURAS CALIBRADAS PELA EQUIPE (medidas no tapete oficial):
    preto 10-15 | cinza escuro 27 | cinza claro 33 | areia 46
    pastel 50   | branco 65
    verde 44-51 -> VARIA COM A LUZ AMBIENTE. Foi o que obrigou a
    subir LIM_BRANCO de 50 para 58. Refazer esta medicao no dia da
    competicao, com a iluminacao do local.

LOGICA DE 3 ESTADOS (por sensor):
    BRANCO -> na linha, tudo certo
    PRETO  -> invadiu a faixa central -> derivou para o lado OPOSTO
    CINZA  -> saiu da via para fora   -> derivou para ESTE lado

    Regra pratica: sensor que ve PRETO -> vira para o MESMO lado.
                   sensor que ve CINZA -> vira para o lado OPOSTO.
    (confirmado pela geometria da via e por teste de bancada)

ANCORAGEM - ATENCAO:
    O Vade Mecum avisa que a organizacao NAO usa mesas com borda, entao
    nao existe parede para encostar. As unicas ancoras validas sao:
      1. Alinhamento manual na base (gabarito / objeto estrategico)
      2. Linhas do tapete detectadas por sensor
      3. Cruzamentos (os dois sensores no preto)
    O tapete ainda pode variar ate 5% - por isso ancora por sensor
    sempre vence odometria pura em trechos longos.
"""

from ev3dev2.motor import MoveSteering, LargeMotor, OUTPUT_A, OUTPUT_D
from ev3dev2.sensor import INPUT_1, INPUT_2, INPUT_3, INPUT_4
from ev3dev2.sensor.lego import ColorSensor, GyroSensor
from ev3dev2.button import Button
from time import sleep, time

# ==================== HARDWARE ====================
# CONFIRMAR via SSH: ls /sys/class/tacho-motor/ e /sys/class/lego-sensor/
PORTA_MOTOR_ESQ = OUTPUT_A
PORTA_MOTOR_DIR = OUTPUT_D
PORTA_SENSOR_ESQ = INPUT_3
PORTA_SENSOR_DIR = INPUT_1
PORTA_GIRO = INPUT_2

robo = MoveSteering(PORTA_MOTOR_ESQ, PORTA_MOTOR_DIR)   #alterado para modelo definitivo
motor_esq = LargeMotor(PORTA_MOTOR_ESQ)
motor_dir = LargeMotor(PORTA_MOTOR_DIR)

sensor_esq = ColorSensor(PORTA_SENSOR_ESQ)
sensor_dir = ColorSensor(PORTA_SENSOR_DIR)
giro = GyroSensor(PORTA_GIRO)
botao = Button()

# ==================== CONSTANTES FISICAS ====================
DIAMETRO_RODA = 5.8                                # cm (pneu 58x28)
CM_POR_GRAU = (3.14159 * DIAMETRO_RODA) / 360.0    # ~0.0506 cm/grau
GRAUS_POR_CM = 1.0 / CM_POR_GRAU                   # ~19.75 graus/cm

# ==================== LIMIARES DE COR ====================
LIM_PRETO = 20      
LIM_BRANCO = 58    



# ==================== VELOCIDADES ====================
VEL_NAVEGACAO = 30
VEL_LINHA = -15
VEL_GIRO = 15        
VEL_ANCORAGEM = -10

# ==================== CONTROLE ====================
CORRECAO_LEVE = 20        # so um sensor acusou desvio
CORRECAO_FORTE = 35       # os dois sensores acusaram (deriva confirmada)
CICLO = 0.005             # 5ms
TOLERANCIA_ANGULO = 2     # graus

# Vies mecanico do robo: com steering=0 ele nao anda perfeitamente reto
# (mesmo desvio observado no andar_cm() simples, sem giroscopio).
# AJUSTAR TESTANDO: rode seguir_linha_por_cm() num trecho reto e veja
# para que lado ele entorta no fim. Se entortar para a DIREITA, o
# motor direito esta "ganhando" -> BIAS_RETO negativo (puxa esquerda
# para compensar). Se entortar para a ESQUERDA, BIAS_RETO positivo.
# Comece com +-3 e ajuste de 1 em 1.
BIAS_RETO = -3


# ==================== ESTADO DOS SENSORES ====================
def estado(sensor):
    """Classifica a leitura em PRETO / CINZA / BRANCO."""
    v = sensor.reflected_light_intensity
    if v < LIM_PRETO:
        return "PRETO"
    if v > LIM_BRANCO:
        return "BRANCO"
    return "CINZA"


def estado_esq():
    return estado(sensor_esq)


def estado_dir():
    return estado(sensor_dir)


def na_via():
    """True se pelo menos um sensor ainda ve a via (branco ou preto)."""
    return estado_esq() != "CINZA" or estado_dir() != "CINZA"


def em_cruzamento():
    return estado_esq() == "PRETO" and estado_dir() == "PRETO"


# ==================== SEGUE-LINHA (3 ESTADOS) ====================
def _steering_segue_linha():
    """Retorna a correcao de steering para o estado atual.
    Negativo = vira para a ESQUERDA. Positivo = vira para a DIREITA."""
    e, d = estado_esq(), estado_dir()

    # --- centralizado ---
    if e == "BRANCO" and d == "BRANCO":
        return BIAS_RETO

    # --- cruzamento: os dois no preto -> segue reto ---
    if e == "PRETO" and d == "PRETO":
        return BIAS_RETO

    # --- deriva confirmada pelos dois sensores ---
    if e == "PRETO" and d == "CINZA":
        return -CORRECAO_FORTE      # derivou p/ direita -> corrige esquerda
    if e == "CINZA" and d == "PRETO":
        return CORRECAO_FORTE       # derivou p/ esquerda -> corrige direita

    # --- so um sensor acusou ---
    if e == "PRETO":                # esq no preto -> vira p/ esquerda
        return -CORRECAO_LEVE
    if d == "PRETO":                # dir no preto -> vira p/ direita
        return CORRECAO_LEVE
    if e == "CINZA":                # esq saiu p/ fora -> corrige direita
        return CORRECAO_LEVE
    if d == "CINZA":                # dir saiu p/ fora -> corrige esquerda
        return -CORRECAO_LEVE

    return 0


def _passo_segue_linha(velocidade=VEL_LINHA):
    robo.on(steering=_steering_segue_linha(), speed=velocidade)


# ==================== GIROSCOPIO ====================
def angulo():
   
        return giro.angle


def calibrar_giro():
   
    robo.off()
    sleep(0.5)
    giro.reset()
    sleep(0.5)
    print("Giro calibrado. Angulo:", angulo())


def girar_para(angulo_alvo, velocidade=VEL_GIRO):
        while True:
        erro = angulo_alvo - angulo()
        if abs(erro) <= TOLERANCIA_ANGULO or botao.any():
            break
        lado = 1 if erro > 0 else -1
        vel = velocidade if abs(erro) > 15 else max(5, velocidade // 2)
        robo.on(steering=100 * lado, speed=vel)
        sleep(CICLO)
    robo.off()


def girar_relativo(graus, velocidade=VEL_GIRO):
    """+ = direita, - = esquerda, a partir da direcao atual."""
    girar_para(angulo() + graus, velocidade)


# ==================== DISTANCIA (ENCODER) ====================
def andar_cm(distancia_cm, velocidade=VEL_NAVEGACAO):
    """Trechos curtos. Negativo = de re."""
    graus = abs(distancia_cm) * GRAUS_POR_CM
    vel = velocidade if distancia_cm > 0 else -velocidade
    robo.on_for_degrees(steering=0, speed=vel, degrees=graus, brake=True)


def andar_cm_reto(distancia_cm, velocidade=VEL_NAVEGACAO):
    """Trechos longos: trava o rumo com o giroscopio enquanto anda.
    USAR ESTA COMO PADRAO - este robo puxa para um lado com steering=0,
    e esta versao corrige isso em tempo real."""
    rumo = angulo()
    graus_alvo = abs(distancia_cm) * GRAUS_POR_CM
    pos0 = abs(motor_esq.position)
    sentido = 1 if distancia_cm > 0 else -1

    while abs(abs(motor_esq.position) - pos0) < graus_alvo:
        if botao.any():
            break
        desvio = angulo() - rumo        # + = derivou para a direita
        correcao = max(-25, min(25, -desvio * 2))   # corrige ao contrario
        robo.on(steering=correcao, speed=sentido * velocidade)
        sleep(CICLO)
    robo.off()


# ==================== PERCURSO POR LINHA ====================
def seguir_linha_por_cm(distancia_cm, velocidade=VEL_LINHA):
    centralizar_na_via()      # evita correcao brusca se nao comecou centralizado
    graus_alvo = distancia_cm * GRAUS_POR_CM
    pos0 = abs(motor_esq.position)
    while abs(abs(motor_esq.position) - pos0) < graus_alvo:
        if botao.any():
            break
        _passo_segue_linha(velocidade)
        sleep(CICLO)
    robo.off()


def seguir_linha_ate_cruzamento(n=1, cm_max=200, velocidade=VEL_LINHA):
    """Segue a via ate passar por N cruzamentos. cm_max e trava de
    seguranca. Retorna quantos cruzamentos realmente contou."""
    centralizar_na_via()      # mesmo motivo: evita correcao brusca inicial
    contador = 0
    graus_max = cm_max * GRAUS_POR_CM
    pos0 = abs(motor_esq.position)
    dentro = False

    while contador < n:
        if botao.any():
            break
        if abs(abs(motor_esq.position) - pos0) > graus_max:
            print("AVISO: limite de", cm_max, "cm sem achar cruzamento.")
            break

        if em_cruzamento():
            if not dentro:              # conta so na borda de entrada
                contador += 1
                dentro = True
        else:
            dentro = False

        _passo_segue_linha(velocidade)
        sleep(CICLO)

    robo.off()
    return contador


# ==================== ANCORAGEM ====================
def alinhar_na_base():
    """Nao existe parede para encostar (regra do TBR). O alinhamento
    inicial e feito na mao, com gabarito/objeto estrategico dentro da
    base - o que a regra permite. Esta funcao so zera as referencias
    de software depois que a equipe posicionou o robo."""
    robo.off()
    sleep(0.5)
    giro.reset()
    motor_esq.position = 0
    sleep(0.3)
    print("Referencias zeradas na base. Angulo:", angulo())


def re_ancorar_na_linha(velocidade=VEL_ANCORAGEM, tempo_max=4.0):
    """Anda ate encontrar a via. MIRE PERPENDICULAR a ela: a via
    inteira te 'pega', um ponto especifico nao. Mata o erro acumulado."""
    inicio = time()
    robo.on(steering=0, speed=velocidade)
    while time() - inicio < tempo_max:
        if estado_esq() != "CINZA" or estado_dir() != "CINZA":
            robo.off()
            return True
        if botao.any():
            break
        sleep(CICLO)
    robo.off()
    print("AVISO: nao encontrou a via na re-ancoragem.")
    return False


def buscar_linha_girando(primeiro_lado=1, tempo_por_lado=1.5):
    """Perdeu a via: gira procurando. Tenta um lado, depois o outro."""
    for lado in (primeiro_lado, -primeiro_lado):
        inicio = time()
        robo.on(steering=100 * lado, speed=VEL_ANCORAGEM)
        while time() - inicio < tempo_por_lado:
            if na_via():
                robo.off()
                return True
            if botao.any():
                robo.off()
                return False
            sleep(CICLO)
    robo.off()
    return False


def centralizar_na_via(tempo_max=3.0):
    """Depois de reencontrar a via, ajusta ate os dois sensores
    ficarem no branco (robo centralizado e pronto para seguir)."""
    inicio = time()
    while time() - inicio < tempo_max:
        if estado_esq() == "BRANCO" and estado_dir() == "BRANCO":
            robo.off()
            return True
        if botao.any():
            break
        _passo_segue_linha(VEL_ANCORAGEM)
        sleep(CICLO)
    robo.off()
    return False


# ==================== FERRAMENTA DE MEDICAO ====================
def medir_ate_cruzamento(distancia_max=200, velocidade=VEL_LINHA):
    """Segue a via de verdade (com todas as correcoes do segue-linha)
    ate encontrar o primeiro cruzamento, medindo a distancia percorrida
    pelo encoder. Posicione o robo JA NA VIA antes de chamar (rode
    medir_distancia_ate_via() antes, se ainda nao estiver nela)."""
    centralizar_na_via()
    pos0 = abs(motor_esq.position)
    graus_max = distancia_max * GRAUS_POR_CM

    while abs(abs(motor_esq.position) - pos0) < graus_max:
        if botao.any():
            break
        if em_cruzamento():
            percorrido = (abs(motor_esq.position) - pos0) / GRAUS_POR_CM
            robo.off()
            print("Cruzamento encontrado apos", round(percorrido, 1), "cm.")
            return percorrido
        _passo_segue_linha(velocidade)
        sleep(CICLO)

    robo.off()
    print("Cruzamento NAO encontrado em", distancia_max, "cm.")
    print("Aumente distancia_max ou confira se ha mesmo um cruzamento nesse trecho.")
    return None


def medir_distancia_ate_via(passo_cm=2, distancia_max=60):
    """Anda em passos curtos ate um sensor encontrar a via, medindo a
    distancia exata pelo encoder - sem depender de fita metrica.

    Posicione o robo na base (alinhado pelo gabarito) ANTES de chamar.
    Se ele passar de distancia_max sem achar, o angulo de saida da
    base provavelmente esta errado - reposicione a mao e teste de novo."""
    percorrido = 0
    while percorrido < distancia_max:
        if botao.any():
            break
        if na_via():
            print("Via encontrada apos", percorrido, "cm.")
            print("esq:", estado_esq(), "| dir:", estado_dir())
            if estado_esq() != "CINZA" and estado_dir() != "CINZA":
                print("Os dois sensores bateram junto -> angulo de saida parece OK.")
            else:
                print("So um sensor bateu -> pode precisar ajustar o angulo de saida.")
            return percorrido
        andar_cm(passo_cm)
        percorrido += passo_cm
    print("Via NAO encontrada em", distancia_max, "cm.")
    print("Provavel causa: angulo de saida da base errado. Reposicione e tente de novo.")
    return None


# ==================== FERRAMENTA DE CALIBRACAO ====================
def testar_steering_parcial(steering=35, segundos=2, velocidade=VEL_LINHA):
    """Recria exatamente a situacao do medir_ate_cruzamento(): um
    steering parcial (nem 0, nem 100) sustentado por alguns segundos.
    Observe as DUAS rodas: alguma gira para tras?

    steering positivo deveria fazer a roda DIREITA girar mais devagar
    (ou a esquerda mais rapido) - nenhuma das duas deveria inverter."""
    print("steering={}, speed={}, por {}s.".format(steering, velocidade, segundos))
    print("Observe: alguma roda gira ao contrario?")
    robo.on(steering=steering, speed=velocidade)
    sleep(segundos)
    robo.off()


def monitorar_sensores():
    """Roda isso com o robo na mao para conferir os limiares em cada
    regiao do tapete. Botao encerra."""
    print("esq / dir  (botao para sair)")
    while not botao.any():
        print(sensor_esq.reflected_light_intensity, estado_esq(), "|",
              sensor_dir.reflected_light_intensity, estado_dir())
        sleep(0.3)


# ==================== ESQUELETO DE MISSAO ====================
def viagem_exemplo():
    """Substituir os valores pelas medidas reais do tapete."""
    alinhar_na_base()

    andar_cm(20)                      # sai da base
    re_ancorar_na_linha()             # encosta na via, erro zerado
    centralizar_na_via()
    seguir_linha_ate_cruzamento(1)    # ate o X perto da base
    girar_para(90)
    seguir_linha_por_cm(30)

    # ... acao da missao ...

    girar_para(-90)
    re_ancorar_na_linha()             # mira LARGO na via para voltar


if __name__ == "__main__":
    print("Posicione o robo na base e NAO MOVA durante a calibracao.")
    calibrar_giro()
    print("Pronto. Use monitorar_sensores() para conferir os limiares.")