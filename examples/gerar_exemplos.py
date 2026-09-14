"""examples/gerar_exemplos.py — Gera 1 exemplo de cada relatório (Fase 05).

Lê os dados reais de teste (data/dados_avaliadores.txt) e simula a saída do
motor da Fase 01 (resultado por aluno) para alimentar as 3 camadas:

  Camada 1: Relatório Individual (Murilo, faixa branca, 3 avaliadores)
  Camada 2: Consolidado do Dojo + Tendências (faixa branca inteira)
  Camada 3: Master Multi-Dojo (Dojo A = branca, Dojo B = amarela)

Simulação documentada (apenas para o exemplo — o motor da Fase 01 é a fonte
de verdade em produção):
  - fc (frequência) = soma das marcações do código no quesito entre avaliadores
  - detalhes contém TODOS os critérios (fc 0 quando ausente) — necessário
    para o elogio transversal
  - nota_quesito = max(0, 25 - soma dos descontos A1-A12); A10 presente => teto 10
  - nota_final = soma das 4 categorias; APROVADO >= 70, senão RECUPERACAO

Uso: python examples/gerar_exemplos.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.relatorios import (
    CODIGO_CHAVE,
    NOME_CRITERIO,
    carregar_json,
    consolidar_dojo,
    formatar_consolidado_dojo,
    relatorio_individual,
    relatorio_master,
    relatorio_tendencias,
)

RAIZ = Path(__file__).resolve().parents[1]

REGRAS = {
    "elogios": {
        "criterio_transversal_min_quesitos": 2,
        "destaque_geral_min": 85.0,
    },
}

# Tabela de descontos A1-A12 (Fase 00/01) — usada só na simulação de nota.
PESOS_DESCONTO = {
    "A1": 1.0, "A2": 1.0, "A3": 1.0, "A4": 0.5, "A5": 2.0, "A6": 1.0,
    "A7": 1.0, "A8": 0.5, "A9": 1.0, "A10": 2.5, "A11": 1.0, "A12": 0.5,
}
TETO_A10 = 10.0
NOTA_APROVACAO = 70.0
QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

def parse_exame(caminho: Path) -> dict:
    """Parse do formato exame-*.txt -> {avaliador: {faixa: {aluno: {quesito: [codigos]}}}}"""
    dados = {}
    avaliador = faixa = aluno = None
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        m = re.match(r"Avaliador (\d+)", linha)
        if m:
            avaliador = int(m.group(1))
            dados.setdefault(avaliador, {})
            faixa = aluno = None
            continue
        m = re.match(r"Faixa (.+):", linha)
        if m:
            faixa = m.group(1).strip()
            dados[avaliador].setdefault(faixa, {})
            aluno = None
            continue
        m = re.match(r"Nome do aluno:\s*(.*)", linha)
        if m:
            aluno = m.group(1).strip()
            dados[avaliador][faixa].setdefault(aluno, {})
            continue
        m = re.match(r"(Kihon|Kata|Bunkai|Kumite):\s*cod:(.*)", linha)
        if m and aluno:
            quesito = m.group(1).lower()
            codigos = [c.strip() for c in m.group(2).split(",") if c.strip()]
            dados[avaliador][faixa][aluno][quesito] = codigos
    return dados

def montar_resultado(aluno: str, faixa: str, por_avaliador: dict) -> dict:
    """Converte marcações por avaliador em um resultado no formato do motor."""
    n_av = len(por_avaliador)
    quesitos = {}
    for quesito in QUESITOS:
        detalhes = {}
        for chave in NOME_CRITERIO:
            detalhes[chave] = {"fc": 0.0, "marcacoes": [0] * n_av, "nome": NOME_CRITERIO[chave]}
        desconto = 0.0
        a10_avaliadores = []
        for av, marcacoes in por_avaliador.items():
            for codigo in marcacoes.get(quesito, []):
                chave = CODIGO_CHAVE.get(codigo)
                if not chave:
                    continue
                detalhes[chave]["marcacoes"][av - 1] += 1
                desconto += PESOS_DESCONTO.get(codigo, 0.0)
                if codigo == "A10":
                    a10_avaliadores.append(av)
        for det in detalhes.values():
            det["fc"] = float(sum(det["marcacoes"]))
        nota = max(0.0, 25.0 - desconto)
        if a10_avaliadores:
            nota = min(nota, TETO_A10)
        alerta = ("ALERTA_ETICO" if quesito in ("bunkai", "kumite")
                  and a10_avaliadores and len(a10_avaliadores) < n_av else None)
        quesitos[quesito] = {"alerta": alerta, "nota": nota, "detalhes": detalhes}
    nota_final = round(sum(q["nota"] for q in quesitos.values()), 1)
    status = "APROVADO" if nota_final >= NOTA_APROVACAO else "RECUPERACAO"
    return {"aluno": aluno, "faixa": faixa, "nota_final": nota_final,
            "status": status, "quesitos": quesitos}

def alunos_da_faixa(dados: dict, faixa: str) -> list[dict]:
    """Todos os alunos de uma faixa, com marcações dos 3 avaliadores."""
    nomes = set()
    for av in dados:
        nomes.update(dados[av].get(faixa, {}).keys())
    alunos = []
    for nome in sorted(nomes):
        por_av = {av: dados[av].get(faixa, {}).get(nome, {}) for av in sorted(dados)}
        alunos.append(montar_resultado(nome, faixa, por_av))
    return alunos

def main() -> None:
    recomendacoes = carregar_json(RAIZ / "config" / "recomendacoes.json")
    dados = parse_exame(RAIZ / "data" / "dados_avaliadores.txt")

    # --- Camada 1: Relatório Individual ---
    aluno_exemplo = "Murilo Magalhães Souza Romualdo"
    por_av = {av: dados[av]["Branca"][aluno_exemplo] for av in sorted(dados)}
    resultado = montar_resultado(aluno_exemplo, "Branca", por_av)
    print("=" * 60)
    print("CAMADA 1 — RELATORIO INDIVIDUAL")
    print("=" * 60)
    print(relatorio_individual(resultado, REGRAS, recomendacoes, {"nome": aluno_exemplo}))
    print()

    # --- Camada 2: Consolidado do Dojo + Tendências ---
    alunos_branca = alunos_da_faixa(dados, "Branca")
    consolidado = consolidar_dojo(alunos_branca, REGRAS)
    print("=" * 60)
    print("CAMADA 2 — CONSOLIDADO DO DOJO (faixa branca)")
    print("=" * 60)
    print(formatar_consolidado_dojo(consolidado))
    print()
    print("=" * 60)
    print("CAMADA 2 — TENDENCIAS (faixa branca)")
    print("=" * 60)
    print(relatorio_tendencias(alunos_branca, recomendacoes))
    print()

    # --- Camada 3: Master Multi-Dojo ---
    alunos_amarela = alunos_da_faixa(dados, "Amarela")
    dojo_a = {"dojo_id": "DOJO-KARATE-ASHI", "alunos": alunos_branca}
    dojo_b = {"dojo_id": "DOJO-SATELITE", "alunos": alunos_amarela}
    print("=" * 60)
    print("CAMADA 3 — MASTER MULTI-DOJO")
    print("=" * 60)
    print(relatorio_master([dojo_a, dojo_b], REGRAS, recomendacoes))

if __name__ == "__main__":
    main()