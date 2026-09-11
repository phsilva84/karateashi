"""tests/test_faixas.py — Fase 06: estrutura multi-faixa."""
import json
from pathlib import Path

import pytest

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
FAIXAS_PLACEHOLDER = ["roxa", "marrom", "preta"]
QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

def _avaliador(**freqs):
    """Monta um avaliador no schema v2.0 do engine."""
    return {
        "avaliacoes": {
            q: {"frequencias": freqs.get(q, {}), "observacao": ""}
            for q in QUESITOS
        }
    }

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