"""tests/test_pipeline_integracao.py — OMR → agregação → engine (CI)."""
import json
from pathlib import Path

import pytest

from core.pipeline import (
    agregar_por_aluno,
    carregar_jsons_omr,
    converter_frequencias_omr,
    montar_lote_engine,
    processar_folhas_omr,
)


def _folha(aluno="A01", avaliador="S01", faixa="branca",
           frequencias=None, origem="scanner", presenca="PRESENTE"):
    """Monta um JSON de folha idêntico ao que o ingest_folhas grava.

    presenca="PRESENTE" por padrão: a regra de negócio trata presença não
    marcada como AUSENTE (sem avaliar frequências). Passar presenca="AUSENTE"
    para testar o cenário de ausência.
    """
    return {
        "metadados": {"aluno_id": aluno, "avaliador_id": avaliador,
                      "faixa": faixa, "exame_id": "EXA-TESTE-2026"},
        "aluno": {"id": aluno, "faixa_atual": faixa.upper()},
        "presenca": presenca,
        "avaliacoes": {
            q: {"frequencias": (frequencias or {}).get(q, {}),
                "observacao": ""}
            for q in ["kihon", "kata", "bunkai", "kumite"]
        },
        "observacoes_marcadas": [],
        "observacao_montada": "",
        "origem": origem,
    }


def _gravar(pasta, folha):
    """Grava uma folha como JSON na pasta (nome no padrão do ingest)."""
    caminho = pasta / f"folha_{folha['metadados']['avaliador_id']}.json"
    caminho.write_text(json.dumps(folha), encoding="utf-8")
    return caminho


def test_converter_posicao_para_criterio_pela_matriz():
    """A posição N da leitura vira o critério N da matriz (nunca por shift).

    Usa modo_presenca=False para isolar o mapeamento posicional (a contagem
    bruta é preservada). O default do pipeline é modo_presenca=True (presença).
    """
    folha = {"avaliacoes": {"kihon": {"frequencias": {"c1": 2, "c3": 1}}}}
    matriz = {"quesitos": {"kihon": {"criterios": [
        {"chave": "base_incorreta"},
        {"chave": "execucao_tecnica_incorreta"},
        {"chave": "movimento_sem_carga"},
    ]}}}
    convertidas = converter_frequencias_omr(folha, matriz,
                                            modo_presenca=False)
    assert convertidas["kihon"] == {
        "base_incorreta": 2, "movimento_sem_carga": 1}


def test_converter_posicao_para_criterio_modo_presenca():
    """Default (modo_presenca=True): qualquer balão marcado conta como 1."""
    folha = {"avaliacoes": {"kihon": {"frequencias": {"c1": 2, "c3": 1}}}}
    matriz = {"quesitos": {"kihon": {"criterios": [
        {"chave": "base_incorreta"},
        {"chave": "execucao_tecnica_incorreta"},
        {"chave": "movimento_sem_carga"},
    ]}}}
    convertidas = converter_frequencias_omr(folha, matriz)
    assert convertidas["kihon"] == {
        "base_incorreta": 1, "movimento_sem_carga": 1}


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


def test_pipeline_omr_para_engine_sem_faltas(tmp_path, base_cfg):
    """3 avaliadores presentes, sem marcações → 100,0 e APROVADO."""
    for i in (1, 2, 3):
        _gravar(tmp_path, _folha("A01", f"S0{i}"))
    resultados = processar_folhas_omr(tmp_path, base_cfg)
    assert len(resultados) == 1
    assert resultados[0]["aluno_id"] == "A01"
    assert resultados[0]["nota_final"] == 100.0
    assert resultados[0]["status"] == "APROVADO"
    assert resultados[0]["origens"] == ["scanner", "scanner", "scanner"]


def test_pipeline_omr_para_engine_com_faltas(tmp_path, base_cfg):
    """1 avaliador presente marca 'c1' no kihon → nota do kihon desconta.

    Interpretação B (presença): c1:2 vira 1 ocorrência do critério
    base_incorreta (peso 1.0) → fc = 1.0 e nota do kihon < 25,0.
    """
    _gravar(tmp_path, _folha("A01", "S01",
                             frequencias={"kihon": {"c1": 2}}))
    resultados = processar_folhas_omr(tmp_path, base_cfg)
    kihon = resultados[0]["quesitos"]["kihon"]
    assert kihon["nota"] < 25.0
    assert sum(d["fc"] for d in kihon["detalhes"].values()) == 1.0


def test_pipeline_omr_para_engine_ausente(tmp_path, base_cfg):
    """Presença não marcada → AUSENTE, sem avaliar frequências.

    Mesmo com marcações, o aluno ausente não pode receber nota.
    """
    _gravar(tmp_path, _folha("A01", "S01",
                             frequencias={"kihon": {"c1": 2}},
                             presenca="AUSENTE"))
    resultados = processar_folhas_omr(tmp_path, base_cfg)
    assert len(resultados) == 1
    assert resultados[0]["status"] == "AUSENTE"
    assert resultados[0]["nota_final"] == 0.0
    assert resultados[0]["quesitos"] == {}


def test_pipeline_omr_para_engine_consenso_3_avaliadores(tmp_path, base_cfg):
    """3 avaliadores com as mesmas marcações → consenso perfeito (fc igual)."""
    for i in (1, 2, 3):
        _gravar(tmp_path, _folha("A01", f"S0{i}",
                                 frequencias={"kihon": {"c1": 2},
                                              "kata": {"c2": 1}}))
    resultados = processar_folhas_omr(tmp_path, base_cfg)
    assert len(resultados) == 1
    assert resultados[0]["origens"] == ["scanner", "scanner", "scanner"]
    kihon = resultados[0]["quesitos"]["kihon"]
    # Interpretação B: cada avaliador contribui 1 (presença) → fc = média 1.0
    assert kihon["detalhes"]["base_incorreta"]["fc"] == 1.0
    assert kihon["detalhes"]["base_incorreta"]["marcacoes"] == [1, 1, 1]