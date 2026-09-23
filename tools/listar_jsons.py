"""listar_jsons.py — Lista os JSONs do OMR com aluno, avaliador e faixa.

Uso: python tools/listar_jsons.py
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

pasta = Path("output/teste_omr")
for p in sorted(pasta.glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    m = d.get("metadados", {})
    print(f"{p.name:<45} aluno={m.get('aluno_id')} "
          f"avaliador={m.get('avaliador_id')} faixa={m.get('faixa')}")