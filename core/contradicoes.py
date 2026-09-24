"""core/contradicoes.py — Contradições de observação (Karate-Ashi v2col-3.0).

O MESMO avaliador (uma folha) não pode marcar, no mesmo quesito, o par
contraditório: um 'Bom!' (positiva) e o 'A melhorar' oposto. Quando marca,
AS DUAS observações são anuladas e a contradição vai para o relatório geral
(campo 'contradicoes_observacoes') para o mestre refinar com o avaliador.

Pares data-driven: config/observacoes_contradicoes.json (o mestre ajusta
sem tocar no código).

NOTA (contrato): 'otimo' é o IDENTIFICADOR técnico do par (usado no JSON
custom e nos testes); o TEXTO exposto (otimo_texto) vem do vocabulário em
core/observacoes.py, que usa 'Bom'/'Boa' (sem prefácio 'Ótimo!').
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core import observacoes  # vocabulário único (fonte comum da folha)

log = logging.getLogger("karate-ashi.contradicoes")

# Pares padrão 6+6 homólogos (p = Bom! | m = A melhorar) — alinhados ao
# vocabulário real (obs_p1..p6 / obs_m1..m6) e à folha (rodapé 6+6).
PARES_PADRAO = [
    {"topico": "kihon",      "otimo": "obs_p1", "melhorar": "obs_m1"},
    {"topico": "kata",       "otimo": "obs_p2", "melhorar": "obs_m2"},
    {"topico": "bunkai",     "otimo": "obs_p3", "melhorar": "obs_m3"},
    {"topico": "kumite",     "otimo": "obs_p4", "melhorar": "obs_m4"},
    {"topico": "técnica",    "otimo": "obs_p5", "melhorar": "obs_m5"},
    {"topico": "desempenho", "otimo": "obs_p6", "melhorar": "obs_m6"},
]

VOCAB = {**observacoes.OBS_POSITIVAS, **observacoes.OBS_MELHORAR}


def carregar_pares(base_cfg: Path) -> list[dict]:
    """União dos pares padrão com os customizados (item 7 — Fase 3).

    Antes, o JSON custom SUBSTITUÍA os pares padrão. Agora é união:
    - o custom pode ADICIONAR pares novos;
    - se redefinir um par com as MESMAS chaves (otimo/melhorar), o custom
      prevalece (sem duplicar);
    - os padrão não citados continuam valendo.
    A deduplicação usa a chave (otimo, melhorar) — identidade funcional.
    """
    pares_por_chave: dict[tuple[str, str], dict] = {
        (p.get("otimo"), p.get("melhorar")): p for p in PARES_PADRAO
    }
    caminho = base_cfg / "observacoes_contradicoes.json"
    if caminho.exists():
        with open(caminho, encoding="utf-8") as fh:
            custom = json.load(fh).get("pares", [])
        for par in custom:
            chave = (par.get("otimo"), par.get("melhorar"))
            pares_por_chave[chave] = par
    return list(pares_por_chave.values())


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