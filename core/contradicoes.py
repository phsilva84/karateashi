"""core/contradicoes.py — Contradições de observação (Karate-Ashi v2col-3.0).

O MESMO avaliador (uma folha) não pode marcar, no mesmo quesito, o par
contraditório: um 'Ótimo!' e o 'A melhorar' oposto. Quando marca, AS DUAS
observações são anuladas e a contradição vai para o relatório geral
(campo 'contradicoes_observacoes') para o mestre refinar com o avaliador.

Pares data-driven: config/observacoes_contradicoes.json (o mestre ajusta
sem tocar no código).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core import observacoes  # vocabulário único (fonte comum da folha)

log = logging.getLogger("karate-ashi.contradicoes")

# Pares padrão derivados do vocabulário (p = Ótimo! | m = A melhorar).
PARES_PADRAO = [
    {"topico": "execução técnica", "otimo": "obs_p1", "melhorar": "obs_m6"},
    {"topico": "bases / postura",  "otimo": "obs_p2", "melhorar": "obs_m1"},
    {"topico": "foco / olhar",     "otimo": "obs_p4", "melhorar": "obs_m4"},
    {"topico": "kata",             "otimo": "obs_p7", "melhorar": "obs_m7"},
    {"topico": "kihon",            "otimo": "obs_p8", "melhorar": "obs_m8"},
]

VOCAB = {**observacoes.OBS_POSITIVAS, **observacoes.OBS_MELHORAR}

def carregar_pares(base_cfg: Path) -> list[dict]:
    caminho = base_cfg / "observacoes_contradicoes.json"
    if not caminho.exists():
        log.info("sem %s — usando pares padrão", caminho)
        return PARES_PADRAO
    with open(caminho, encoding="utf-8") as fh:
        return json.load(fh).get("pares", PARES_PADRAO)

def detectar(marcadas: list[str], pares: list[dict]) -> tuple[list[str], list[dict]]:
    """Anula pares contraditórios e devolve (limpas, contradicoes)."""
    presentes = set(marcadas)
    anular: set[str] = set()
    contradicoes: list[dict] = []
    for par in pares:
        otimo, melhorar = par.get("otimo"), par.get("melhorar")
        if otimo in presentes and melhorar in presentes:
            anular.update((otimo, melhorar))
            contradicoes.append({
                "topico": par.get("topico", ""),
                "otimo": otimo,
                "otimo_texto": VOCAB.get(otimo, otimo),
                "melhorar": melhorar,
                "melhorar_texto": VOCAB.get(melhorar, melhorar),
            })
    limpas = [c for c in marcadas if c not in anular]
    if contradicoes:
        log.warning("contradições anuladas: %s", contradicoes)
    return limpas, contradicoes

def consolidar(resultados: list[dict]) -> list[dict]:
    """Agrega contradições de N JSONs para o relatório geral (por avaliador)."""
    linhas = []
    for r in resultados:
        for c in r.get("contradicoes_observacoes", []) or []:
            linhas.append({
                "aluno_id": (r.get("aluno") or {}).get("id"),
                "avaliador_id": (r.get("metadados") or {}).get("avaliador_id"),
                **c,
            })
    return linhas