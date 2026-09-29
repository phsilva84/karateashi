#!/usr/bin/env python3
"""tools/monitor_scans.py — Auto-pipeline do Karate-Ashi v2.

Fluxo automático: arquivo novo em <scans> (Google Drive sincronizado) ->
ingest_folhas (OMR) -> core/pipeline (engine, observações, relatórios, envio
ao GD) -> origem arquivada em <estado>.

Objetivo: NINGUÉM roda ingest manualmente. Basta copiar os scans para
G:\Meu Drive\documentos\KarateAshi_Exames\scans e o monitor dispara o fluxo.

Uso:
  python tools/monitor_scans.py            # fica observando (loop)
  python tools/monitor_scans.py --once     # roda 1 ciclo e sai (teste)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}
DEFAULT_SCANS = Path("G:/Meu Drive/documentos/KarateAshi_Exames/scans")
DEFAULT_ESTADO = Path("G:/Meu Drive/documentos/KarateAshi_Exames/estado")
DEFAULT_INTERVALO = 60      # poll a cada N segundos
DEFAULT_QUIETO = 20         # espera a cópia estabilizar (sem modificação por N s)


def _novos_arquivos(scans: Path) -> list[Path]:
    """Arquivos válidos presentes em scans (ainda não processados/arquivados)."""
    if not scans.is_dir():
        print(f"[aviso] pasta de scans não encontrada: {scans}")
        return []
    return sorted(
        f for f in scans.iterdir()
        if f.is_file()
        and not f.name.startswith((".", "~$"))
        and f.suffix.casefold() in EXT)


def _pronto_para_processar(scans: Path, quieto: float) -> bool:
    """Há arquivos novos E nenhum foi modificado nos últimos <quieto> s."""
    arquivos = _novos_arquivos(scans)
    if not arquivos:
        return False
    agora = time.time()
    return all(agora - f.stat().st_mtime >= quieto for f in arquivos)


def _rodar_fluxo(scans: Path, estado: Path, config: Path, saida: Path,
                 origem: str) -> bool:
    print(f"[{datetime.now():%H:%M:%S}] Novos scans detectados — "
          f"iniciando fluxo completo...")

    # 1) Ingestão OMR — mesmos parâmetros validados (scanner, sem --faixa)
    ingest = [
        sys.executable, str(RAIZ / "tools" / "ingest_folhas.py"),
        "--entrada", str(scans),
        "--config", str(config),
        "--saida", str(saida),
        "--arquivo", str(estado),
        "--origem", origem,
    ]
    r1 = subprocess.run(ingest, cwd=RAIZ)
    if r1.returncode != 0:
        print("[ERRO] Ingest falhou — arquivos permanecem em scans "
              "(serão reprocessados no próximo ciclo).")
        return False

    # 2) Pipeline: engine + observações + relatórios (+ envio ao GD)
    pipeline = [
        sys.executable, str(RAIZ / "core" / "pipeline.py"),
        "--config", str(config),
        "--data", str(RAIZ / "data"),
        "--output", str(RAIZ / "output"),
        "--pasta-omr", str(saida),
    ]
    r2 = subprocess.run(pipeline, cwd=RAIZ)
    if r2.returncode != 0:
        print("[ERRO] Pipeline falhou — verifique os relatórios.")
        return False

    print(f"[{datetime.now():%H:%M:%S}] Fluxo completo concluído com sucesso.")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Monitor automático do fluxo Karate-Ashi")
    ap.add_argument("--scans", type=Path, default=DEFAULT_SCANS,
                    help="pasta sincronizada com o GD onde chegam os scans")
    ap.add_argument("--estado", type=Path, default=DEFAULT_ESTADO,
                    help="pasta para arquivar os scans processados")
    ap.add_argument("--config", type=Path, default=RAIZ / "config")
    ap.add_argument("--saida", type=Path, default=RAIZ / "output" / "omr")
    ap.add_argument("--origem", choices=("auto", "scanner", "foto"),
                    default="scanner",
                    help="origem padrão do OMR (default: scanner)")
    ap.add_argument("--intervalo", type=int, default=DEFAULT_INTERVALO)
    ap.add_argument("--quieto", type=int, default=DEFAULT_QUIETO)
    ap.add_argument("--once", action="store_true",
                    help="roda um único ciclo e sai (modo teste)")
    args = ap.parse_args()

    print(f"[monitor] Observando: {args.scans}")
    print(f"[monitor] Intervalo: {args.intervalo}s | quieto: {args.quieto}s | "
          f"origem: {args.origem}")

    while True:
        try:
            if _pronto_para_processar(args.scans, args.quieto):
                _rodar_fluxo(args.scans, args.estado, args.config,
                             args.saida, args.origem)
        except KeyboardInterrupt:
            print("\n[monitor] Encerrado.")
            return 0
        except Exception as exc:  # noqa: BLE001 — monitor não pode morrer
            print(f"[erro] {exc}")
        if args.once:
            break
        time.sleep(args.intervalo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())