"""tests/test_observacoes.py — Observações estruturadas (v2col-2.8).

Cobre o vocabulário oficial (16 chaves), a montagem do texto legível
(montar_observacao) e a integração com o JSON do OMR (merge_no_json).
O fluxo antigo de CSV (carregar/gerar_templates/consolidar) foi removido
e não é mais testado.

Ordem canônica das chaves brutas: 'Ótimo!' (obs_p*) antes de
'A Melhorar' (obs_m*), cada coluna na ordem impressa na folha.
"""
from __future__ import annotations

from core import observacoes

def test_vocabulario_completo():
    """As 16 chaves oficiais existem e não se sobrepõem."""
    positivas = set(observacoes.OBS_POSITIVAS)
    melhorar = set(observacoes.OBS_MELHORAR)
    assert len(positivas) == 8
    assert len(melhorar) == 8
    assert positivas.isdisjoint(melhorar)
    assert all(c.startswith("obs_p") for c in positivas)
    assert all(c.startswith("obs_m") for c in melhorar)

def test_vocabulario_chaves_sequenciais():
    """Chaves obs_p1..p8 e obs_m1..m8 sequenciais (contrato ROIs)."""
    assert set(observacoes.OBS_POSITIVAS) == {f"obs_p{i}" for i in range(1, 9)}
    assert set(observacoes.OBS_MELHORAR) == {f"obs_m{i}" for i in range(1, 9)}

def test_montar_observacao_vazio():
    assert observacoes.montar_observacao([]) == ""

def test_montar_observacao_so_positivas():
    texto = observacoes.montar_observacao(["obs_p3", "obs_p1"])
    assert texto == "Ótimo! Boa execução técnica; Bom controle de distância"

def test_montar_observacao_so_melhorar():
    texto = observacoes.montar_observacao(["obs_m6", "obs_m2"])
    assert texto == ("A melhorar: Dificuldade nas Transições de Bases; "
                     "Erros Técnicos Constantes")

def test_montar_observacao_misto():
    texto = observacoes.montar_observacao(["obs_m2", "obs_p1"])
    assert texto == ("Ótimo! Boa execução técnica. A melhorar: "
                     "Dificuldade nas Transições de Bases")

def test_montar_observacao_ordem():
    """Ótimo! sempre antes de A melhorar; dentro da coluna, ordem da folha."""
    texto = observacoes.montar_observacao(["obs_m8", "obs_m1", "obs_p7", "obs_p2"])
    assert texto == ("Ótimo! Ótima base / postura; Ótima Execução do Kata. "
                     "A melhorar: Melhorar bases / postura; "
                     "Dificuldade na execução de Kihons")

def test_montar_observacao_ignora_chaves_desconhecidas():
    texto = observacoes.montar_observacao(["obs_p1", "obs_x99", "obs_outro_p"])
    assert texto == "Ótimo! Boa execução técnica"

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
        "Ótimo! Boa execução técnica. A melhorar: "
        "Dificuldade nas Transições de Bases"
    )

def test_merge_no_json_sem_marcadas():
    saida = observacoes.merge_no_json({"metadados": {}})
    assert saida["observacoes_marcadas"] == []
    assert saida["observacao_montada"] == ""