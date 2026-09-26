"""tests/test_faixas.py — Fase 06: estrutura multi-faixa.

Fase 07: bloco adicional de cobertura do core.engine calibrado com a
tabela real da faixa branca (config/faixas/branca.json) e as regras
gerais (config/regras_gerais.json).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config import (
    FAIXAS_SUPORTADAS,
    FAIXAS_PLACEHOLDER,
    QUESITOS,
)

# Critérios técnicos A1–A12 (nomes normalizados aceitos pelo motor).
# Mesma lista usada em tests/test_estresse.py — validada no CI.
# Critérios vigentes no motor v2.0 (chaves semânticas das matrizes).
# A9 (defesa_incompleta) e A12 (tensao_respiracao) foram EXTINTOS na v2.0 —
# não constam de nenhuma matriz. A lista abaixo contém apenas critérios reais
# (validade travada por test_criterios_motor_sem_fantasmas). Mesma lista
# usada em tests/test_estresse.py — validada no CI.
CRITERIOS_ENGINE = [
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
# ---------------------------------------------------------------------------

def _avaliador_saturado() -> dict:
    """Avaliador com TODOS os critérios A1–A12 no máximo (7 marcações)."""
    freqs = {q: {c: 7 for c in CRITERIOS_ENGINE} for q in QUESITOS}
    return _avaliador(**freqs)

def test_processa_aluno_tem_descontos(base_cfg: Path):
    """2x base_incorreta no Kihon → fc=2, mult=1,5 → desconto 3,0."""
    from core.engine import processa_aluno

    avs = [_avaliador(kihon={"base_incorreta": 2}) for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["quesitos"]["kihon"]["detalhes"]["base_incorreta"]["fc"] == 2.0
    assert r["quesitos"]["kihon"]["nota"] < 25.0

def test_processa_aluno_reprovado(base_cfg: Path):
    """Saturação total → nota 0,0 e REPROVADO."""
    from core.engine import processa_aluno

    avs = [_avaliador_saturado() for _ in range(3)]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["nota_final"] < 70.0
    assert r["status"] == "REPROVADO"

def test_processa_aluno_ponto_atencao(base_cfg: Path):
    """Nota 68,0 → status APROVADO_PONTO_ATENCAO (50 ≤ nota < 70).

    Fórmula real do engine: desconto = fc × peso × multiplicador
    (regras_gerais.json: fc=2 → mult 1,5 | fc=1 → mult 1,0).
    Desconto de 8,0 por quesito → 25 - 8 = 17,0 × 4 = 68,0.
    Sem falta_controle → a trava de segurança não interfere.
    """
    from core.engine import processa_aluno

    avs = [
        _avaliador(
            kihon={"base_incorreta": 2, "execucao_tecnica_incorreta": 2,
                   "movimento_sem_carga": 1, "falta_foco": 1},
            kata={"embusen_incorreto": 1, "base_incorreta": 1,
                  "execucao_tecnica_incorreta": 1, "movimento_sem_carga": 1,
                  "falta_foco": 1, "perda_equilibrio": 1,
                  "falta_ritmo": 1, "ausencia_kiai": 1},
            bunkai={"base_incorreta": 2, "execucao_tecnica_incorreta": 2,
                    "movimento_sem_carga": 1, "falta_foco": 1},
            kumite={"movimento_sem_carga": 2, "falta_foco": 2,
                    "perda_equilibrio": 1, "distancia_inadequada": 1},
        )
        for _ in range(3)
    ]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["status"] == "APROVADO_PONTO_ATENCAO"
    assert r["nota_final"] == 68.0

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

def test_processa_aluno_deriva_faixa_do_bloco(base_cfg: Path):
    """Sem faixa no chamador → deriva de aluno.faixa_atual."""
    from core.engine import processa_aluno

    avs = [_avaliador() for _ in range(3)]
    avs[0]["aluno"] = {"faixa_atual": "branca"}
    r = processa_aluno(avs, base_cfg)  # sem o 3º argumento
    assert r["faixa"] == "branca"
    assert r["nota_final"] == 100.0

def test_processa_aluno_revisao_pendente(base_cfg: Path):
    """dados_legados → REVISAO_PENDENTE."""
    from core.engine import processa_aluno

    avs = [_avaliador() for _ in range(3)]
    avs[0]["dados_legados"] = True
    avs[0]["codigos_descartados"] = {"kihon": [9, 10]}
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["status"] == "REVISAO_PENDENTE"
    assert r["dados_legados"] is True
    assert r["alerta_legado"]["codigos_descartados"]["kihon"] == [9, 10]

def test_processa_aluno_observacoes(base_cfg: Path):
    """Observações por quesito e gerais são repassadas."""
    from core.engine import processa_aluno

    avs = [_avaliador() for _ in range(3)]
    avs[0]["avaliacoes"]["kihon"]["observacao"] = "Chutes firmes"
    avs[0]["observacao_geral"] = "Ótima evolução"
    r = processa_aluno(avs, base_cfg, "branca")
    assert "Chutes firmes" in r["observacoes"]["por_quesito"]["kihon"]
    assert "Ótima evolução" in r["observacoes"]["gerais"]
    
def test_criterios_motor_sem_fantasmas(base_cfg: Path):
    """A lista de critérios do motor só pode conter chaves reais das matrizes
    v2.0 — A9/A12 extintos não podem voltar como 'fantasmas'."""
    cfg = json.loads(
        (base_cfg / "faixas" / "branca.json").read_text(encoding="utf-8")
    )
    chaves_reais = {
        c["chave"]
        for q in cfg["quesitos"].values()
        for c in q["criterios"]
    }
    for chave in CRITERIOS_ENGINE:
        assert chave in chaves_reais, (
            f"'{chave}' não existe nas matrizes v2.0 — critério fantasma?"
        )
        
def test_criterios_identicos_ate_azul(base_cfg: Path):
    """Decisão de produto: da branca à azul, TODAS as faixas usam os MESMOS
    critérios (matriz única, sem progressão nesta versão). Trava a regra —
    se alguém editar uma matriz divergente, a suíte falha na hora."""
    referencia = None
    for faixa in FAIXAS_SUPORTADAS:
        cfg = json.loads(
            (base_cfg / "faixas" / f"{faixa}.json").read_text(encoding="utf-8"))
        atuais = {
            q: sorted(c["chave"] for c in cfg["quesitos"][q]["criterios"])
            for q in QUESITOS
        }
        if referencia is None:
            referencia = atuais
            continue
        assert atuais == referencia, (
            f"{faixa} diverge dos critérios da branca — decisão de produto "
            "determina critérios idênticos da branca à azul (pesos: roadmap)")