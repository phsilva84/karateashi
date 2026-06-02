from pathlib import Path

# Diretórios
DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

# Categorias
CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

# Tabela v1.1 (A10 = 2.5)
WEIGHT_TABLE = {
    'A1': 1.0, 'A2': 1.0, 'A3': 1.0, 'A4': 0.5, 'A5': 2.0, 'A6': 1.0,
    'A7': 1.0, 'A8': 0.5, 'A9': 1.0, 'A10': 2.5, 'A11': 1.0, 'A12': 0.5,
}

# Significados para Relatório Pedagógico
CODE_MEANINGS = {
    'A1': {'descricao': 'Base incorreta', 'recomendacao': 'Trabalhar posicionamento de pés e distribuição de peso'},
    'A2': {'descricao': 'Execução técnica incorreta', 'recomendacao': 'Revisar forma correta com instrutor'},
    'A3': {'descricao': 'Movimento sem carga/peso', 'recomendacao': 'Aumentar transferência de peso'},
    'A4': {'descricao': 'Ausência de kiai', 'recomendacao': 'Trabalhar respiração sincronizada'},
    'A5': {'descricao': 'Embusen incorreto', 'recomendacao': 'Memorizar padrão correto de deslocamento'},
    'A6': {'descricao': 'Falta de foco / olhar incorreto', 'recomendacao': 'Treinar concentração visual'},
    'A7': {'descricao': 'Perda de equilíbrio', 'recomendacao': 'Fortalecer estabilidade e core'},
    'A8': {'descricao': 'Falta de ritmo', 'recomendacao': 'Sincronizar movimentos com ritmo'},
    'A9': {'descricao': 'Defesa incompleta', 'recomendacao': 'Treinar defesa ativa e contra-ataques'},
    'A10': {'descricao': 'Falta de controle no ataque', 'recomendacao': 'Trabalhar controle e segurança no kumite'},
    'A11': {'descricao': 'Distância inadequada', 'recomendacao': 'Treinar distância correta (ma-ai)'},
    'A12': {'descricao': 'Tensão / respiração inadequada', 'recomendacao': 'Trabalhar relaxamento e respiração'}
}

# Elogios (Pontos Positivos)
PONTOS_POSITIVOS = {
    'A1': 'Excelente trabalho de bases e posicionamento de pés',
    'A2': 'Ótima execução técnica e forma correta',
    'A3': 'Boa transferência de peso e potência nos golpes',
    'A4': 'Kiai forte e respiração sincronizada',
    'A5': 'Domínio total do Embusen (trajeto do Kata)',
    'A6': 'Foco e olhar impecáveis durante as técnicas',
    'A7': 'Estabilidade e equilíbrio mantidos em todos os níveis',
    'A8': 'Ritmo e cadência de execução excelentes',
    'A9': 'Defesa ativa e contra-ataques precisos',
    'A10': 'Controle absoluto de força e segurança com o parceiro',
    'A11': 'Ma-ai (distância) correta em todas as situações',
    'A12': 'Relaxamento e respiração adequados'
}