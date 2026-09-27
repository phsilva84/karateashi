"""core/observacoes.py — Observações estruturadas da folha (Karate-Ashi v4.9).

A observação do avaliador nasce na FOLHA como checkboxes (6+6), uniforme
para todas as faixas:

    'Ótimo!'     -> obs_p1..obs_p6   (pontos fortes)
    'A Melhorar' -> obs_m1..obs_m6   (correções)
O OMR lê as ROIs 'obs_*' na mesma passada dos códigos de erro e grava no
JSON intermediário:

    resultado["observacoes_marcadas"] = ["obs_p1", "obs_m2", ...]

Este módulo é o MAPEADOR chave -> texto: converte as chaves marcadas na
observação legível do relatório (observacao_montada).
Fonte única do vocabulário: OBS_POSITIVAS e OBS_MELHORAR definidas AQUI.
O tools/pre_exame.py IMPORTA essas constantes para desenhar a seção —
folha e relatório nunca divergem (princípio dos gêmeos).

CONTRADIÇÕES: quando o MESMO avaliador marca o positivo e o negativo do
MESMO tópico (ex.: obs_p1 'Boa execução dos Kihons' + obs_m1 'Dificuldade
nos Kihon'), a regra ANULA ambas as marcações e indica a contradição no
relatório. Os pares válidos ficam em config/observacoes_contradicoes.json.

Observações AUTOMÁTICAS (derivadas das frequências por regras) ficam em
core/observacoes_automaticas.py — módulo separado e complementar.
Integração:
    # OMR (Fase 03) — após ler as ROIs de observação:
    from core import observacoes
    resultado["observacoes_marcadas"] = chaves_marcadas
    resultado = observacoes.merge_no_json(resultado)
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import carregar_json

log = logging.getLogger("karate-ashi.observacoes")
# --- Vocabulário oficial das observações (v4.9 — 6+6) ----------------------
# Única fonte de verdade: a folha desenha e o relatório lê esta lista.
# Não duplicar em outro módulo — importe daqui.
OBS_POSITIVAS = {
    "obs_p1": "Boa execucao dos Kihons",
    "obs_p2": "Bom dominio do Kata",
    "obs_p3": "Boa aplicacao do Bunkai",
    "obs_p4": "Boa Conducao no Kumite",
    "obs_p5": "Bom Dominio Tecnico",
    "obs_p6": "Otimo Desempenho",
}

OBS_MELHORAR = {
    "obs_m1": "Dificuldade nos Kihon",
    "obs_m2": "Dificuldade no Kata",
    "obs_m3": "Dificuldade no Bunkai",
    "obs_m4": "Dificuldade nos Kumites",
    "obs_m5": "Erros Tecnicos Constantes",
    "obs_m6": "Nervosismo Constante",
}

_COLUNAS = (
    ("Bom!", OBS_POSITIVAS),
    ("A Melhorar", OBS_MELHORAR),
)


def _ordem(chave: str) -> int:
    """Extrai o número final da chave (obs_p1 -> 1, obs_m6 -> 6)."""
    digitos = "".join(c for c in chave if c.isdigit())
    try:
        return int(digitos)
    except ValueError:
        return 0


def _ordem_canonica(chave: str) -> tuple[int, int]:
    """Ordem da folha: coluna 'Ótimo!' (p) antes de 'A Melhorar' (m);
    dentro da coluna, pela ordem impressa (número)."""
    prefixo = chave.split("_")[1][0] if "_" in chave and len(chave.split("_")) > 1 else ""
    return (0 if prefixo == "p" else 1, _ordem(chave))


def _carregar_pares(caminho: Path | None = None) -> list[dict]:
    """Carrega os pares de contradição de config/observacoes_contradicoes.json."""
    caminho = caminho or Path(__file__).resolve().parents[1] / "config" / \
        "observacoes_contradicoes.json"
    try:
        return carregar_json(caminho).get("pares", [])
    except Exception:  # noqa: BLE001 — config ausente/inválida não quebra o fluxo
        return []


def detectar_contradicoes(marcadas: list[str],
                          pares: list[dict] | None = None) -> list[dict]:
    """Detecta contradições: mesmo tópico marcado como Ótimo! e A Melhorar.

    Retorna a lista de pares contraditórios {topico, otimo, melhorar}.
    Ex.: marcar obs_p1 e obs_m1 juntos -> [{"topico": "kihon", ...}].
    """
    pares = pares if pares is not None else _carregar_pares()
    marcadas_set = set(marcadas)
    return [p for p in pares
            if p["otimo"] in marcadas_set and p["melhorar"] in marcadas_set]


def montar_observacao(marcadas: list[str],
                      pares: list[dict] | None = None) -> str:
    """Converte chaves marcadas na observação legível do relatório.

    Detecta contradições (mesmo tópico em Bom! e A Melhorar), ANULA as
    marcações contraditórias e indica a contradição no texto.

    Ex.: ["obs_p1", "obs_m1", "obs_m6"] ->
         "Boa execucao dos Kihons; Nervosismo Constante. CONTRADIÇÃO: Kihon
          marcado como Bom! e A Melhorar simultaneamente — marcações anuladas."

    Ordena por coluna (Bom! antes de A Melhorar) e, dentro de cada coluna,
    pela ordem impressa na folha. Chaves desconhecidas são ignoradas.
    """
    contradicoes = detectar_contradicoes(marcadas, pares)
    chaves_anuladas = set()
    for p in contradicoes:
        chaves_anuladas.add(p["otimo"])
        chaves_anuladas.add(p["melhorar"])
    marcadas = [c for c in marcadas if c not in chaves_anuladas]

    positivas = sorted((c for c in marcadas if c in OBS_POSITIVAS), key=_ordem)
    melhorar = sorted((c for c in marcadas if c in OBS_MELHORAR), key=_ordem)
    desconhecidas = [c for c in marcadas
                     if c not in OBS_POSITIVAS and c not in OBS_MELHORAR]
    if desconhecidas:
        log.warning("chaves de observação desconhecidas ignoradas: %s",
                    desconhecidas)
    partes = []
    partes.extend(OBS_POSITIVAS[c] for c in positivas)
    partes.extend(OBS_MELHORAR[c] for c in melhorar)
    for p in contradicoes:
        partes.append(
            f"CONTRADIÇÃO: {p['topico'].capitalize()} marcado como Bom! "
            f"e A Melhorar simultaneamente — marcações anuladas.")
    return "; ".join(partes)


def merge_no_json(resultado: dict) -> dict:
    """Constrói 'observacao_montada' e 'contradicoes' a partir das marcadas.

    Não lê CSV. O OMR deve ter gravado resultado['observacoes_marcadas']
    (lista de chaves obs_*). Mantém este nome de função para a chamada
    já existente no OMR (Fase 03).

    A lista bruta sai na ordem da folha (Ótimo! antes de A Melhorar, por
    número) — não em ordem lexicográfica (que colocaria as 'm' antes das
    'p').
    """
    marcadas = set(str(c) for c in resultado.get("observacoes_marcadas", []) or [])
    resultado["observacoes_marcadas"] = sorted(marcadas, key=_ordem_canonica)
    resultado["contradicoes"] = detectar_contradicoes(
        resultado["observacoes_marcadas"])
    resultado["observacao_montada"] = montar_observacao(
        resultado["observacoes_marcadas"])
    log.info("observação montada: %r", resultado["observacao_montada"])
    return resultado


if __name__ == "__main__":
    # Checagem rápida de alinhamento: imprime o vocabulário oficial.
    print("Observações estruturadas (v4.9) — vocabulário oficial:\n")
    for titulo, coluna in _COLUNAS:
        print(f"--- {titulo} ---")
        for chave, texto in coluna.items():
            print(f"  {chave}: {texto}")
        print()