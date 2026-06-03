from pathlib import Path

DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

WEIGHT_TABLE = {
    'A1': 1.0, 'A2': 1.0, 'A3': 1.0, 'A4': 0.5, 'A5': 2.0, 'A6': 1.0,
    'A7': 1.0, 'A8': 0.5, 'A9': 1.0, 'A10': 2.5, 'A11': 1.0, 'A12': 0.5,
}

RECOMENDACOES = {
    'A1': {'descricao': 'Base Incorreta', 'severidade': '🔴 CRÍTICO', 'recomendacao': 'Priorizar exercícios de fixação de base e distribuição de peso nas próximas aulas.', 'threshold': 0.30},
    'A2': {'descricao': 'Execução Técnica Incorreta', 'severidade': '🟠 IMPORTANTE', 'recomendacao': 'Dedicar tempo para correção coletiva de trajetórias e rotação de quadril e punho.', 'threshold': 0.30},
    'A3': {'descricao': 'Movimento sem Carga/Peso', 'severidade': '🟡 ATENÇÃO', 'recomendacao': 'Trabalhar a explosão final e a ativação do abdômen em exercícios de grupo.', 'threshold': 0.30},
    'A4': {'descricao': 'Ausência de Kiai', 'severidade': '🟢 OBSERVAÇÃO', 'recomendacao': 'Cobrar maior intensidade na expiração e no uso do Kiai durante as técnicas.', 'threshold': 0.30},
    'A5': {'descricao': 'Embusen Incorreto', 'severidade': '🟠 IMPORTANTE', 'recomendacao': 'Revisar o trajeto dos Katas (Embusen) no tatame, focando no ponto de retorno.', 'threshold': 0.30},
    'A6': {'descricao': 'Falta de Foco', 'severidade': '🟡 ATENÇÃO', 'recomendacao': 'Implementar treinos de atenção visual e manutenção do olhar fixo no alvo.', 'threshold': 0.30},
    'A7': {'descricao': 'Perda de Equilíbrio', 'severidade': '🔴 CRÍTICO', 'recomendacao': 'Focar em exercícios de fortalecimento de pernas e estabilidade nas transições.', 'threshold': 0.30},
    'A8': {'descricao': 'Falta de Ritmo/Cadência', 'severidade': '🟡 ATENÇÃO', 'recomendacao': 'Treinar a cadência do Kata, alternando entre velocidade e controle de tempo.', 'threshold': 0.30},
    'A9': {'descricao': 'Defesa Incompleta', 'severidade': '🟠 IMPORTANTE', 'recomendacao': 'Reforçar a importância da cobertura total da área de ataque e preparo do contra-ataque.', 'threshold': 0.30},
    'A10': {'descricao': 'Falta de Controle', 'severidade': '🔴 CRÍTICO', 'recomendacao': 'Monitorar rigorosamente a potência dos golpes e a segurança entre os parceiros.', 'threshold': 0.30},
    'A11': {'descricao': 'Distância Inadequada', 'severidade': '🟡 ATENÇÃO', 'recomendacao': 'Praticar a noção de distância relativa para garantir a eficiência do alcance dos golpes.', 'threshold': 0.30},
    'A12': {'descricao': 'Rigidez Muscular / Respiração Bloqueada', 'severidade': '🟢 OBSERVAÇÃO', 'recomendacao': 'Introduzir rotinas de soltura de ombros e exercícios de respiração diafragmática.', 'threshold': 0.30}
}

PONTOS_POSITIVOS = {
    'A1': 'Excelente domínio das bases e estabilidade postural',
    'A2': 'Alta precisão técnica e fluidez nos movimentos',
    'A3': 'Forte aplicação de potência e contração muscular',
    'A4': 'Kiai vigoroso e sincronia respiratória exemplar',
    'A5': 'Perfeita orientação espacial e respeito ao Embusen',
    'A6': 'Foco visual e concentração inabaláveis durante a execução',
    'A7': 'Equilíbrio sólido e controle total do centro de gravidade',
    'A8': 'Ritmo cadenciado e excelente controle de tempo/pausa',
    'A9': 'Defesas eficientes com cobertura total da área de ataque',
    'A10': 'Controle de impacto exemplar, garantindo a segurança mútua',
    'A11': 'Noção de distância e alcance muito bem aplicados no Kumite',
    'A12': 'Movimentação relaxada com respiração abdominal fluida'
}