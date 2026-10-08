#!/usr/bin/env python3
"""tools/gerar_relatorios_rapido.py — Regenera os relatórios (master + sensei +
individuais) a partir dos JSONs OMR já ingeridos, SEM reler scans nem rodar o
ingest. Cada exame é processado INDEPENDENTEMENTE e gravado no seu próprio
diretório, como se o run do workflow tivesse rodado:
    output/distribuicao/master/EXA-<id>/relatorio_master_...html
    output/distribuicao/senseis/<Sensei>/EXA-<id>/...

Uso:
    python tools/gerar_relatorios_rapido.py ^
        --omr output/omr/EXA-D01-2026-10 output/omr/EXA-D02-2026-10 ^
        --config config --data data --output output [--so-master]

Cada pasta em --omr = UM exame (sem resumo_ingestao.json). Sem --so-master,
gera também sensei + individuais por exame.
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.config import carregar_json  # noqa: E402
from core.relatorio_html import salvar_html_master  # noqa: E402
from core.pipeline import (  # noqa: E402
    _carregar_avaliadores, _carregar_nomes, _carregar_senseis_por_dojo,
    _extrair_metadados_exame, _slug, carregar_jsons_omr,
    gerar_relatorios_html, processar_folhas_omr,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--omr", nargs="+", type=Path, required=True,
                    help="pastas com JSONs OMR (uma por exame)")
    ap.add_argument("--config", type=Path, default=RAIZ / "config")
    ap.add_argument("--data", type=Path, default=RAIZ / "data")
    ap.add_argument("--output", type=Path, default=RAIZ / "output")
    ap.add_argument("--so-master", action="store_true",
                    help="gera somente o master de cada exame (mais rápido)")
    args = ap.parse_args()

    cfg = args.config
    cadastro = (args.data / "cadastro") if (args.data / "cadastro").is_dir() else args.data
    regras = carregar_json(cfg / "regras_gerais.json")
    recomendacoes = carregar_json(cfg / "recomendacoes.json")
    nomes = _carregar_nomes(cadastro)
    senseis = _carregar_senseis_por_dojo(cfg)
    avaliadores = _carregar_avaliadores(cadastro, cfg)

    staging = args.output / "distribuicao"
    for omr in args.omr:
        if not omr.is_dir():
            print(f"[ERRO] pasta OMR não encontrada: {omr}")
            return 2
        folhas = carregar_jsons_omr(omr)
        if not folhas:
            print(f"[AVISO] nenhum JSON OMR em {omr} — pulando")
            continue
        exame_id, dojo_id, av_id = _extrair_metadados_exame(folhas)
        resultados = processar_folhas_omr(omr, cfg)
        # UM master por exame, no seu próprio diretório (como o workflow)
        dojos = [{"dojo_id": dojo_id, "alunos": resultados}]
        sensei = (senseis.get(dojo_id) or avaliadores.get(av_id) or av_id or "")
        print(f"[INFO] {exame_id} | {dojo_id} | alunos: {len(resultados)}")

        # --- Master do exame (v3.0 analítico) ----------------------------
        master_pasta = staging / "master" / exame_id
        master_pasta.mkdir(parents=True, exist_ok=True)
        p_master = salvar_html_master(
            dojos, regras, recomendacoes,
            master_pasta / f"relatorio_master_{exame_id}.html",
            exame_id=exame_id,
            titulo=f"Relatório Master Consolidado — {exame_id}",
            nomes=nomes, avaliadores_map=avaliadores,
        )
        print(f"[OK] Master: {p_master}")

        # --- Sensei + individuais do exame (opcional) --------------------
        if not args.so_master:
            rel_dir = args.output / "relatorios" / exame_id
            rel_dir.mkdir(parents=True, exist_ok=True)
            gerar_relatorios_html(resultados, regras, recomendacoes,
                                  exame_id, dojo_id, rel_dir,
                                  nomes=nomes, sensei_responsavel=sensei,
                                  avaliadores_map=avaliadores)
            print(f"[OK] Sensei/individuais: {rel_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())