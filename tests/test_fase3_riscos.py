# tests/test_fase3_riscos.py
import json
from pathlib import Path

RAIZ = Path(__file__).parent.parent

def test_recomendacoes_sem_criterios_extintos():
    """Fase 4: A9/A12 não existem na v2.0 — config não pode tê-los."""
    rec = json.loads(
        (RAIZ / "config" / "recomendacoes.json").read_text(encoding="utf-8"))
    for chave in ("defesa_incompleta", "tensao_respiracao"):
        assert chave not in rec, f"resíduo A9/A12 no topo: {chave}"
        assert chave not in rec.get("exercicios", {}), \
            f"resíduo A9/A12 em exercicios: {chave}"