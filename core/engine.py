import pandas as pd

# Dicionário de descontos da Tabela v1.1 (A1-A12) – valores em pontos perdidos
PESOS = {
    'A1': 1.0,
    'A2': 2.0,
    'A3': 1.5,
    'A4': 2.5,
    'A5': 3.0,
    'A6': 1.0,
    'A7': 4.0,
    'A8': 2.0,
    'A9': 3.5,
    'A10': 12.0,  # será limitado a -10.0 (na prática desconto ≤10)
    'A11': 1.0,
    'A12': 5.0
}

# Dicionário de descrições das falhas técnicas
DESCRICOES = {
    'A1': 'Postura incorreta',
    'A2': 'Distância inadequada',
    'A3': 'Timing errado',
    'A4': 'Falta de concentração',
    'A5': 'Execução incompleta',
    'A6': 'Deslocamento incorreto',
    'A7': 'Ritmo quebrado',
    'A8': 'Respiração inadequada',
    'A9': 'Finalização ausente',
    'A10': 'Excesso de força no kumite',
    'A11': 'Orientação errada',
    'A12': 'Falta de continuidade'
}

def aplicar_teto_a10(valor):
    """Limita o desconto de A10 a no máximo 10 pontos (teto de -10.0)."""
    return min(valor, 10.0)  # desconto não pode ultrapassar 10

def calcular_resultados(df):
    """
    Recebe um DataFrame com colunas 'Aluno' e códigos A1-A12.
    Calcula nota final (base 100), aplica teto de -10.0 para A10 no kumite.
    Retorna um DataFrame com médias e uma lista de diagnósticos técnicos.
    """
    # Faz uma cópia para não modificar original
    df_trabalho = df.copy()
    alunos = df_trabalho['Aluno'].tolist()

    # Lista dos códigos de falha
    codigos = [f'A{i}' for i in range(1, 13)]

    # Calcula a penalidade total por aluno, aplicando o teto no A10
    penalidade_total = []
    diagnosticos = []
    for _, row in df_trabalho.iterrows():
        soma = 0.0
        falhas = []
        for cod in codigos:
            valor = row.get(cod, 0)  # assume 0 se coluna ausente
            peso = PESOS.get(cod, 0)
            if cod == 'A10':
                # aplica teto no peso
                peso_aplicado = aplicar_teto_a10(peso)
            else:
                peso_aplicado = peso
            soma += valor * peso_aplicado
            if valor != 0:  # falha presente
                falhas.append(cod)
        penalidade_total.append(soma)
        diagnosticos.append(falhas)

    # Nota final = 100 - penalidade (não negativa)
    notas_finais = [max(100 - p, 0) for p in penalidade_total]

    # Monta DataFrame de resultados por aluno
    df_resultados = pd.DataFrame({
        'Aluno': alunos,
        'NotaFinal': notas_finais,
        'Falhas': diagnosticos
    })

    # Cálculo das médias
    media_final = df_resultados['NotaFinal'].mean()

    # Média de ocorrência de cada código (frequência relativa)
    medias_codigos = {cod: df_trabalho[cod].mean() for cod in codigos}

    # Cria DataFrame de médias
    medias_dict = {
        'Metrica': ['Media_Final'] + codigos,
        'Valor': [media_final] + [medias_codigos[cod] for cod in codigos]
    }
    df_medias = pd.DataFrame(medias_dict)

    return df_medias, diagnosticos

def identificar_tendencias(df):
    """
    Identifica o erro mais comum do grupo (código com maior soma de ocorrências).
    """
    codigos = [f'A{i}' for i in range(1, 13)]
    contagens = {cod: df[cod].sum() for cod in codigos}
    mais_comum = max(contagens, key=contagens.get)
    return mais_comum, DESCRICOES.get(mais_comum, 'Descrição não encontrada')