"""tests/test_engine.py — Critérios de aceite da Fase 01 (Karate-Ashi v2.0)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine import (
    NOTA_MAX_QUESITO,
    QUESTOS_ORDEM,
    carregar_json,
    classificar_status,
    consenso_controle,
    desconto_criterio,
    frequencia_media,
    multiplicador_progressivo,
    processa_aluno,
)

BASE_CFG = ROOT / "config"

@pytest.fixture(scope="module")
def regras() -> dict:
    return carregar_json(BASE_CFG / "regras_gerais.json")

@pytest.fixture(scope="module")
def cfg_quesitos() -> dict:
    return carregar_json(BASE_CFG / "criterios_por_quesito.json")

def chaves_do_quesito(cfg_quesitos: dict, quesito: str) -> list[str]:
    return [c["chave"] for c in cfg_quesitos["quesitos"][quesito]["criterios"]]

def avaliador_limpo(cfg_quesitos: dict) -> dict:
    """Avaliador sem nenhuma marcação de falha."""
    av = {"avaliacoes": {}}
    for q in QUESTOS_ORDEM:
        av["avaliacoes"][q] = {
            "frequencias": {ch: 0 for ch in chaves_do_quesito(cfg_quesitos, q)},
            "observacao": "",
        }
    return av

def aval_com_marcacoes(cfg_quesitos: dict, quesito: str,
                       marcacoes: dict, n_avaliadores: int = 3) -> list[dict]:
    """Cria n_avaliadores com o MESMO padrão de marcações em um quesito."""
    avs = []
    for _ in range(n_avaliadores):
        av = avaliador_limpo(cfg_quesitos)
        for chave, freq in marcacoes.items():
            av["avaliacoes"][quesito]["frequencias"][chave] = freq
        avs.append(av)
    return avs

# --- Critério 1: zero faltas -> 100.0 / APROVADO -------------------------
def test_sem_faltas_aprovado_100(cfg_quesitos, regras):
    avs = [avaliador_limpo(cfg_quesitos) for _ in range(3)]
    res = processa_aluno(avs, BASE_CFG)

    assert res["nota_final"] == 100.0
    assert res["status"] == "APROVADO"
    for q in QUESTOS_ORDEM:
        assert res["quesitos"][q]["nota"] == NOTA_MAX_QUESITO
        assert res["quesitos"][q]["alerta"] is None

# --- Critério 2: saturação (7 em tudo) -> 0.0 / REPROVADO -----------------
def test_saturacao_total_reprovado_0(cfg_quesitos, regras):
    avs = [avaliador_limpo(cfg_quesitos) for _ in range(3)]
    for av in avs:
        for q in QUESTOS_ORDEM:
            for ch in chaves_do_quesito(cfg_quesitos, q):
                av["avaliacoes"][q]["frequencias"][ch] = 7

    res = processa_aluno(avs, BASE_CFG)

    assert res["nota_final"] == 0.0
    assert res["status"] == "REPROVADO"
    for q in QUESTOS_ORDEM:
        assert res["quesitos"][q]["nota"] == 0.0

# --- Critério 3: trava por consenso total (Bunkai 3/3) ---------------------
def test_trava_consenso_total_bunkai(cfg_quesitos, regras):
    avs = aval_com_marcacoes(cfg_quesitos, "bunkai",
                             {"falta_controle": 1}, n_avaliadores=3)
    res = processa_aluno(avs, BASE_CFG)
    r = res["quesitos"]["bunkai"]

    assert r["alerta"] == "TRAVA_ATIVADA"
    assert r["nota"] == 10.0  # nota bruta 13.0 limitada pelo teto
    assert r["controle_marcacoes"] == [1, 1, 1]

# --- Critério 4: trava parcial (1/3) -> ALERTA_ETICO, sem trava ------------
def test_trava_parcial_alerta_etico(cfg_quesitos, regras):
    avs = aval_com_marcacoes(cfg_quesitos, "kumite",
                             {"falta_controle": 1}, n_avaliadores=3)
    avs[1]["avaliacoes"]["kumite"]["frequencias"]["falta_controle"] = 0
    avs[2]["avaliacoes"]["kumite"]["frequencias"]["falta_controle"] = 0

    res = processa_aluno(avs, BASE_CFG)
    r = res["quesitos"]["kumite"]

    assert r["alerta"] == "ALERTA_ETICO"
    assert r["nota"] > 10.0  # trava NÃO deve ativar

    peso = next(c["peso"] for c in cfg_quesitos["quesitos"]["kumite"]["criterios"]
                if c["chave"] == "falta_controle")
    fc = frequencia_media([1, 0, 0])
    mult = multiplicador_progressivo(fc, regras["progressivo"])
    esperado = round(NOTA_MAX_QUESITO - desconto_criterio(fc, peso, mult), 2)
    assert r["nota"] == esperado == 21.0  # com peso A10 = 12.0

# --- Critério 5: variação de bancas (1, 2, 3 avaliadores) -------------------
def test_variacao_bancas_divisor_correto(cfg_quesitos, regras):
    notas = []
    for n in (1, 2, 3):
        avs = aval_com_marcacoes(cfg_quesitos, "kihon",
                                 {"base_incorreta": 2, "execucao_incorreta": 1},
                                 n_avaliadores=n)
        res = processa_aluno(avs, BASE_CFG)
        notas.append(res["nota_final"])

    assert notas == [95.0, 95.0, 95.0]  # mesmo padrão -> mesma nota
    assert frequencia_media([2]) == 2.0
    assert frequencia_media([2, 2]) == 2.0
    assert frequencia_media([2, 2, 2]) == 2.0

# --- Unit tests dos helpers -------------------------------------------------
def test_frequencia_media():
    assert frequencia_media([]) == 0.0
    assert frequencia_media([3, 4]) == 3.5
    assert frequencia_media([7, 7, 7]) == 7.0

def test_multiplicador_progressivo(regras):
    faixas = regras["progressivo"]
    casos = {
        0.0: 0.0, 0.5: 1.0, 1.0: 1.0,
        1.1: 1.5, 2.5: 1.5,
        2.6: 2.0, 4.5: 2.0,
        4.6: 2.5, 7.0: 2.5,
        7.5: 0.0,  # fora das faixas
    }
    for fc, esperado in casos.items():
        assert multiplicador_progressivo(fc, faixas) == esperado

def test_desconto_criterio():
    assert desconto_criterio(2.0, 2.0, 1.5) == 6.0
    assert desconto_criterio(2.0, -2.0, 1.5) == 6.0  # usa |peso|
    assert desconto_criterio(1 / 3, 12.0, 1.0) == 4.0

def test_consenso_controle():
    assert consenso_controle([1, 1, 1]) is True
    assert consenso_controle([0, 0, 0]) is False
    assert consenso_controle([1, 0, 1]) is False
    assert consenso_controle([]) is False

def test_classificar_status(regras):
    assert classificar_status(100.0, regras) == "APROVADO"
    assert classificar_status(70.0, regras) == "APROVADO"
    assert classificar_status(69.9, regras) == "RECUPERACAO"
    assert classificar_status(60.0, regras) == "RECUPERACAO"
    assert classificar_status(59.9, regras) == "REPROVADO"