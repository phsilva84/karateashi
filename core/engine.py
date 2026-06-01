import json
from pathlib import Path

# Dicionários de pesos e descrições
PESOS = {
    "A1": 1.0,
    "A2": 2.0,
    "A3": 1.5,
    "A4": 2.5,
    "A5": 3.0,
    "A6": 1.0,
    "A7": 4.0,
    "A8": 2.0,
    "A9": 3.5,
    "A10": 12.0,
    "A11": 1.0,
    "A12": 5.0,
}

DESCRICOES = {
    "A1": "Postura incorreta",
    "A2": "Distância inadequada",
    "A3": "Movimento repetitivo",
    "A4": "Força excessiva",
    "A5": "Pressão mecânica",
    "A6": "Vibração localizada",
    "A7": "Iluminação inadequada",
    "A8": "Ruído excessivo",
    "A9": "Temperatura extrema",
    "A10": "Carga postural estática",
    "A11": "Estresse físico",
    "A12": "Jornada prolongada",
}

def aplicar_teto_a10(valor: float) -> float:
    """Aplica limite máximo de 10 pontos para A10."""
    return min(valor, 10.0)

def calcular_resultados(scores: dict) -> dict:
    """Calcula o escore ponderado e normaliza para base 100."""
    # Aplicar teto em A10
    scores_com_teto = scores.copy()
    if "A10" in scores_com_teto:
        scores_com_teto["A10"] = aplicar_teto_a10(scores_com_teto["A10"])

    # Soma ponderada
    total_ponderado = sum(scores_com_teto[k] * PESOS[k] for k in PESOS)

    # Valor máximo possível (cada fator até 10, exceto A10 já limitado)
    max_possivel = sum(10.0 * w for w in PESOS.values())  # 385.0
    resultado_normalizado = (total_ponderado / max_possivel) * 100.0

    return {
        "total_ponderado": total_ponderado,
        "resultado_base_100": round(resultado_normalizado, 2),
        "detalhes": {k: {"peso": PESOS[k], "descricao": DESCRICOES.get(k, ""), "valor": scores_com_teto[k]} for k in PESOS}
    }

def identificar_tendencias(resultado: float) -> str:
    """Classifica o resultado em faixas de tendência."""
    if resultado < 30:
        return "Baixo risco"
    elif resultado < 60:
        return "Médio risco"
    elif resultado < 85:
        return "Alto risco"
    else:
        return "Risco crítico"

if __name__ == "__main__":
    # Define diretório raiz (pai do diretório core/)
    project_root = Path(__file__).resolve().parent.parent
    print("LOG: Diretório raiz do projeto:", project_root)

    # Caminhos dos arquivos
    input_path = project_root / "data" / "exame-matriz-30-05-26.txt"
    output_path = project_root / "output" / "diagnostico.json"

    # Leitura do arquivo de entrada
    print("LOG: Lendo arquivo de entrada:", input_path)
    with open(input_path, "r", encoding="utf-8") as f:
        linhas = f.readlines()

    # Parse das linhas – espera-se formato "A1=5.5" por linha
    scores = {}
    for linha in linhas:
        linha = linha.strip()
        if not linha or "=" not in linha:
            continue
        chave, valor_str = linha.split("=", 1)
        chave = chave.strip()
        try:
            valor = float(valor_str.strip())
        except ValueError:
            print(f"LOG: Aviso – valor inválido para {chave}: '{valor_str}'")
            continue
        scores[chave] = valor

    print("LOG: Scores extraídos:", scores)

    # Cálculo dos resultados
    resultados = calcular_resultados(scores)
    tendencia = identificar_tendencias(resultados["resultado_base_100"])
    resultados["tendencia"] = tendencia

    print("LOG: Resultado base 100:", resultados["resultado_base_100"])
    print("LOG: Tendência identificada:", tendencia)

    # Garantir que o diretório de saída existe
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Salvar JSON
    print("LOG: Salvando diagnóstico em:", output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print("LOG: Processamento concluído com sucesso.")