from pathlib import Path

# ============================================================================
# DIRETÓRIOS E CONFIGURAÇÕES DE INFRAESTRUTURA
# ============================================================================
DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

# Tabela de Pesos v1.1 (A10 corrigido para 2.5)
WEIGHT_TABLE = {
    'A1': 1.0, 'A2': 1.0, 'A3': 1.0, 'A4': 0.5, 'A5': 2.0, 'A6': 1.0,
    'A7': 1.0, 'A8': 0.5, 'A9': 1.0, 'A10': 2.5, 'A11': 1.0, 'A12': 0.5,
}

# ============================================================================
# RECOMENDAÇÕES PEDAGÓGICAS v1.3.2 (EQUILÍBRIO DIDÁTICO)
# ============================================================================
RECOMENDACOES = {
    'A1': {
        'descricao': 'Base Incorreta',
        'severidade': '🔴 CRÍTICO',
        'recomendacao': 'Corrigir o posicionamento dos pés e a distribuição de peso nas bases.',
        'threshold': 0.30
    },
    'A2': {
        'descricao': 'Execução Técnica Incorreta',
        'severidade': '🟠 IMPORTANTE',
        'recomendacao': 'Revisar a trajetória dos movimentos e a rotação de quadril e punho.',
        'threshold': 0.30
    },
    'A3': {
        'descricao': 'Movimento sem Carga/Peso',
        'severidade': '🟡 ATENÇÃO',
        'recomendacao': 'Finalizar o golpe com firmeza, contraindo o abdômen para gerar potência.',
        'threshold': 0.30
    },
    'A4': {
        'descricao': 'Ausência de Kiai',
        'severidade': '🟢 OBSERVAÇÃO',
        'recomendacao': 'Sincronizar a saída do ar com o final do golpe para canalizar a energia.',
        'threshold': 0.30
    },
    'A5': {
        'descricao': 'Embusen Incorreto',
        'severidade': '🟠 IMPORTANTE',
        'recomendacao': 'Respeitar o trajeto correto do Kata (Embusen) e retornar ao ponto de início.',
        'threshold': 0.30
    },
    'A6': {
        'descricao': 'Falta de Foco',
        'severidade': '🟡 ATENÇÃO',
        'recomendacao': 'Manter o foco visual e a intenção no alvo durante toda a técnica.',
        'threshold': 0.30
    },
    'A7': {
        'descricao': 'Perda de Equilíbrio',
        'severidade': '🔴 CRÍTICO',
        'recomendacao': 'Flexionar mais os joelhos para ganhar estabilidade e evitar balanços.',
        'threshold': 0.30
    },
    'A8': {
        'descricao': 'Falta de Ritmo/Cadência',
        'severidade': '🟡 ATENÇÃO',
        'recomendacao': 'Ajustar a velocidade dos movimentos, respeitando o tempo correto do Kata.',
        'threshold': 0.30
    },
    'A9': {
        'descricao': 'Defesa Incompleta',
        'severidade': '🟠 IMPORTANTE',
        'recomendacao': 'Garantir que o bloqueio cubra a área de ataque e prepare o contra-ataque.',
        'threshold': 0.30
    },
    'A10': {
        'descricao': 'Falta de Controle',
        'severidade': '🔴 CRÍTICO',
        'recomendacao': 'Controlar a distância e a potência do impacto para garantir a segurança do parceiro.',
        'threshold': 0.30
    },
    'A11': {
        'descricao': 'Distância Inadequada',
        'severidade': '🟡 ATENÇÃO',
        'recomendacao': 'Ajustar o posicionamento para garantir que o golpe alcance o alvo com eficiência.',
        'threshold': 0.30
    },
    'A12': {
        'descricao': 'Tensão/Respiração Inadequada',
        'severidade': '🟢 OBSERVAÇÃO',
        'recomendacao': 'Relaxar os ombros e manter a respiração abdominal fluida e constante.',
        'threshold': 0.30
    }
}

# Elogios para o Dojo (Força Relativa)
PONTOS_POSITIVOS = {
    'A1': 'Domínio técnico das bases e posicionamento',
    'A2': 'Precisão na trajetória técnica e rotação',
    'A3': 'Excelente aplicação de firmeza e potência muscular',
    'A4': 'Kiai expressivo e respiração sincronizada',
    'A5': 'Perfeita execução do Embusen (trajeto do Kata)',
    'A6': 'Foco visual e intenção impecáveis',
    'A7': 'Estabilidade e controle de centro de gravidade',
    'A8': 'Ritmo e cadência de execução harmoniosos',
    'A9': 'Bloqueios eficientes com cobertura total',
    'A10': 'Excelente controle de impacto e segurança',
    'A11': 'Noção de distância muito bem aplicada',
    'A12': 'Fluidez respiratória e relaxamento muscular'
}