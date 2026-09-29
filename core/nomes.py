"""core/nomes.py — Utilitários de nomes do Karate-Ashi v2.0.

Folhas (tools/pre_exame.py): espaço fixo ao lado do balão de presença e na
faixa do rodapé → nome ABREVIADO como identificador (ex.: "Pedro J. Silva"),
para não quebrar o layout nem depender de fonte mínima ilegível.
Relatórios (core/pipeline + core/relatorio_html): sem limite de espaço →
nome COMPLETO (não usa esta função).
"""
from __future__ import annotations

_PREPOSICOES = {"da", "de", "do", "das", "dos"}


def abreviar_nome(nome: str, max_len: int = 22) -> str:
    """Abrevia nome completo para identificação em FOLHAS: 'Pedro J. Silva'.

    Mantém o primeiro nome e o último sobrenome, com a inicial do primeiro
    sobrenome SIGNIFICATIVO (ignora 'da/de/do/das/dos'). Se ainda exceder
    max_len, corta e acrescenta '…'.
    """
    partes = [p for p in str(nome or "").strip().split() if p]
    if not partes:
        return ""
    if len(partes) == 1:
        return partes[0][:max_len]
    primeiro = partes[0]
    ultimo = partes[-1]
    meio = [p for p in partes[1:-1] if p.lower() not in _PREPOSICOES]
    abrev = primeiro
    if meio:
        abrev += f" {meio[0][0].upper()}."
    abrev += f" {ultimo}"
    if len(abrev) > max_len:
        abrev = abrev[: max_len - 1].rstrip() + "…"
    return abrev