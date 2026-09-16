# tests/test_contradicoes_merge.py
"""Fase 3 (item 7): pares customizados SÃO UNIDOS aos padrão (não substituem)."""
import json
from pathlib import Path

from core.contradicoes import PARES_PADRAO, carregar_pares

def _escrever_pares(tmp_path: Path, pares: list[dict]) -> Path:
    caminho = tmp_path / "observacoes_contradicoes.json"
    caminho.write_text(
        json.dumps({"pares": pares}, ensure_ascii=False), encoding="utf-8")
    return caminho

def test_pares_custom_se_somam_aos_padrao(tmp_path: Path):
    extra = {"topico": "kumite", "otimo": "obs_p3", "melhorar": "obs_m5"}
    _escrever_pares(tmp_path, [extra])
    pares = carregar_pares(tmp_path)
    chaves = {(p["otimo"], p["melhorar"]) for p in pares}
    assert len(pares) == len(PARES_PADRAO) + 1
    assert (extra["otimo"], extra["melhorar"]) in chaves
    for p in PARES_PADRAO:  # todos os padrão continuam presentes
        assert (p["otimo"], p["melhorar"]) in chaves

def test_pares_custom_redefinem_mesma_chave_sem_duplicar(tmp_path: Path):
    base = PARES_PADRAO[0]  # redefine o 1º par padrão, mesmas chaves
    redefine = {
        "topico": base["topico"] + " (ajustado)",
        "otimo": base["otimo"],
        "melhorar": base["melhorar"],
    }
    _escrever_pares(tmp_path, [redefine])
    pares = carregar_pares(tmp_path)
    assert len(pares) == len(PARES_PADRAO)  # sem duplicar
    achado = next(p for p in pares
                  if p["otimo"] == base["otimo"]
                  and p["melhorar"] == base["melhorar"])
    assert achado["topico"] == redefine["topico"]  # versão custom prevalece

def test_sem_arquivo_custom_retorna_padrao(tmp_path: Path):
    assert carregar_pares(tmp_path) == PARES_PADRAO