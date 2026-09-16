"""tests/test_contradicoes.py — Cobertura e trava da regra de contradição.

Regra (v2col-3.0): o MESMO avaliador (uma folha) não pode marcar o par
contraditório — um 'Ótimo!' e o 'A melhorar' oposto. Quando marca, as DUAS
observações são anuladas e a contradição é registrada em
'contradicoes_observacoes' para o relatório geral, para o mestre refinar com
o avaliador.

Cobre: detectar (anula os dois, preserva o solto, múltiplos pares),
carregar_pares (padrão embutido e leitura do config) e consolidar
(agregação por aluno/avaliador).
"""
from __future__ import annotations

import json

from core import contradicoes
from core.contradicoes import (
    PARES_PADRAO,
    VOCAB,
    carregar_pares,
    consolidar,
    detectar,
)

# --- detectar ---------------------------------------------------------------

def test_detectar_par_contraditorio_anula_ambos():
    limpas, contras = detectar(["obs_p7", "obs_m7"], PARES_PADRAO)
    assert limpas == []
    assert len(contras) == 1
    assert contras[0]["otimo"] == "obs_p7"
    assert contras[0]["melhorar"] == "obs_m7"
    assert contras[0]["topico"] == "kata"

def test_detectar_par_solto_preserva():
    limpas, contras = detectar(["obs_p7"], PARES_PADRAO)
    assert limpas == ["obs_p7"]
    assert contras == []

def test_detectar_preserva_as_nao_contraditorias():
    limpas, contras = detectar(
        ["obs_p1", "obs_p7", "obs_m7", "obs_m3"], PARES_PADRAO)
    assert limpas == ["obs_p1", "obs_m3"]
    assert len(contras) == 1

def test_detectar_multiplos_pares():
    limpas, contras = detectar(
        ["obs_p7", "obs_m7", "obs_p8", "obs_m8"], PARES_PADRAO)
    assert limpas == []
    assert len(contras) == 2
    topicos = {c["topico"] for c in contras}
    assert topicos == {"kata", "kihon"}

def test_detectar_sem_marcacoes():
    limpas, contras = detectar([], PARES_PADRAO)
    assert limpas == []
    assert contras == []

def test_detectar_topico_sem_par_no_vocabulario_preserva():
    """obs_p5 não tem par contraditório definido — deve permanecer."""
    limpas, contras = detectar(["obs_p5", "obs_m3"], PARES_PADRAO)
    assert limpas == ["obs_p5", "obs_m3"]
    assert contras == []

def test_detectar_traz_texto_legivel_do_vocabulario():
    _, contras = detectar(["obs_p7", "obs_m7"], PARES_PADRAO)
    assert contras[0]["otimo_texto"] == VOCAB["obs_p7"]
    assert contras[0]["melhorar_texto"] == VOCAB["obs_m7"]
    assert contras[0]["otimo_texto"] == "Ótima Execução do Kata"
    assert contras[0]["melhorar_texto"] == "Execução Incorreta do Kata"

def test_detectar_respeita_pares_customizados():
    """A regra é data-driven: pares passados vencem os padrão."""
    pares = [{"topico": "custom", "otimo": "obs_p1", "melhorar": "obs_m1"}]
    limpas, contras = detectar(["obs_p1", "obs_m1", "obs_p7", "obs_m7"], pares)
    assert limpas == ["obs_p7", "obs_m7"]
    assert contras[0]["topico"] == "custom"

# --- carregar_pares ---------------------------------------------------------

def test_carregar_pares_sem_arquivo_usa_padrao(tmp_path):
    assert carregar_pares(tmp_path) == PARES_PADRAO

def test_carregar_pares_le_do_config(tmp_path):
    """Fase 3 (item 7): JSON custom SOMA aos pares padrão (união).

    Um par novo sem colisão com os padrão é ADICIONADO; nenhum padrão
    some do relatório. Ex.: custom (obs_p1, obs_m1) não colide com
    nenhum padrão -> resultado tem len(PARES_PADRAO) + 1.
    """
    pares = [{"topico": "custom", "otimo": "obs_p1", "melhorar": "obs_m1"}]
    (tmp_path / "observacoes_contradicoes.json").write_text(
        json.dumps({"pares": pares}), encoding="utf-8")
    resultado = carregar_pares(tmp_path)
    chaves = {(p["otimo"], p["melhorar"]) for p in resultado}
    assert len(resultado) == len(PARES_PADRAO) + 1
    assert ("obs_p1", "obs_m1") in chaves  # custom presente
    for p in PARES_PADRAO:                  # padrão continuam todos
        assert (p["otimo"], p["melhorar"]) in chaves

def test_carregar_pares_json_sem_campo_pares_usa_padrao(tmp_path):
    (tmp_path / "observacoes_contradicoes.json").write_text(
        json.dumps({"outra": "coisa"}), encoding="utf-8")
    assert carregar_pares(tmp_path) == PARES_PADRAO

# --- consolidar -------------------------------------------------------------

def _resultado(aluno, avaliador, contradicoes_obs):
    return {
        "aluno": {"id": aluno, "faixa_atual": "branca"},
        "metadados": {"avaliador_id": avaliador},
        "contradicoes_observacoes": contradicoes_obs,
    }

def test_consolidar_agrega_por_aluno_e_avaliador():
    resultados = [
        _resultado("A02", "S01", [{
            "topico": "kata", "otimo": "obs_p7",
            "otimo_texto": "Ótima Execução do Kata",
            "melhorar": "obs_m7",
            "melhorar_texto": "Execução Incorreta do Kata",
        }]),
        _resultado("A07", "S02", [{
            "topico": "kihon", "otimo": "obs_p8",
            "otimo_texto": "Ótima execução de Kihons",
            "melhorar": "obs_m8",
            "melhorar_texto": "Dificuldade na execução de Kihons",
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