"""tests/test_pipeline_integracao.py — OMR → agregação → engine (CI)."""

import json

import pytest

from core.pipeline import (
    agregar_por_aluno,
    carregar_jsons_omr,
    converter_frequencias_omr,
    montar_lote_engine,
    processar_folhas_omr,
)


def _folha(aluno="A01", avaliador="S01", faixa="branca",
           frequencias=None, origem="scanner"):
    """Monta um JSON de folha idêntico ao que o ingest_folhas grava."""
    return {
        "metadados": {"aluno_id": aluno, "avaliador_id": avaliador,
                      "faixa": faixa, "exame_id": "EXA-TESTE-2026"},
        "aluno": {"id": aluno, "faixa_atual": faixa.upper()},
        "avaliacoes": {
            q: {"frequencias": dict(frequencias or {}), "observacao": ""}
            for q in ["kihon", "kata", "bunkai", "kumite"]
        },
        "observacoes_marcadas": [],
        "observacao_montada": "",
        "origem": origem,
    }


def test_converter_posicao_para_criterio_pela_matriz():
    """A posição N da leitura vira o critério N da matriz (nunca por shift)."""
    folha = {"avaliacoes": {"kihon": {"frequencias": {"c1": 2, "c3": 1}}}}
    matriz = {"quesitos": {"kihon": {"criterios": [
        {"chave": "base_incorreta"},
        {"chave": "execucao_tecnica_incorreta"},
        {"chave": "movimento_sem_carga"},
    ]}}}
    convertidas = converter_frequencias_omr(folha, matriz)
    assert convertidas["kihon"] == {
        "base_incorreta": 2,
        "movimento_sem_carga": 1,
    }


def test_carregar_jsons_omr_ignora_resumo(tmp_path):
    for nome in ("A01_S01.json", "A01_S02.json", "resumo_ingestao.json"):
        (tmp_path / nome).write_text(
            json.dumps({"aluno": {"id": "A01"}}), encoding="utf-8")
    carregados = carregar_jsons_omr(tmp_path)
    assert len(carregados) == 2


def test_agregar_por_aluno(tmp_path):
    folhas = [_folha("A01", "S01"), _folha("A01", "S02"),
              _folha("A02", "S01")]
    grupos = agregar_por_aluno(folhas)
    assert set(grupos) == {"A01", "A02"}
    assert len(grupos["A01"]) == 2


def test_pipeline_omr_para_engine_sem_faltas(base_cfg):
    """3 avaliadores sem marcações → 100,0 e APROVADO."""
    folhas = [_folha("A01", f"S0{i}") for i in (1, 2, 3)]
    for f in folhas:
        (tmp := __import__("tempfile").mkdtemp())
    import shutil
    from pathlib import Path
    pasta = Path(tmp)
    for f in folhas:
        (pasta / f"folha_{f['metadados']['avaliador_id']}.json").write_text(
            json.dumps(f), encoding="utf-8")
    resultados = processar_folhas_omr(pasta, base_cfg)
    shutil.rmtree(pasta, ignore_errors=True)
    assert len(resultados) == 1
    assert resultados[0]["aluno_id"] == "A01"
    assert resultados[0]["nota_final"] == 100.0
    assert resultados[0]["status"] == "APROVADO"
    assert resultados[0]["origens"] == ["scanner", "scanner", "scanner"]


def test_pipeline_omr_para_engine_com_faltas(base_cfg):
    """1 avaliador marca 'c1' no kihon → a nota do kihon desconta (< 25,0)."""
    folha = _folha("A01", "S01",
                   frequencias={"kihon": {"c1": 2}})
    resultados = processar_folhas_omr(
        _escoar(folha), base_cfg)  # ver helper abaixo
    kihon = resultados[0]["quesitos"]["kihon"]
    assert kihon["nota"] < 25.0
    assert sum(d["fc"] for d in kihon["detalhes"].values()) == 2.0