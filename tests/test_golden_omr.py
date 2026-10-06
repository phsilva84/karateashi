"""tests/test_golden_omr.py — Regressão da LEITURA OMR contra a verdade manual.
Fonte da verdade: marcações conferidas à mão pelo Sensei Paulo em 5 páginas
do exame EXA-D01-2026-10 (quesito KIHON).
IMPORTANTE: cada célula da verdade está VINCULADA ao scan físico em que foi
validada. Há múltiplos scans da MESMA folha (original 03/10 + re-scans 04/10
e 05/10) e o teste NÃO pode depender de 'primeiro scan com o aluno'.
Presença: W06 (Sophia, folha em branco) NUNCA pode sair PRESENTE em NENHUM scan.
Como rodar (local, antes de qualquer commit):
  $env:KARATE_SCANS = "G:/Meu Drive/documentos/KarateAshi_Exames/scans"
  python -m pytest tests/test_golden_omr.py -v
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parent.parent
_SCANS = Path(os.environ.get("KARATE_SCANS", _RAIZ / "scans"))
_CONFIG = _RAIZ / "config"

# (avaliador, aluno) -> (scan_validado, verdade_kihon)
KIHON_VERDADE: dict[tuple[str, str], tuple[str, dict[str, int]]] = {
    ("S03", "W04"): ("img20261004_00471691.png",
        {"base_incorreta": 2, "execucao_tecnica_incorreta": 3,
         "perda_equilibrio": 2, "ausencia_kiai": 1}),
    ("S03", "W05"): ("img20261004_00471691.png",
        {"base_incorreta": 4, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 1, "falta_foco": 1,
         "perda_equilibrio": 4, "ausencia_kiai": 2}),
    ("S04", "W10"): ("img20261003_22053521.png",
        {"base_incorreta": 2, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 1, "perda_equilibrio": 3}),
    ("S04", "W11"): ("img20261003_22053521.png",
        {"base_incorreta": 2, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 1, "falta_foco": 1,
         "perda_equilibrio": 3, "ausencia_kiai": 1}),
    ("S04", "W07"): ("img20261003_22032837.png",
        {"base_incorreta": 2, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 2, "falta_foco": 3,
         "perda_equilibrio": 2}),
    ("S04", "W08"): ("img20261003_22032837.png",
        {"base_incorreta": 1, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 1, "falta_foco": 3,
         "perda_equilibrio": 2}),
    ("S04", "W09"): ("img20261003_22032837.png",
        {"base_incorreta": 3, "execucao_tecnica_incorreta": 4,
         "movimento_sem_carga": 2, "falta_foco": 4,
         "perda_equilibrio": 2, "ausencia_kiai": 2}),
    ("S02", "W01"): ("img20261003_22490841.png",
        {"execucao_tecnica_incorreta": 2, "movimento_sem_carga": 2,
         "falta_foco": 1, "perda_equilibrio": 1}),
    ("S02", "W02"): ("img20261003_22490841.png",
        {"execucao_tecnica_incorreta": 3, "movimento_sem_carga": 3,
         "perda_equilibrio": 2}),
    ("S02", "W03"): ("img20261003_22490841.png",
        {"base_incorreta": 2, "execucao_tecnica_incorreta": 3,
         "movimento_sem_carga": 3, "perda_equilibrio": 2}),
    ("S02", "W07"): ("img20261003_22263733.png",
        {"execucao_tecnica_incorreta": 3, "movimento_sem_carga": 2,
         "falta_foco": 1, "perda_equilibrio": 2, "ausencia_kiai": 1}),
    ("S02", "W08"): ("img20261003_22263733.png",
        {"execucao_tecnica_incorreta": 3, "movimento_sem_carga": 1,
         "perda_equilibrio": 1, "ausencia_kiai": 2}),
    ("S02", "W09"): ("img20261003_22263733.png",
        {"execucao_tecnica_incorreta": 2, "movimento_sem_carga": 1,
         "falta_foco": 1, "perda_equilibrio": 2, "ausencia_kiai": 2}),
}

# W06 (Sophia): presença nunca PRESENTE em NENHUM scan (folha em branco)
AUSENTE_SEMPRE = {"W06"}


@lru_cache(maxsize=None)
def _ler_scan(nome: str) -> dict:
    """Lê UM arquivo de scan uma única vez e indexa por aluno (cacheado)."""
    from core import omr_reader
    try:
        res = omr_reader.processar_imagem(_SCANS / nome, base_cfg=_CONFIG,
                                          origem="scanner")
    except Exception as exc:  # noqa: BLE001
        return {"__erro__": str(exc)}
    return {
        r["metadados"]["aluno_id"]: {
            "presenca": r["presenca"],
            **{q: dict(r["avaliacoes"][q]["frequencias"])
               for q in r["avaliacoes"]},
        }
        for r in res
    }


@pytest.mark.skipif(not _SCANS.is_dir(),
                    reason="Defina KARATE_SCANS para o diretório de scans")
class TestGoldenKihon:
    @pytest.mark.parametrize("av,aluno,scan,esperado", [
        pytest.param(av, aluno, scan, esperado,
                     id=f"{av}_{aluno}_{scan[:16]}")
        for (av, aluno), (scan, esperado) in sorted(KIHON_VERDADE.items())
    ])
    def test_kihon_por_celula(self, av, aluno, scan, esperado):
        arq = _SCANS / scan
        assert arq.is_file(), f"scan validado ausente: {scan}"
        leitura = _ler_scan(scan)[aluno]["kihon"]
        assert leitura == esperado, (
            f"{av}/{aluno} (scan {scan}): leitura {leitura} "
            f"!= verdade manual {esperado}"
        )


@pytest.mark.skipif(not _SCANS.is_dir(),
                    reason="Defina KARATE_SCANS para o diretório de scans")
class TestPresenca:
    @pytest.mark.parametrize("aluno", sorted(AUSENTE_SEMPRE))
    def test_ausencia_em_todos_os_scans(self, aluno):
        achou = False
        for p in sorted(_SCANS.glob("*.png")):
            dados = _ler_scan(p.name)
            if "__erro__" in dados or aluno not in dados:
                continue
            achou = True
            assert dados[aluno]["presenca"] == "AUSENTE", (
                f"{p.name}: {aluno} leu {dados[aluno]['presenca']} "
                "(falso positivo de presença na folha em branco)"
            )
        assert achou, f"nenhum scan com {aluno} encontrado"