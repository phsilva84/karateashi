"""tests/test_observacoes.py — Captura digital das observações (v2.0).

Contrato: o parâmetro `base` de carregar()/merge_no_json() é a RAIZ da
pasta de observações (equivalente a data/observacoes). O caminho completo
é <base>/<exame>/<avaliador>.csv. Os testes criam os arquivos nesse
formato, com tmp_path como raiz.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.observacoes import QUESITOS, carregar, merge_no_json

def test_carregar_ignora_csv_inexistente(tmp_path):
    assert carregar("EXA-001", "S01", tmp_path) == {}

def test_carregar_lida_com_bom_do_excel(tmp_path):
    """O cenário que motivou a correção: BOM real (EF BB BF), como o Excel grava."""
    caminho = tmp_path / "EXA-001" / "S01.csv"
    caminho.parent.mkdir(parents=True)
    caminho.write_bytes(
        b"\xef\xbb\xbfaluno_id,nome,kihon,kata,bunkai,kumite\n"
        b"A01,Isabelly,Chutes firmes.,,,\n"
    )
    obs = carregar("EXA-001", "S01", tmp_path)
    assert obs["A01"]["kihon"] == "Chutes firmes."

def test_carregar_lida_sem_bom(tmp_path):
    """utf-8-sig também lê arquivos sem BOM — não quebra o fluxo antigo."""
    caminho = tmp_path / "EXA-001" / "S01.csv"
    caminho.parent.mkdir(parents=True)
    caminho.write_text(
        "aluno_id,nome,kihon,kata,bunkai,kumite\n"
        "A02,Nicole,,Boa concentração,,\n",
        encoding="utf-8",
    )
    obs = carregar("EXA-001", "S01", tmp_path)
    assert obs["A02"]["kata"] == "Boa concentração"

def test_merge_no_json_preenche_observacoes(tmp_path):
    caminho = tmp_path / "EXA-001" / "S01.csv"
    caminho.parent.mkdir(parents=True)
    caminho.write_text(
        "aluno_id,nome,kihon,kata,bunkai,kumite\n"
        "A01,Isabelly,Chutes firmes.,,,\n",
        encoding="utf-8",
    )
    resultado = {
        "metadados": {"exame_id": "EXA-001", "avaliador_id": "S01"},
        "aluno": {"id": "A01"},
        "avaliacoes": {q: {"frequencias": {}, "observacao": ""} for q in QUESITOS},
    }
    merge_no_json(resultado, tmp_path)
    assert resultado["avaliacoes"]["kihon"]["observacao"] == "Chutes firmes."
    assert resultado["avaliacoes"]["kata"]["observacao"] == ""