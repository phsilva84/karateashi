"""tests/test_observacoes.py — Contrato do vocabulário 6+6 e da montagem da
observação sem prefixos ('Ótimo!'/'A melhorar:').

Alinhado à decisão: manter o vocabulário atual (Boa execucao dos Kihons, ...)
e montar a observação apenas com os textos, separados por '; '.
"""
from core import observacoes


def test_vocabulario_completo():
    """As 12 chaves oficiais existem e não se sobrepõem (6+6)."""
    positivas = set(observacoes.OBS_POSITIVAS)
    melhorar = set(observacoes.OBS_MELHORAR)
    assert len(positivas) == 6
    assert len(melhorar) == 6
    assert positivas.isdisjoint(melhorar)


def test_vocabulario_chaves_sequenciais():
    """Chaves obs_p1..p6 e obs_m1..m6 sequenciais (contrato ROIs)."""
    assert set(observacoes.OBS_POSITIVAS) == {f"obs_p{i}" for i in range(1, 7)}
    assert set(observacoes.OBS_MELHORAR) == {f"obs_m{i}" for i in range(1, 7)}


def test_vocabulario_textos_esperados():
    """Textos oficiais do vocabulário 6+6 (fonte única da folha e relatório)."""
    assert observacoes.OBS_POSITIVAS["obs_p1"] == "Boa execucao dos Kihons"
    assert observacoes.OBS_POSITIVAS["obs_p6"] == "Otimo Desempenho"
    assert observacoes.OBS_MELHORAR["obs_m2"] == "Dificuldade no Kata"
    assert observacoes.OBS_MELHORAR["obs_m6"] == "Nervosismo Constante"


def test_montar_observacao_so_positivas():
    """Sem prefixos; ordem da folha (p1 antes de p3)."""
    texto = observacoes.montar_observacao(["obs_p3", "obs_p1"])
    assert texto == "Boa execucao dos Kihons; Boa aplicacao do Bunkai"


def test_montar_observacao_so_melhorar():
    """Sem prefixos; ordem da folha (m2 antes de m6)."""
    texto = observacoes.montar_observacao(["obs_m6", "obs_m2"])
    assert texto == "Dificuldade no Kata; Nervosismo Constante"


def test_montar_observacao_misto():
    """BOM! sempre antes de A MELHORAR; sem prefixos."""
    texto = observacoes.montar_observacao(["obs_m2", "obs_p1"])
    assert texto == "Boa execucao dos Kihons; Dificuldade no Kata"


def test_montar_observacao_ordem():
    """p antes de m; dentro da coluna, ordem impressa na folha."""
    texto = observacoes.montar_observacao(
        ["obs_m1", "obs_p6", "obs_p2", "obs_m4"])
    assert texto == ("Bom dominio do Kata; Otimo Desempenho; "
                     "Dificuldade nos Kihon; Dificuldade nos Kumites")


def test_montar_observacao_ignora_chaves_desconhecidas(caplog):
    """Chaves fora do vocabulário são ignoradas (com aviso)."""
    texto = observacoes.montar_observacao(["obs_p1", "obs_x99", "obs_outro_p"])
    assert texto == "Boa execucao dos Kihons"
    assert any("desconhecidas" in r.message for r in caplog.records)


def test_merge_no_json_popula_campos():
    """Lista bruta sai na ordem canônica (p antes de m), deduplicada."""
    resultado = {
        "metadados": {"avaliador_id": "S01", "exame_id": "EXA-D01-2026-02"},
        "aluno": {"id": "A01"},
        "observacoes_marcadas": ["obs_m2", "obs_p1", "obs_m2"],
    }
    saida = observacoes.merge_no_json(resultado)
    assert saida is resultado
    assert saida["observacoes_marcadas"] == ["obs_p1", "obs_m2"]
    assert saida["observacao_montada"] == (
        "Boa execucao dos Kihons; Dificuldade no Kata")


def test_merge_no_json_sem_marcacoes():
    """Sem observações marcadas, montada fica vazia e marcadas vazia."""
    resultado = {"aluno": {"id": "A01"}, "observacoes_marcadas": []}
    saida = observacoes.merge_no_json(resultado)
    assert saida["observacoes_marcadas"] == []
    assert saida["observacao_montada"] == ""