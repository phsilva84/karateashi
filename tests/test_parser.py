"""tests/test_parser.py — Testes do parser de fallback TXT v2.0 (Fase 02).

Cobre os critérios de aceite:
- parse válido com frequências por repetição de código;
- código fora do intervalo rejeitado com aviso no log (sem abortar o arquivo);
- observações granulares (uma por quesito) capturadas nos campos corretos;
- cabeçalho (exame, dojo, avaliador, aluno, faixa) parseado corretamente.
"""
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.parser import (  # noqa: E402
    _extrair_codigos,
    carregar_criterios,
    parse_arquivo,
    parse_bloco,
)

BLOCO_VALIDO = """\
EXAME: EXA-D01-2026-02
DOJO: D01
AVALIADOR: S01
ALUNO: A01 | Isabelly Santos
FAIXA: BRANCA -> AMARELA
KIHON: cod:1,1,1,2,4
Observação Kihon: Corrigir largura no Zenkutsu-dachi.
KATA: cod:2,5
Observação Kata: Boa velocidade, ajustar rotação.
BUNKAI: cod:7
Observação Bunkai: Distância muito curta na aplicação.
KUMITE: cod:3
Observação Kumite: Manter guarda alta durante esquivas.
"""

@pytest.fixture
def base_cfg(tmp_path: Path) -> Path:
    """Config mínima da Fase 00: Kihon 1-6, Kata 1-8, Bunkai 1-8, Kumite 1-7."""
    cfg = {
        "quesitos": {
            "kihon": {"criterios": [{} for _ in range(6)]},
            "kata": {"criterios": [{} for _ in range(8)]},
            "bunkai": {"criterios": [{} for _ in range(8)]},
            "kumite": {"criterios": [{} for _ in range(7)]},
        }
    }
    (tmp_path / "criterios_por_quesito.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path

def test_carregar_criterios(base_cfg: Path) -> None:
    max_codigos = carregar_criterios(base_cfg)
    assert max_codigos == {"kihon": 6, "kata": 8, "bunkai": 8, "kumite": 7}

def test_parse_valido(base_cfg: Path) -> None:
    max_codigos = carregar_criterios(base_cfg)
    resultado = parse_bloco(BLOCO_VALIDO, max_codigos)

    # Cabeçalho
    assert resultado["metadados"]["versao_schema"] == "2.0"
    assert resultado["metadados"]["exame_id"] == "EXA-D01-2026-02"
    assert resultado["metadados"]["dojo_id"] == "D01"
    assert resultado["metadados"]["avaliador_id"] == "S01"
    assert resultado["aluno"]["id"] == "A01"
    assert resultado["aluno"]["nome"] == "Isabelly Santos"
    assert resultado["aluno"]["faixa_atual"] == "BRANCA"
    assert resultado["aluno"]["faixa_pretendida"] == "AMARELA"

    # Frequência por repetição de código
    kihon = resultado["avaliacoes"]["kihon"]["frequencias"]
    assert kihon["base_incorreta"] == 3              # cod:1,1,1
    assert kihon["execucao_tecnica_incorreta"] == 1  # cod:2
    assert kihon["falta_foco"] == 1                  # cod:4

    kata = resultado["avaliacoes"]["kata"]["frequencias"]
    assert kata["base_incorreta"] == 1               # cod:2
    assert kata["execucao_tecnica_incorreta"] == 1   # cod:5

    bunkai = resultado["avaliacoes"]["bunkai"]["frequencias"]
    assert bunkai["distancia_inadequada"] == 1       # cod:7

    kumite = resultado["avaliacoes"]["kumite"]["frequencias"]
    assert kumite["perda_equilibrio"] == 1           # cod:3

def test_observacoes_granulares(base_cfg: Path) -> None:
    max_codigos = carregar_criterios(base_cfg)
    resultado = parse_bloco(BLOCO_VALIDO, max_codigos)
    av = resultado["avaliacoes"]
    assert av["kihon"]["observacao"] == "Corrigir largura no Zenkutsu-dachi."
    assert av["kata"]["observacao"] == "Boa velocidade, ajustar rotação."
    assert av["bunkai"]["observacao"] == "Distância muito curta na aplicação."
    assert av["kumite"]["observacao"] == "Manter guarda alta durante esquivas."

def test_codigo_invalido_rejeita_linha_sem_abortar(
    base_cfg: Path, caplog: pytest.LogCaptureFixture
) -> None:
    max_codigos = carregar_criterios(base_cfg)
    bloco = BLOCO_VALIDO.replace("KIHON: cod:1,1,1,2,4", "KIHON: cod:1,7,2")
    with caplog.at_level(logging.WARNING, logger="karate-ashi.parser"):
        resultado = parse_bloco(bloco, max_codigos)

    kihon = resultado["avaliacoes"]["kihon"]["frequencias"]
    assert kihon["base_incorreta"] == 1              # cod:1 válido
    assert kihon["execucao_tecnica_incorreta"] == 1  # cod:2 válido
    assert "fora do intervalo" in caplog.text
    # O resto do bloco não foi abortado
    assert resultado["avaliacoes"]["kata"]["frequencias"]["base_incorreta"] == 1

def test_extrair_codigos_vazio() -> None:
    assert _extrair_codigos("") == []

def test_extrair_codigos_invalido() -> None:
    with pytest.raises(ValueError, match="código inválido"):
        _extrair_codigos("1,a,3")

def test_parse_arquivo(base_cfg: Path, tmp_path: Path) -> None:
    txt = tmp_path / "exemplo_fallback_v2.txt"
    txt.write_text("---\n" + BLOCO_VALIDO + "\n---\n", encoding="utf-8")
    resultados = parse_arquivo(txt, base_cfg)
    assert len(resultados) == 1
    assert resultados[0]["aluno"]["nome"] == "Isabelly Santos"
    assert resultados[0]["aluno"]["faixa_pretendida"] == "AMARELA"