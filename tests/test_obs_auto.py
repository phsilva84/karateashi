"""Teste rápido das observações automáticas (Karate-Ashi)."""
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao caminho de busca de módulos
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import observacoes_automaticas

exemplo = {
    "kihon": {"frequencias": {"1": 3, "2": 0, "3": 1, "4": 0, "5": 0, "6": 0}},
    "kata": {"frequencias": {"1": 4, "2": 0, "3": 2, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0}},
    "bunkai": {"frequencias": {"1": 2, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0, "8": 0}},
    "kumite": {"frequencias": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "7": 0}},
}

obs = observacoes_automaticas.gerar_observacoes_automaticas(exemplo, "branca")
print("Observações automáticas geradas:")
for o in obs:
    print(f"  [{o['tipo']}] {o['texto']}")