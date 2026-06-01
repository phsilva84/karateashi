import pandas as pd
import json
import re
from pathlib import Path

# Dicionários oficiais (Tabela v1.1)
PESOS = {
    'A1': 2, 'A2': 3, 'A3': 1, 'A4': 4, 'A5': 2,
    'A6': 3, 'A7': 1, 'A8': 2, 'A9': 3, 'A10': 5,
    'A11': 2, 'A12': 3
}

DESCRICOES = {
    'A1': 'Dificuldade para caminhar',
    'A2': 'Quedas frequentes',
    'A3': 'Perda de peso',
    'A4': 'Disfunção cognitiva',
    'A5': 'Incontinência urinária',
    'A6': 'Uso de múltiplos medicamentos',
    'A7': 'Déficit visual',
    'A8': 'Déficit auditivo',
    'A9': 'Isolamento social',
    'A10': 'Dependência em AVD',
    'A11': 'Desnutrição',
    'A12': 'Comorbidades múltiplas'
}

def aplicar_teto_a10(valor):
    """Aplica teto máximo de 10 pontos no item A10."""
    return min(valor, 10)

def calcular_resultados(df):
    """Calcula nota base 100, aplica teto no A10, retorna médias e diagnósticos."""
    if df.empty:
        return {'erro': 'DataFrame vazio'}

    # Nota base 100: soma dos pesos dos itens presentes
    df['nota_base'] = 0.0
    for col in PESOS.keys():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            df['nota_base'] += df[col] * PESOS[col]

    # Aplicar teto no A10
    if 'A10' in df.columns:
        df['A10_original'] = df['A10']
        df['A10'] = df['A10'].apply(aplicar_teto_a10)
        # Recalcular nota base com A10 ajustado
        df['nota_com_teto'] = 0.0
        for col in PESOS.keys():
            if col in df.columns:
                df['nota_com_teto'] += df[col] * PESOS[col]

    # Médias, diagnósticos
    resultado = {
        'media_nota_base': df['nota_base'].mean(),
        'media_nota_com_teto': df['nota_com_teto'].mean() if 'nota_com_teto' in df.columns else None,
        'diagnosticos': []
    }

    for col in PESOS.keys():
        if col in df.columns:
            media = df[col].mean()
            desc = DESCRICOES.get(col, '')
            if media > 0.5:
                nivel = 'Alto'
            elif media > 0.2:
                nivel = 'Moderado'
            else:
                nivel = 'Baixo'
            resultado['diagnosticos'].append({
                'item': col,
                'descricao': desc,
                'media': round(media, 2),
                'nivel': nivel
            })

    return resultado

def identificar_tendencias(df):
    """Identifica o erro mais comum (item com maior média)."""
    if df.empty:
        return None
    medias = {}
    for col in PESOS.keys():
        if col in df.columns:
            medias[col] = df[col].mean()
    if not medias:
        return None
    item_mais_comum = max(medias, key=medias.get)
    return {
        'item_mais_comum': item_mais_comum,
        'descricao': DESCRICOES.get(item_mais_comum, ''),
        'media': round(medias[item_mais_comum], 2)
    }

def parse_exame_file(file_path):
    """
    Lê arquivo .txt no formato 'Kihon: cod:1,7'.
    Retorna DataFrame com colunas A1..A12 (0/1) indicando presença de cada código.
    """
    arquivo = Path(file_path)
    if not arquivo.exists():
        raise FileNotFoundError(f'Arquivo não encontrado: {file_path}')

    registros = []
    with open(arquivo, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha or not linha.startswith('Kihon:'):
                continue
            # Extrair parte após 'cod:'
            match = re.search(r'cod:\s*([\d,]+)', linha)
            if not match:
                continue
            cod_str = match.group(1)
            codigos = [int(c.strip()) for c in cod_str.split(',') if c.strip().isdigit()]
            # Mapear códigos para itens A1..A12 (código 1 -> A1, etc.)
            row = {f'A{i}': 0 for i in range(1, 13)}
            for cod in codigos:
                if 1 <= cod <= 12:
                    row[f'A{cod}'] = 1
            registros.append(row)

    if not registros:
        return pd.DataFrame(columns=[f'A{i}' for i in range(1,13)])

    df = pd.DataFrame(registros)
    # Garantir que todas as colunas existam
    for col in [f'A{i}' for i in range(1,13)]:
        if col not in df.columns:
            df[col] = 0
    return df

if __name__ == "__main__":
    # Define raiz do projeto (assume que este script está em core/ e projeto na raiz)
    project_root = Path(__file__).resolve().parent.parent
    print(f"DEBUG: project_root = {project_root}")

    # Caminhos
    input_file = project_root / "data" / "exame-matriz-30-05-26.txt"
    output_dir = project_root / "output"
    output_file = output_dir / "diagnostico.json"

    # Criar diretório de saída se não existir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse do arquivo
    print(f"DEBUG: Lendo arquivo: {input_file}")
    df = parse_exame_file(input_file)
    print(f"DEBUG: DataFrame shape: {df.shape}")
    print(f"DEBUG: Colunas: {list(df.columns)}")

    # Cálculos
    resultado = calcular_resultados(df)
    print(f"DEBUG: Resultado calculado: {json.dumps(resultado, indent=2, ensure_ascii=False)}")

    # Tendências
    tendencia = identificar_tendencias(df)
    print(f"DEBUG: Tendência identificada: {tendencia}")

    # Consolidar
    consolidado = {
        "resultados": resultado,
        "tendencias": tendencia
    }

    # Salvar
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(consolidado, f, indent=2, ensure_ascii=False)
    print(f"DEBUG: Diagnóstico salvo em: {output_file}")