"""tools/comparar_json.py — compara dois lotes de JSON do OMR (antes vs depois).

Reporta por foto: observações marcadas e frequências que mudaram. Serve para
confirmar que a revalidação não alterou nenhuma leitura (ou apontar quais
mudaram, e em quê).

Uso:
    python tools/comparar_json.py --antes output/json_antes --depois output/json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

def _carregar(diretorio: Path) -> dict:
    lotes = {}
    for caminho in sorted(diretorio.glob("*.json")):
        lotes[caminho.stem] = json.loads(caminho.read_text(encoding="utf-8"))
    return lotes

def main() -> int:
    ap = argparse.ArgumentParser(description="Compara lotes de JSON do OMR")
    ap.add_argument("--antes", required=True, type=Path)
    ap.add_argument("--depois", required=True, type=Path)
    args = ap.parse_args()

    antes = _carregar(args.antes)
    depois = _carregar(args.depois)
    iguais = diferentes = 0

    for chave in sorted(set(antes) | set(depois)):
        a, b = antes.get(chave), depois.get(chave)
        if a is None or b is None:
            print(f"[NOVO/REMOVIDO] {chave}")
            diferentes += 1
            continue

        obs_a = a.get("observacoes_marcadas", [])
        obs_b = b.get("observacoes_marcadas", [])
        freq_a = {q: v.get("frequencias", {})
                  for q, v in a.get("avaliacoes", {}).items()}
        freq_b = {q: v.get("frequencias", {})
                  for q, v in b.get("avaliacoes", {}).items()}

        if obs_a == obs_b and freq_a == freq_b:
            iguais += 1
            print(f"[IGUAL] {chave}")
            continue

        diferentes += 1
        print(f"[DIFERENTE] {chave}")
        if obs_a != obs_b:
            print(f"   obs antes:  {obs_a}")
            print(f"   obs depois: {obs_b}")
        for quesito in sorted(set(freq_a) | set(freq_b)):
            if freq_a.get(quesito) != freq_b.get(quesito):
                print(f"   {quesito}: {freq_a.get(quesito)} -> {freq_b.get(quesito)}")

    print(f"\nResumo: {iguais} iguais | {diferentes} diferentes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())