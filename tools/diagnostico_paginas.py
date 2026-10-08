"""tools/diagnostico_paginas.py — Diagnóstico do deslize de 1 linha.
Uso: python tools/diagnostico_paginas.py [pasta_scans]
Para cada scan, lê com o leitor ATUAL e imprime, por aluno:
  - presença; offset dx/dy escolhido (seed QR, grade, linha) e incidentes;
  - Kihon lido vs verdade manual; ✅/❌.
Rode sobre TODOS os scans e veja EXATAMENTE quais arquivos falham e com qual dy.
"""
from __future__ import annotations

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ))

from tests.test_golden_omr import KIHON_VERDADE  # noqa: E402
from core import omr_reader  # noqa: E402


def main() -> None:
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path("G:/Meu Drive/documentos/KarateAshi_Exames/scans"))
    total = ok = falhas = 0
    for p in sorted(pasta.glob("*.png")):
        try:
            res = omr_reader.processar_imagem(p, base_cfg=_RAIZ / "config",
                                              origem="scanner")
        except Exception as e:
            print(f"[ERRO] {p.name}: {e}")
            continue
        for r in res:
            md = r.get("metadados", {})
            chave = (md.get("avaliador_id"), md.get("aluno_id"))
            esperado = KIHON_VERDADE.get(chave)
            if esperado is None:
                continue
            total += 1
            lido = dict(r.get("avaliacoes", {}).get("kihon", {})
                        .get("frequencias", {}) or {})
            inc = [i for i in r.get("incidentes_auditoria", [])
                   if "calibracao" in i or "alinhamento" in i]
            status = "OK " if lido == esperado else "FAIL"
            if lido == esperado:
                ok += 1
            else:
                falhas += 1
                print(f"[{status}] {p.name} | {chave[0]}/{chave[1]} | "
                      f"pres={r.get('presenca')} | inc={inc}")
                print(f"        lido     : {lido}")
                print(f"        esperado : {esperado}")
    print(f"\nResumo: {ok}/{total} células de Kihon conferem | falhas: {falhas}")


if __name__ == "__main__":
    main()