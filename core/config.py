from pathlib import Path

# Diretórios
DATA_DIR = Path('data')
PROCESSED_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = Path('output')

# Categorias Base
CATEGORIES = ['Kihon', 'Kata', 'Bunkai', 'Kumite']

# Tabela de Pesos v1.1 (A10 corrigido para 2.5)
WEIGHT_TABLE = {
    'A1': 1.0, 'A2': 1.0, 'A3': 1.0, 'A4': 0.5, 'A5': 2.0, 'A6': 1.0,
    'A7': 1.0, 'A8': 0.5, 'A9': 1.0, 'A10': 2.5, 'A11': 1.0, 'A12': 0.5,
}

# Significado dos Códigos
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
    'A10': {'descricao': 'Falta de controle no ataque / excesso de força', 'recomendacao': 'Trabalhar controle e segurança no kumite'},
    'A11': {'descricao': 'Distância inadequada', 'recomendacao': 'Treinar distância correta (ma-ai)'},
    'A12': {'descricao': 'Tensão / respiração inadequada', 'recomendacao': 'Trabalhar relaxamento e respiração'}
}

# Elogios (Inverso dos códigos)
PONTOS_POSITIVOS = {
    'A1': 'Alunos com bom trabalho de bases e posicionamento de pés',
    'A2': 'Alunos com boa execução técnica e forma correta',
    'A3': 'Alunos com boa transferência de peso e potência',
    'A4': 'Alunos com boa respiração sincronizada e vocalização',
    'A5': 'Alunos com excelente memorização e execução de kata',
    'A6': 'Alunos com excelente concentração e foco visual',
    'A7': 'Alunos com excelente estabilidade e equilíbrio',
    'A8': 'Alunos com excelente sincronização e ritmo',
    'A9': 'Alunos com excelente defesa e contra-ataques',
    'A10': 'Alunos com excelente controle e segurança no kumite',
    'A11': 'Alunos com excelente ma-ai (distância correta)',
    'A12': 'Alunos com excelente relaxamento e respiração'
}