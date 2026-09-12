"""tests/test_parser.py — Testes do parser de fallback TXT v2.0 (Fase 02).

Cobre os critérios de aceite:
- parse válido com frequências por repetição de código;
- código fora do intervalo rejeitado com aviso no log (sem abortar o arquivo);
- observações granulares (uma por quesito) capturadas nos campos corretos;
- cabeçalho (exame, dojo, avaliador, aluno, faixa) parseado corretamente.

Fase 06 (multi-faixa): o parser lê config/faixas/<faixa>.json e
carregar_criterios exige a faixa. O fixture base_cfg grava faixas/branca.json
com os critérios na ordem da tabela v2.0 — o código de falha é o campo
'codigo' (1-based) de cada critério.
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

FAIXA_TESTE = "branca"

# Ordem dos critérios na tabela v2.0. O 'codigo' é a posição (1-based).
CRITERIOS_V2 = {
    "kihon": [
        "base_incorreta",
        "execucao_tecnica_incorreta",
        "movimento_sem_carga",
        "falta_foco",
        "perda_equilibrio",
        "ausencia_kiai",
    ],
    "kata": [
        "embusen_incorreto",
        "base_incorreta",
        "falta_ritmo",
        "ausencia_kiai",
        "execucao_tecnica_incorreta",
        "movimento_sem_carga",
        "falta_foco",
        "perda_equilibrio",
    ],
    "bunkai": [
        "base_incorreta",
        "ausencia_kiai",
        "execucao_tecnica_incorreta",
        "movimento_sem_carga",
        "falta_foco",
        "perda_equilibrio",
        "distancia_inadequada",
        "falta_controle",
    ],
    "kumite": [
        "movimento_sem_carga",
        "falta_foco",
        "perda_equilibrio",
        "ausencia_kiai",
        "distancia_inadequada",
        "falta_combatividade",
        "falta_controle",
    ],
}

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
    """Config no layout multi-faixa (Fase 06): config/faixas/<faixa>.json.

    Antes o fixture escrevia criterios_por_quesito.json na raiz (layout
    Fase 00), que o parser não lê mais. Agora grava faixas/branca.json com
    os critérios na ordem da tabela v2.0 — o parser mapeia código -> chave
    pelo campo 'codigo' (1-based) de cada critério.
    """
    cfg = {
        "faixa": FAIXA_TESTE,
        "quesitos": {
            q: {"criterios": [
                {"codigo": i, "chave": ch, "nome": ch, "peso": 1.0}
                for i, ch in enumerate(chaves, start=1)
            ]}
            for q, chaves in CRITERIOS_V2.items()
        },
    }
    destino = tmp_path / "faixas"
    destino.mkdir(parents=True)
    (destino / f"{FAIXA_TESTE}.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path

def test_carregar_criterios(base_cfg: Path) -> None:
    criterios = carregar_criterios(base_cfg, FAIXA_TESTE)
    assert {q: criterios[q]["total"] for q in criterios} == {
        "kihon": 6, "kata": 8, "bunkai": 8, "kumite": 7}

def test_parse_valido(base_cfg: Path) -> None:
    criterios = carregar_criterios(base_cfg, FAIXA_TESTE)
    resultado = parse_bloco(BLOCO_VALIDO, criterios)

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
    criterios = carregar_criterios(base_cfg, FAIXA_TESTE)
    resultado = parse_bloco(BLOCO_VALIDO, criterios)
    av = resultado["avaliacoes"]
    assert av["kihon"]["observacao"] == "Corrigir largura no Zenkutsu-dachi."
    assert av["kata"]["observacao"] == "Boa velocidade, ajustar rotação."
    assert av["bunkai"]["observacao"] == "Distância muito curta na aplicação."
    assert av["kumite"]["observacao"] == "Manter guarda alta durante esquivas."

def test_codigo_invalido_rejeita_linha_sem_abortar(
    base_cfg: Path, caplog: pytest.LogCaptureFixture
) -> None:
    criterios = carregar_criterios(base_cfg, FAIXA_TESTE)
    bloco = BLOCO_VALIDO.replace("KIHON: cod:1,1,1,2,4", "KIHON: cod:1,7,2")
    with caplog.at_level(logging.WARNING, logger="karate-ashi.parser"):
        resultado = parse_bloco(bloco, criterios)

    kihon = resultado["avaliacoes"]["kihon"]["frequencias"]
    assert kihon["base_incorreta"] == 1              # cod:1 válido
    assert kihon["execucao_tecnica_incorreta"] == 1  # cod:2 válido
    assert "fora da tabela" in caplog.text
    assert resultado["dados_legados"] is True
    assert resultado["codigos_descartados"]["kihon"] == [7]
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