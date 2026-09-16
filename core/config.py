"""core/config.py — Configuração central do Karate-Ashi v2.0.

Centraliza (Fase 4):
- carregar_json — antes duplicado em engine, relatorios, omr_reader e
  notifications; agora existe num lugar só, com mensagens de erro claras;
- QUESITOS — ordem canônica dos quesitos, antes redefinida em 3 módulos
  (omr_reader, engine como QUESTOS_ORDEM, parser);
- FAIXAS_SUPORTADAS / FAIXAS_PLACEHOLDER — antes hardcoded em 6 lugares;
- faixas_suportadas(base_cfg) — deriva do índice config/faixas.json quando
  ele existir, com fallback para a lista embutida.
"""
from __future__ import annotations

import json
from pathlib import Path

# Ordem canônica dos quesitos (v2.0) — fonte única.
QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

# Faixas com matriz de critérios v2.0 (roxa/marrom/preta são placeholders).
FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
FAIXAS_PLACEHOLDER = ["roxa", "marrom", "preta"]

def carregar_json(caminho: Path) -> dict:
    """Lê um JSON de configuração. Falha com mensagem clara se inválido."""
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Configuração não encontrada: {caminho}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido em {caminho}: {exc}") from exc

def faixas_suportadas(base_cfg: Path) -> list[str]:
    """Lista canônica de faixas — deriva de config/faixas.json (índice).

    Se o índice existir com a chave 'suportadas', usa-o; senão, volta à
    lista embutida (compatibilidade com versões anteriores do repositório).
    """
    indice = base_cfg / "faixas.json"
    if indice.exists():
        dados = carregar_json(indice)
        if isinstance(dados, dict) and dados.get("suportadas"):
            return [str(f).strip().lower() for f in dados["suportadas"]]
    return FAIXAS_SUPORTADAS