"""Testes de estresse do Karate-Ashi — Seção 14 da especificação v2.0."""

from pathlib import Path

import pytest
from core.config import QUESITOS

from core.engine import processa_aluno

# Critérios técnicos A1–A12 (nomes normalizados usados pelo motor).
# Lista completa para que "zero faltas" e "saturação" exercitem TODOS os
# critérios, não só os de Kihon (nota da seção 9 da Fase 07).
CRITERIOS = [
    "base_incorreta",              # A1
    "execucao_tecnica_incorreta",  # A2
    "movimento_sem_carga",         # A3
    "ausencia_kiai",               # A4
    "embusen_incorreto",           # A5
    "falta_foco",                  # A6
    "perda_equilibrio",            # A7
    "falta_ritmo",                 # A8
    "falta_controle",              # A10 (trava ética)
    "distancia_inadequada",        # A11
]

def _avaliacao_vazia(aluno_id: str = "A01") -> list[dict]:
    """Três avaliadores SEM nenhuma marcação (categoria zerada)."""
    freq = {c: 0 for c in CRITERIOS}
    return [
        {
            "avaliacoes": {
                q: {"frequencias": dict(freq), "observacao": ""}
                for q in QUESITOS
            }
        }
        for _ in range(3)
    ]

def _avaliacao_saturada() -> list[dict]:
    """Todos os critérios com 7 marcações (saturação máxima)."""
    avaliacoes = _avaliacao_vazia()
    for av in avaliacoes:
        for q in av["avaliacoes"]:
            for chave in av["avaliacoes"][q]["frequencias"]:
                av["avaliacoes"][q]["frequencias"][chave] = 7
    return avaliacoes

def test_cenario_1_zero_faltas(base_cfg: Path):
    """Cenário 1: avaliação impecável deve dar 100,0 e APROVADO."""
    resultado = processa_aluno(_avaliacao_vazia(), base_cfg, "branca")
    assert resultado["nota_final"] == 100.0
    assert resultado["status"] == "APROVADO"

def test_cenario_2_saturacao_maxima(base_cfg: Path):
    """Cenário 2: saturação total deve zerar todos os quesitos."""
    resultado = processa_aluno(_avaliacao_saturada(), base_cfg, "branca")
    for q in ["kihon", "kata", "bunkai", "kumite"]:
        assert resultado["quesitos"][q]["nota"] == 0.0
    assert resultado["nota_final"] == 0.0
    assert resultado["status"] == "REPROVADO"

def _com_falta_controle(n_avaliadores_com_marcacao: int) -> list[dict]:
    """Banca de 3 com falta de controle em Kumite em N dos avaliadores."""
    base = _avaliacao_vazia()
    for i in range(3):
        if i < n_avaliadores_com_marcacao:
            base[i]["avaliacoes"]["kumite"]["frequencias"]["falta_controle"] = 1
    return base

def test_cenario_3_trava_consenso_total(base_cfg: Path):
    """3/3 marcaram falta de controle → teto de 10,0 no Kumite."""
    resultado = processa_aluno(_com_falta_controle(3), base_cfg, "branca")
    assert resultado["quesitos"]["kumite"]["nota"] == 10.0
    assert resultado["quesitos"]["kumite"]["alerta"] == "TRAVA_ATIVADA"

def test_cenario_3b_trava_parcial_alerta_etico(base_cfg: Path):
    """1/3 marcaram → NÃO trava; deve gerar ALERTA_ETICO."""
    resultado = processa_aluno(_com_falta_controle(1), base_cfg, "branca")
    assert resultado["quesitos"]["kumite"]["nota"] > 10.0
    assert resultado["quesitos"]["kumite"]["alerta"] == "ALERTA_ETICO"

def test_cenario_4_variacao_de_bancas(base_cfg: Path):
    """1, 2 e 3 avaliadores com o mesmo padrão → divisor N correto.

    Cada avaliador marca 2 em 'base_incorreta' no Kihon.
    fc esperado: 1 avaliador → 2,0 | 2 avaliadores → 2,0 | 3 → 2,0
    (a MÉDIA é a mesma, pois o padrão é idêntico).
    """
    for n in [1, 2, 3]:
        avaliacoes = _avaliacao_vazia()[:n]
        for av in avaliacoes:
            av["avaliacoes"]["kihon"]["frequencias"]["base_incorreta"] = 2
        resultado = processa_aluno(avaliacoes, base_cfg, "branca")
        detalhe = resultado["quesitos"]["kihon"]["detalhes"]["base_incorreta"]
        assert detalhe["fc"] == 2.0, f"N={n}: fc={detalhe['fc']}"