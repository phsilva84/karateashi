#!/usr/bin/env python3
"""gerar_faixas.py — Fase 06.

Gera:
  config/faixas/{amarela,laranja,verde,azul}.json  (cópia da tabela v2.0)
  config/faixas/{roxa,marrom,preta}.json           (placeholders)
  config/coordenadas/{amarela,laranja,verde,azul}.json (cópia do template)

Pré-requisito: config/faixas/branca.json e config/coordenadas/branca.json já existem.
Uso: python gerar_faixas.py [base_cfg]   # base_cfg default = "config"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
FAIXAS_PLACEHOLDER = ["roxa", "marrom", "preta"]

def _carregar(caminho: Path) -> dict:
    if not caminho.exists():
        raise FileNotFoundError(
            f"arquivo-base ausente: {caminho} (crie-o antes de rodar o gerador)"
        )
    return json.loads(caminho.read_text(encoding="utf-8"))

def _salvar(caminho: Path, dados: dict) -> None:
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  criado: {caminho}")

def gerar(base_cfg: Path) -> None:
    # --- 1) Faixas suportadas: cópia da tabela v2.0 (branca) ---
    print("Faixas suportadas:")
    dir_faixas = base_cfg / "faixas"
    tabela = _carregar(dir_faixas / "branca.json")
    for faixa in FAIXAS_SUPORTADAS[1:]:
        cfg = json.loads(json.dumps(tabela))  # deep copy
        cfg["faixa"] = faixa
        _salvar(dir_faixas / f"{faixa}.json", cfg)

    # --- 2) Placeholders ---
    print("Placeholders:")
    for faixa in FAIXAS_PLACEHOLDER:
        cfg = {
            "versao_schema": "2.0.0",
            "faixa": faixa,
            "nao_suportada": True,
            "quesitos": {},
        }
        _salvar(dir_faixas / f"{faixa}.json", cfg)

    # --- 3) Coordenadas: cópia do template (recalibração por faixa) ---
    print("Coordenadas:")
    dir_coord = base_cfg / "coordenadas"
    template = _carregar(dir_coord / "branca.json")
    for faixa in FAIXAS_SUPORTADAS[1:]:
        cfg = json.loads(json.dumps(template))
        cfg["faixa"] = faixa
        cfg["versao_template"] = f"{faixa}_v1"
        _salvar(dir_coord / f"{faixa}.json", cfg)

if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config")
    gerar(base)
    print(f"\nOK — 8 arquivos de faixa e 5 de coordenadas em '{base}'.")