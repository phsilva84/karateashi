"""tests/test_contradicoes.py — Trava da regra de contradição (v2col-3.0).

Alinhado ao vocabulário 6+6: pares contraditórios homólogos obs_pN ↔ obs_mN
(mesma regra do omr_reader). Cobre detectar, carregar_pares e consolidar.
"""
from __future__ import annotations

import json

from core.contradicoes import (
    PARES_PADRAO,
    VOCAB,
    carregar_pares,
    consolidar,
    detectar,
)


def _resultado(aluno_id, avaliador_id, contradicoes):
    return {
        "aluno": {"id": aluno_id},
        "metadados": {"avaliador_id": avaliador_id},
        "contradicoes_observacoes": contradicoes,
    }


# --- detectar ---------------------------------------------------------------
def test_detectar_par_contraditorio_anula_ambos():
    limpas, contras = detectar(["obs_p2", "obs_m2"], PARES_PADRAO)
    assert limpas == []
    assert len(contras) == 1
    assert contras[0]["otimo"] == "obs_p2"
    assert contras[0]["melhorar"] == "obs_m2"
    assert contras[0]["topico"] == "kata"


def test_detectar_par_solto_preserva():
    limpas, contras = detectar(["obs_p2"], PARES_PADRAO)
    assert limpas == ["obs_p2"]
    assert contras == []


def test_detectar_preserva_as_nao_contraditorias():
    limpas, contras = detectar(
        ["obs_p1", "obs_p2", "obs_m2", "obs_m3"], PARES_PADRAO)
    assert limpas == ["obs_p1", "obs_m3"]
    assert len(contras) == 1


def test_detectar_multiplos_pares():
    limpas, contras = detectar(
        ["obs_p2", "obs_m2", "obs_p4", "obs_m4"], PARES_PADRAO)
    assert limpas == []
    assert len(contras) == 2
    topicos = {c["topico"] for c in contras}
    assert topicos == {"kata", "kumite"}


def test_detectar_sem_marcacoes():
    limpas, contras = detectar([], PARES_PADRAO)
    assert limpas == [] and contras == []


def test_detectar_chave_desconhecida_preserva():
    limpas, contras = detectar(["obs_p1", "obs_x99"], PARES_PADRAO)
    assert limpas == ["obs_p1", "obs_x99"]
    assert contras == []


def test_detectar_traz_texto_legivel_do_vocabulario():
    _, contras = detectar(["obs_p2", "obs_m2"], PARES_PADRAO)
    assert contras[0]["otimo_texto"] == VOCAB["obs_p2"]
    assert contras[0]["melhorar_texto"] == VOCAB["obs_m2"]
    assert contras[0]["otimo_texto"] == "Bom dominio do Kata"
    assert contras[0]["melhorar_texto"] == "Dificuldade no Kata"


def test_detectar_respeita_pares_customizados():
    """A regra é data-driven: pares passados vencem os padrão."""
    pares = [{"topico": "custom", "otimo": "obs_p1",
              "melhorar": "obs_m1"}]
    limpas, contras = detectar(
        ["obs_p1", "obs_m1", "obs_p2", "obs_m2"], pares)
    assert limpas == ["obs_p2", "obs_m2"]
    assert contras[0]["topico"] == "custom"


# --- carregar_pares ---------------------------------------------------------
def test_carregar_pares_sem_arquivo_usa_padrao(tmp_path):
    assert carregar_pares(tmp_path) == PARES_PADRAO


def test_carregar_pares_le_do_config(tmp_path):
    """JSON custom SOMA aos pares padrão (união, Fase 3 item 7)."""
    pares = [{"topico": "custom", "otimo": "obs_p3",
              "melhorar": "obs_m1"}]
    (tmp_path / "observacoes_contradicoes.json").write_text(
        json.dumps({"pares": pares}), encoding="utf-8")
    resultado = carregar_pares(tmp_path)
    chaves = {(p["otimo"], p["melhorar"]) for p in resultado}
    assert len(resultado) == len(PARES_PADRAO) + 1
    assert ("obs_p3", "obs_m1") in chaves
    for p in PARES_PADRAO:
        assert (p["otimo"], p["melhorar"]) in chaves


def test_carregar_pares_json_sem_campo_pares_usa_padrao(tmp_path):
    (tmp_path / "observacoes_contradicoes.json").write_text(
        json.dumps({"outra": "coisa"}), encoding="utf-8")
    assert carregar_pares(tmp_path) == PARES_PADRAO


# --- consolidar -------------------------------------------------------------
def test_consolidar_agrega_por_aluno_e_avaliador():
    resultados = [
        _resultado("A02", "S01", [{
            "topico": "kata", "otimo": "obs_p2",
            "otimo_texto": "Bom dominio do Kata",
            "melhorar": "obs_m2",
            "melhorar_texto": "Dificuldade no Kata",
        }]),
        _resultado("A07", "S02", [{
            "topico": "kumite", "otimo": "obs_p4",
            "otimo_texto": "Boa Conducao no Kumite",
            "melhorar": "obs_m4",
            "melhorar_texto": "Dificuldade nos Kumites",
        }]),
    ]
    linhas = consolidar(resultados)
    assert len(linhas) == 2
    assert linhas[0]["aluno_id"] == "A02"
    assert linhas[0]["avaliador_id"] == "S01"
    assert linhas[0]["topico"] == "kata"
    assert linhas[1]["aluno_id"] == "A07"
    assert linhas[1]["avaliador_id"] == "S02"


def test_consolidar_vazio_quando_sem_contradicoes():
    resultados = [
        _resultado("A01", "S01", []),
        {"aluno": {"id": "A02"}, "metadados": {"avaliador_id": "S01"}},
    ]
    assert consolidar(resultados) == []


def test_consolidar_tolera_campo_ausente_ou_none():
    resultados = [
        {"aluno": {"id": "A03"}, "metadados": {"avaliador_id": "S03"},
         "contradicoes_observacoes": None},
        {"aluno": {}, "metadados": {}},
    ]
    assert consolidar(resultados) == []