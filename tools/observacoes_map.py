"""tools/observacoes_map.py — imprime o mapa chave -> texto das observações.

Marca UMA chave de observação por vez e mostra como o core/observacoes.py a
traduz. É a forma de conferir se a CHAVE que o OMR lê corresponde ao TEXTO
impresso na folha (hipótese de mapeamento trocado).

Uso:
    python tools/observacoes_map.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import observacoes  # noqa: E402

CHAVES = [f"obs_{p}{i}" for p in ("p", "m") for i in range(1, 9)]

def main() -> int:
    print("chave        -> texto")
    print("-" * 70)
    for chave in CHAVES:
        resultado = {"observacoes_marcadas": [chave]}
        try:
            montado = observacoes.merge_no_json(resultado)
            texto = montado.get("observacao_montada", "")
        except Exception as exc:  # noqa: BLE001
            texto = f"[erro: {exc}]"
        print(f"{chave:12s} -> {texto}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())