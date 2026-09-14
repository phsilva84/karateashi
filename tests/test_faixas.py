"""tests/test_faixas.py — Fase 06: estrutura multi-faixa.

Correção Fase 07: bloco adicional de cobertura do core.engine usando a
lista de critérios A1–A12 validada no CI (mesma de tests/test_estresse.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
FAIXAS_PLACEHOLDER = ["roxa", "marrom", "preta"]
QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

# Critérios técnicos A1–A12 (nomes normalizados aceitos pelo motor).
# Mesma lista usada em tests/test_estresse.py — validada no CI.
CRITERIOS_ENGINE = [
    "base_incorreta",              # A1
    "execucao_tecnica_incorreta",  # A2
    "movimento_sem_carga",         # A3
    "ausencia_kiai",               # A4
    "embusen_incorreto",           # A5
    "falta_foco",                  # A6
    "perda_equilibrio",            # A7
    "falta_ritmo",                 # A8
    "defesa_incompleta",           # A9
    "falta_controle",              # A10 (trava ética)
    "distancia_inadequada",        # A11
    "tensao_respiracao",           # A12
]

def _avaliador(**freqs):
    """Monta um avaliador no schema v2.0 do engine."""
    return {
        "avaliacoes": {
            q: {"frequencias": freqs.get(q, {}), "observacao": ""}
            for q in QUESITOS
        }
    }

# ---------------------------------------------------------------------------
# Testes originais (Fase 06) — mantidos sem alteração
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("faixa", FAIXAS_SUPORTADAS)
def test_faixas_suportadas_tem_tabela(faixa, base_cfg: Path):
    cfg = json.loads(
        (base_cfg / "faixas" / f"{faixa}.json").read_text(encoding="utf-8")
    )
    assert cfg["nao_suportada"] is False
    assert set(cfg["quesitos"]) == set(QUESITOS)
    assert len(cfg["quesitos"]["kihon"]["criterios"]) == 6
    assert len(cfg["quesitos"]["kata"]["criterios"]) == 8
    assert len(cfg["quesitos"]["bunkai"]["criterios"]) == 8
    assert len(cfg["quesitos"]["kumite"]["criterios"]) == 7

@pytest.mark.parametrize("faixa", FAIXAS_PLACEHOLDER)
def test_faixas_placeholder_nao_suportadas(faixa, base_cfg: Path):
    cfg = json.loads(
        (base_cfg / "faixas" / f"{faixa}.json").read_text(encoding="utf-8")
    )
    assert cfg["nao_suportada"] is True
    assert cfg["quesitos"] == {}

def test_coordenadas_por_faixa_existem(base_cfg: Path):
    for faixa in FAIXAS_SUPORTADAS:
        assert (base_cfg / "coordenadas" / f"{faixa}.json").exists()

def test_carregar_faixa_rejeita_placeholder(base_cfg: Path):
    from core.engine import carregar_faixa

    with pytest.raises(ValueError, match="não suportada"):
        carregar_faixa(base_cfg, "roxa")

def test_carregar_faixa_rejeita_inexistente(base_cfg: Path):
    from core.engine import carregar_faixa

    with pytest.raises(ValueError, match="não possui arquivo"):
        carregar_faixa(base_cfg, "inexistente")

def test_processa_aluno_sem_marcacoes(base_cfg: Path):
    from core.engine import processa_aluno

    avs = [_avaliador() for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["faixa"] == "branca"
    assert r["nota_final"] == 100.0
    assert r["status"] == "APROVADO"

def test_trava_seguranca_bunkai(base_cfg: Path):
    from core.engine import processa_aluno

    avs = [_avaliador(bunkai={"falta_controle": 1}) for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["quesitos"]["bunkai"]["alerta"] == "TRAVA_ATIVADA"
    assert r["quesitos"]["bunkai"]["nota"] <= 10.0

# ---------------------------------------------------------------------------
# BLOCO ADICIONAL — Cobertura do core.engine (Fase 07)
# Alvos: descontos por critério, status REPROVADO, alertas de Kumite,
# consenso com N=1/N=2 e carregamento das demais faixas.
# ---------------------------------------------------------------------------

def _avaliador_saturado() -> dict:
    """Avaliador com TODOS os critérios A1–A12 no máximo (7 marcações)."""
    freqs = {q: {c: 7 for c in CRITERIOS_ENGINE} for q in QUESITOS}
    return _avaliador(**freqs)

def test_processa_aluno_tem_descontos(base_cfg: Path):
    """2x base_incorreta no Kihon → frequência 2 e nota abaixo de 25."""
    from core.engine import processa_aluno

    avs = [_avaliador(kihon={"base_incorreta": 2}) for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["quesitos"]["kihon"]["detalhes"]["base_incorreta"]["fc"] == 2.0
    assert r["quesitos"]["kihon"]["nota"] < 25.0

def test_processa_aluno_reprovado(base_cfg: Path):
    """Saturação total → REPROVADO (ramo de status abaixo da nota mínima)."""
    from core.engine import processa_aluno

    avs = [_avaliador_saturado() for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["nota_final"] < 70.0
    assert r["status"] == "REPROVADO"

def test_kumite_alerta_etico_um_de_tres(base_cfg: Path):
    """1 de 3 avaliadores marca falta de controle → ALERTA_ETICO (sem trava)."""
    from core.engine import processa_aluno

    avs = [_avaliador(kumite={"falta_controle": 1})] + [
        _avaliador() for _ in range(2)
    ]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["quesitos"]["kumite"]["alerta"] == "ALERTA_ETICO"
    assert r["quesitos"]["kumite"]["nota"] > 10.0

def test_kumite_trava_tres_de_tres(base_cfg: Path):
    """3 de 3 marcam falta de controle → TRAVA_ATIVADA com teto em 10,0."""
    from core.engine import processa_aluno

    avs = [_avaliador(kumite={"falta_controle": 1}) for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["quesitos"]["kumite"]["alerta"] == "TRAVA_ATIVADA"
    assert r["quesitos"]["kumite"]["nota"] == 10.0

@pytest.mark.parametrize("n", [1, 2])
def test_consenso_com_menos_de_tres_avaliadores(base_cfg: Path, n: int):
    """Consenso com 1 e 2 avaliadores → média correta (100,0)."""
    from core.engine import processa_aluno

    r = processa_aluno([_avaliador() for _ in range(n)], base_cfg, "branca")
    assert r["nota_final"] == 100.0
    assert r["status"] == "APROVADO"

@pytest.mark.parametrize("faixa", ["amarela", "laranja", "verde", "azul"])
def test_sem_marcacoes_nas_demais_faixas(base_cfg: Path, faixa: str):
    """Zero faltas em cada faixa suportada → carrega a tabela e dá 100,0."""
    from core.engine import processa_aluno

    r = processa_aluno([_avaliador() for _ in range(3)], base_cfg, faixa)
    assert r["faixa"] == faixa
    assert r["nota_final"] == 100.0
    assert r["status"] == "APROVADO"
    
def test_processa_aluno_recuperacao(base_cfg: Path):
    """Nota intermediária (68,0) → status RECUPERAÇÃO (ramo do meio).

    Tabela de descontos v2.0 (Códigos Técnicos A1–A12):
    A5 embusen_incorreto = 2,0 | A1 base_incorreta = 1,0 | A6 falta_foco = 1,0
    Com fc=2 em cada um: 2×2,0 + 2×1,0 + 2×1,0 = 8,0 de desconto por quesito
    → 25 - 8 = 17,0 × 4 quesitos = 68,0 → faixa de RECUPERAÇÃO (60–70).
    """
    from core.engine import processa_aluno

    avs = [
        _avaliador(
            kihon={"embusen_incorreto": 2, "base_incorreta": 2, "falta_foco": 2},
            kata={"embusen_incorreto": 2, "base_incorreta": 2, "falta_foco": 2},
            bunkai={"embusen_incorreto": 2, "base_incorreta": 2, "falta_foco": 2},
            kumite={"embusen_incorreto": 2, "base_incorreta": 2, "falta_foco": 2},
        )
        for _ in range(3)
    ]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["status"] == "RECUPERAÇÃO"
    assert r["nota_final"] < 70.0