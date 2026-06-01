import os
import json
from pathlib import Path

# Dicionários de pesos e descrições (exemplos - substituir conforme necessário)
PESOS = {
    "criterio_a": 0.4,
    "criterio_b": 0.3,
    "criterio_c": 0.2,
    "criterio_d": 0.1,
}

DESCRICOES = {
    "criterio_a": "Descrição do critério A",
    "criterio_b": "Descrição do critério B",
    "criterio_c": "Descrição do critério C",
    "criterio_d": "Descrição do critério D",
}


def calcular_resultados(dados: list) -> dict:
    """
    Calcula os resultados com base nos dados fornecidos.
    Esta é uma implementação de exemplo que deve ser substituída.
    """
    resultados = {}
    for chave, peso in PESOS.items():
        resultados[chave] = sum(dado.get(chave, 0) * peso for dado in dados)
    return resultados


def identificar_tendencias(resultados: dict) -> list:
    """
    Identifica tendências a partir dos resultados calculados.
    Implementação de exemplo – ajustar conforme necessidade.
    """
    tendencias = []
    for chave, valor in resultados.items():
        if valor > 0.5:
            tendencias.append(f"{chave}: tendência alta ({valor:.2f})")
        else:
            tendencias.append(f"{chave}: tendência baixa ({valor:.2f})")
    return tendencias


if __name__ == "__main__":
    # Cria diretório output se não existir
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    print("[LOG] Diretório 'output' verificado/criado.")

    # Procura pelo arquivo de entrada na raiz do projeto
    # Assume que o script está em core/engine.py, então a raiz é o diretório pai de core/
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    arquivo_entrada = project_root / "exame-matriz-30-05-26.txt"

    if not arquivo_entrada.exists():
        print(f"[ERRO] Arquivo '{arquivo_entrada}' não encontrado.")
        exit(1)

    print(f"[LOG] Arquivo encontrado: {arquivo_entrada}")

    # Lê os dados do arquivo (formato livre – ajuste conforme necessário)
    with open(arquivo_entrada, "r") as f:
        linhas = f.readlines()

    # Converte linhas para uma lista de dicionários (exemplo: CSV simples)
    # Esta conversão é ilustrativa; adapte ao formato real do arquivo
    dados = []
    for linha in linhas:
        partes = linha.strip().split(",")
        if len(partes) >= 4:
            registro = {
                "criterio_a": float(partes[0]),
                "criterio_b": float(partes[1]),
                "criterio_c": float(partes[2]),
                "criterio_d": float(partes[3]),
            }
            dados.append(registro)

    print(f"[LOG] {len(dados)} registros carregados.")

    # Executa o cálculo
    resultados = calcular_resultados(dados)
    print("[LOG] Cálculo realizado.")

    # Identifica tendências
    tendencias = identificar_tendencias(resultados)
    print("[LOG] Tendências identificadas.")

    # Monta o diagnóstico completo
    diagnostico = {
        "resultados": resultados,
        "tendencias": tendencias,
        "descricoes": DESCRICOES,
    }

    # Salva em output/diagnostico.json
    caminho_saida = output_dir / "diagnostico.json"
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(diagnostico, f, ensure_ascii=False, indent=2)

    print(f"[LOG] Diagnóstico salvo em: {caminho_saida}")
    print("[LOG] Execução concluída com sucesso.")