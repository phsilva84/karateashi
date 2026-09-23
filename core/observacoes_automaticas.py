#!/usr/bin/env python3
"""core/observacoes_automaticas.py — Gera observações pedagógicas automáticas.

Este módulo transforma as frequências (1-5) lidas pelo omr_reader em
observações pedagógicas concretas, baseadas em regras. Ele COMPLEMENTA as
observações manuais (bolhas BOM!/A MELHORAR) com dados objetivos derivados
das marcações dos avaliadores.

Fluxo:
  omr_reader (frequências) → observacoes_automaticas (regras) → relatório

Regras implementadas:
  1. TRANSVERSAL  — mesmo critério com frequência alta (>= limiar) em 2+ quesitos.
  2. CONCENTRADA  — critério com frequência máxima (>= limiar) em um único quesito.
  3. RANKING      — critério com maior soma de frequências entre todos os quesitos.
  4. PERCENTUAL   — percentual de quesitos em que o critério foi marcado.

Limiares configuráveis em config/regras_gerais.json → "observacoes_automaticas".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import QUESITOS, carregar_json

# Nomes dos critérios por quesito — FALLBACK (fonte única real: config/faixas).
# Usado apenas se config/faixas/<faixa>.json não estiver disponível.
CRITERIOS_FALLBACK = {
    "kihon": ["Base Incorreta", "Execucao Tecnica Incorreta", "Movimento sem Carga",
              "Falta de Foco", "Perda de Equilibrio", "Ausencia de Kiai"],
    "kata": ["Embusen Incorreto", "Base Incorreta", "Falta de Ritmo", "Ausencia de Kiai",
             "Execucao Tecnica Incorreta", "Movimento sem Carga", "Falta de Foco",
             "Perda de Equilibrio"],
    "bunkai": ["Base Incorreta", "Ausencia de Kiai", "Execucao Tecnica Incorreta",
               "Movimento sem Carga", "Falta de Foco", "Perda de Equilibrio",
               "Distancia Inadequada", "Falta de Controle"],
    "kumite": ["Movimento sem Carga", "Falta de Foco", "Perda de Equilibrio",
               "Ausencia de Kiai", "Distancia Inadequada", "Falta de Combatividade",
               "Falta de Controle"],
}

# Limiares padrão (usados se config/regras_gerais.json não tiver o nó).
DEFAULT_LIMIARES = {
    "transversal_min_frequencia": 3,   # frequência mínima p/ contar como "alta"
    "transversal_min_quesitos": 2,     # mínimo de quesitos p/ ser transversal
    "concentrada_min_frequencia": 4,   # frequência mínima p/ ser "concentrada"
    "ranking_min_soma": 6,             # soma mínima p/ entrar no ranking
    "percentual_min": 0.50,            # % mínima de quesitos p/ gerar observação
    "max_observacoes": 3,              # limite de observações por aluno
}


def _carregar_limiares(base_cfg: Path | None) -> dict:
    """Carrega os limiares de config/regras_gerais.json (com fallback padrão)."""
    limiares = dict(DEFAULT_LIMIARES)
    if base_cfg is None:
        return limiares
    caminho = base_cfg / "regras_gerais.json"
    if not caminho.exists():
        return limiares
    try:
        dados = carregar_json(caminho)
        bloco = dados.get("observacoes_automaticas", {})
        if isinstance(bloco, dict):
            limiares.update({k: v for k, v in bloco.items() if k in limiares})
    except Exception:  # noqa: BLE001 — config inválida não quebra o fluxo
        pass
    return limiares


def _carregar_nomes_criterios(base_cfg: Path | None, faixa: str) -> dict:
    """Carrega os nomes dos critérios de config/faixas/<faixa>.json.

    Retorna {quesito: [nomes...]}. Fallback: CRITERIOS_FALLBACK.
    """
    if base_cfg is not None:
        caminho = base_cfg / "faixas" / f"{faixa.lower()}.json"
        if caminho.exists():
            try:
                dados = carregar_json(caminho)
                quesitos = dados.get("quesitos", {})
                nomes = {}
                for q in QUESITOS:
                    bloco = quesitos.get(q, {})
                    lista = bloco.get("criterios", []) if isinstance(bloco, dict) else []
                    nomes[q] = [c["nome"] if isinstance(c, dict) else str(c)
                                for c in lista]
                if all(nomes.get(q) for q in QUESITOS):
                    return nomes
            except Exception:  # noqa: BLE001
                pass
    return CRITERIOS_FALLBACK


def _nome_criterio(nomes: dict, quesito: str, indice: int) -> str:
    """Devolve o nome do critério pelo índice (1-based)."""
    lista = nomes.get(quesito, [])
    if 1 <= indice <= len(lista):
        return lista[indice - 1]
    return f"Critério {indice}"


def _frequencias_por_criterio(avaliacoes: dict) -> dict:
    """Normaliza as avaliações em {quesito: {indice: frequencia}}.

    Aceita tanto o formato do omr_reader (frequencias como dict de str)
    quanto um dict simples {indice: frequencia}.
    """
    resultado: dict[str, dict[int, int]] = {}
    for q in QUESITOS:
        bloco = avaliacoes.get(q, {})
        freqs = bloco.get("frequencias", bloco) if isinstance(bloco, dict) else {}
        resultado[q] = {}
        for k, v in freqs.items():
            try:
                resultado[q][int(k)] = int(v)
            except (ValueError, TypeError):
                continue
    return resultado


def _regra_transversal(freqs: dict, nomes: dict, lim: dict) -> list[dict]:
    """Regra 1: mesmo critério com frequência alta em 2+ quesitos."""
    # Agrupa por nome de critério: {nome: [(quesito, frequencia), ...]}
    por_nome: dict[str, list[tuple[str, int]]] = {}
    for q in QUESITOS:
        for indice, freq in freqs[q].items():
            if freq < lim["transversal_min_frequencia"]:
                continue
            nome = _nome_criterio(nomes, q, indice)
            por_nome.setdefault(nome, []).append((q, freq))
    observacoes = []
    for nome, ocorrencias in por_nome.items():
        if len(ocorrencias) >= lim["transversal_min_quesitos"]:
            quesitos = [q for q, _ in ocorrencias]
            frequencias = [f for _, f in ocorrencias]
            observacoes.append({
                "tipo": "transversal",
                "criterio": nome,
                "quesitos": quesitos,
                "frequencias": frequencias,
                "texto": (f"{nome} foi observada com frequência alta em "
                          f"{len(quesitos)} quesitos ({', '.join(q.capitalize() for q in quesitos)}) "
                          f"— indica problema transversal que deve ser trabalhado "
                          f"em todas as técnicas."),
            })
    return observacoes


def _regra_concentrada(freqs: dict, nomes: dict, lim: dict) -> list[dict]:
    """Regra 2: critério com frequência máxima em um único quesito."""
    observacoes = []
    for q in QUESITOS:
        for indice, freq in freqs[q].items():
            if freq < lim["concentrada_min_frequencia"]:
                continue
            nome = _nome_criterio(nomes, q, indice)
            observacoes.append({
                "tipo": "concentrada",
                "criterio": nome,
                "quesitos": [q],
                "frequencias": [freq],
                "texto": (f"{nome} concentrada no {q.capitalize()} "
                          f"(frequência {freq}) — sugere revisão específica "
                          f"dessa técnica."),
            })
    return observacoes


def _regra_ranking(freqs: dict, nomes: dict, lim: dict) -> list[dict]:
    """Regra 3: critério com maior soma de frequências entre todos os quesitos."""
    soma_por_nome: dict[str, int] = {}
    for q in QUESITOS:
        for indice, freq in freqs[q].items():
            if freq == 0:
                continue
            nome = _nome_criterio(nomes, q, indice)
            soma_por_nome[nome] = soma_por_nome.get(nome, 0) + freq
    if not soma_por_nome:
        return []
    melhor_nome = max(soma_por_nome, key=soma_por_nome.get)
    melhor_soma = soma_por_nome[melhor_nome]
    if melhor_soma < lim["ranking_min_soma"]:
        return []
    return [{
        "tipo": "ranking",
        "criterio": melhor_nome,
        "quesitos": [q for q in QUESITOS if any(
            _nome_criterio(nomes, q, i) == melhor_nome and f > 0
            for i, f in freqs[q].items())],
        "frequencias": [melhor_soma],
        "texto": (f"{melhor_nome} foi o erro mais recorrente do exame "
                  f"({melhor_soma} ocorrências somadas) — prioridade de correção."),
    }]


def _regra_percentual(freqs: dict, nomes: dict, lim: dict) -> list[dict]:
    """Regra 4: percentual de quesitos em que o critério foi marcado."""
    por_nome: dict[str, list[str]] = {}
    for q in QUESITOS:
        for indice, freq in freqs[q].items():
            if freq == 0:
                continue
            nome = _nome_criterio(nomes, q, indice)
            por_nome.setdefault(nome, []).append(q)
    observacoes = []
    total_quesitos = len(QUESITOS)
    for nome, quesitos in por_nome.items():
        percentual = len(quesitos) / total_quesitos
        if percentual >= lim["percentual_min"]:
            observacoes.append({
                "tipo": "percentual",
                "criterio": nome,
                "quesitos": quesitos,
                "frequencias": [len(quesitos)],
                "texto": (f"{nome} esteve presente em "
                          f"{percentual:.0%} dos quesitos avaliados."),
            })
    return observacoes


def gerar_observacoes_automaticas(
    avaliacoes: dict,
    faixa: str = "branca",
    base_cfg: Path | None = None,
) -> list[dict]:
    """Gera as observações automáticas de um aluno a partir das avaliações.

    Args:
        avaliacoes: dict no formato do omr_reader
            ({quesito: {"frequencias": {indice: freq}}}).
        faixa: faixa do aluno (para carregar os nomes dos critérios).
        base_cfg: config/ (para limiares e nomes). None = usa padrões.

    Returns:
        Lista de observações estruturadas, limitada a max_observacoes.
    """
    lim = _carregar_limiares(base_cfg)
    nomes = _carregar_nomes_criterios(base_cfg, faixa)
    freqs = _frequencias_por_criterio(avaliacoes)

    observacoes: list[dict] = []
    observacoes.extend(_regra_transversal(freqs, nomes, lim))
    observacoes.extend(_regra_concentrada(freqs, nomes, lim))
    observacoes.extend(_regra_ranking(freqs, nomes, lim))
    observacoes.extend(_regra_percentual(freqs, nomes, lim))

    # Limita o número de observações por aluno (evita poluição).
    return observacoes[: lim["max_observacoes"]]


def merge_no_json(resultado: dict, base_cfg: Path | None = None) -> dict:
    """Integra as observações automáticas no JSON do aluno.

    Lê 'avaliacoes' e 'faixa_atual' do resultado do omr_reader e grava
    'observacoes_automaticas' (lista) no mesmo dict.
    """
    avaliacoes = resultado.get("avaliacoes", {})
    faixa = resultado.get("aluno", {}).get("faixa_atual", "branca") or "branca"
    resultado["observacoes_automaticas"] = gerar_observacoes_automaticas(
        avaliacoes, faixa, base_cfg)
    return resultado


if __name__ == "__main__":
    # Exemplo de uso (exemplo de dados do aluno T01).
    exemplo = {
        "kihon": {"frequencias": {"1": 3, "2": 0, "3": 1, "4": 0, "5": 0, "6": 0}},
        "kata": {"frequencias": {"1": 4, "2": 0, "3": 2, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0}},
        "bunkai": {"frequencias": {"1": 2, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0}},
        "kumite": {"frequencias": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0}},
    }
    obs = gerar_observacoes_automaticas(exemplo, "branca")
    print("Observações automáticas geradas:")
    for o in obs:
        print(f"  [{o['tipo']}] {o['texto']}")