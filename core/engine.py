import json
import csv
from pathlib import Path

# Tabela v1.1 - Pesos e descrições
PESOS = {
    'var1': 0.3,
    'var2': 0.5,
    'var3': 0.2,
}

DESCRICOES = {
    'var1': 'Descrição da variável 1',
    'var2': 'Descrição da variável 2',
    'var3': 'Descrição da variável 3',
}

def aplicar_teto_a10(valor: float) -> float:
    """Aplica um teto máximo de 10 ao valor."""
    return min(valor, 10.0)

def calcular_resultados(dados: list) -> list:
    """Processa os dados aplicando pesos e teto, retorna lista de dicionários com resultados."""
    resultados = []
    for linha in dados:
        resultado = {}
        for chave, peso in PESOS.items():
            valor_original = float(linha.get(chave, 0))
            valor_ponderado = valor_original * peso
            valor_limitado = aplicar_teto_a10(valor_ponderado)
            descricao = DESCRICOES.get(chave, 'Descrição não encontrada')
            resultado[chave] = {
                'valor_original': valor_original,
                'valor_ponderado': round(valor_ponderado, 2),
                'valor_limitado': round(valor_limitado, 2),
                'descricao': descricao,
            }
        resultados.append(resultado)
    return resultados

def identificar_tendencias(resultados: list) -> dict:
    """Identifica tendências com base nos resultados (exemplo simples)."""
    if len(resultados) < 2:
        return {'tendencia': 'insuficiente'}
    ultimo = resultados[-1]
    penultimo = resultados[-2] if len(resultados) >= 2 else {}
    tendencias = {}
    for chave in PESOS:
        if chave in ultimo and chave in penultimo:
            diff = ultimo[chave]['valor_limitado'] - penultimo[chave]['valor_limitado']
            if diff > 0.5:
                tendencias[chave] = 'aumento'
            elif diff < -0.5:
                tendencias[chave] = 'queda'
            else:
                tendencias[chave] = 'estável'
        else:
            tendencias[chave] = 'indeterminado'
    return {'tendencias': tendencias}

if __name__ == "__main__":
    print("=== INÍCIO ===")
    
    # Define diretório raiz do projeto (pai de core/)
    project_root = Path(__file__).resolve().parent.parent
    print(f"project_root: {project_root}")
    
    # Caminho do arquivo de entrada
    input_file = project_root / "data" / "exame-matriz-30-05-26.txt"
    print(f"Arquivo de entrada: {input_file}")
    
    # Leitura do arquivo
    dados = []
    with open(input_file, 'r', encoding='utf-8') as f:
        primeira_linha = f.readline().strip()
        # Detecta separador: vírgula ou tabulação
        if ',' in primeira_linha:
            separador = ','
        elif '\t' in primeira_linha:
            separador = '\t'
        else:
            separador = ','  # fallback
        print(f"Separador detectado: {repr(separador)}")
        f.seek(0)  # volta ao início
        reader = csv.DictReader(f, delimiter=separador)
        for row in reader:
            dados.append(row)
    print(f"Total de linhas lidas: {len(dados)}")
    
    # Processamento
    print("Calculando resultados...")
    resultados = calcular_resultados(dados)
    print(f"Resultados calculados para {len(resultados)} registros")
    
    print("Identificando tendências...")
    tendencias = identificar_tendencias(resultados)
    print(f"Tendências: {tendencias}")
    
    # Saída
    output_dir = project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "diagnostico.json"
    print(f"Salvando em: {output_file}")
    
    diagnostico = {
        'resultados': resultados,
        'tendencias': tendencias,
    }
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(diagnostico, f, indent=2, ensure_ascii=False)
    
    print("=== FIM ===")