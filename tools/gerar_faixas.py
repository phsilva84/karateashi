#!/usr/bin/env python3
"""gerar_faixas.py — Fase 06 (RL-06).

Gera:
  config/faixas/{amarela,laranja,verde,azul}.json  (cópia da tabela v2.0)
  config/faixas/{roxa,marrom,preta}.json           (placeholders)
  config/coordenadas/{amarela,laranja,verde,azul}.json (cópia do template)

Pré-requisito: config/faixas/branca.json e config/coordenadas/branca.json já existem.
Uso: python gerar_faixas.py [base_cfg] [--force]
     base_cfg default = "config"
     --force: sobrescreve arquivos que divergem do gerado (mesmo assim com backup .bak)

RL-06 (Fase 3): o gerador NUNCA sobrescreve um arquivo existente cujo
conteúdo difere do que seria gerado. Uma recalibração manual das
coordenadas (ou uma matriz de faixa personalizada) é PRESERVADA: o
conteúdo divergente vai para <nome>.bak e o gerador pula o arquivo,
avisando. Só o --force sobrescreve — e mesmo assim cria o .bak antes.
Rodar o gerador de novo sobre o que ele mesmo gerou é idempotente
(nenhuma alteração, nenhum backup criado).
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

def _conteudo_igual(dados: dict, caminho: Path) -> bool:
    """True se o arquivo já tem EXATAMENTE o que seria gerado (idempotência)."""
    if not caminho.exists():
        return False
    try:
        atual = json.loads(caminho.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return atual == dados

def _salvar_seguro(caminho: Path, dados: dict, *, forcar: bool) -> None:
    """Salva sem destruir trabalho manual (RL-06).

    - destino não existe  → cria;
    - destino é idêntico  → não faz nada (rodar de novo não muda nada);
    - destino DIVERGE     → preserva: copia o atual para <nome>.bak; sem
      --force, pula e avisa; com --force, sobrescreve (o .bak fica salvo).
    """
    if not caminho.exists():
        caminho.write_text(
            json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  criado: {caminho}")
        return
    if _conteudo_igual(dados, caminho):
        print(f"  inalterado: {caminho}")
        return
    backup = caminho.with_suffix(caminho.suffix + ".bak")
    backup.write_text(caminho.read_text(encoding="utf-8"), encoding="utf-8")
    if not forcar:
        print(f"  preservado: {caminho} difere do gerado "
              f"(backup em {backup.name}) — use --force para sobrescrever.")
        return
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  sobrescrito (--force): {caminho} (backup em {backup.name})")

def gerar(base_cfg: Path, *, forcar: bool = False) -> None:
    """Gera faixas/coordenadas; preserva qualquer divergência (RL-06)."""
    # --- 1) Faixas suportadas: cópia da tabela v2.0 (branca) ---
    print("Faixas suportadas:")
    dir_faixas = base_cfg / "faixas"
    tabela = _carregar(dir_faixas / "branca.json")
    for faixa in FAIXAS_SUPORTADAS[1:]:
        cfg = json.loads(json.dumps(tabela))  # deep copy
        cfg["faixa"] = faixa
        _salvar_seguro(dir_faixas / f"{faixa}.json", cfg, forcar=forcar)

    # --- 2) Placeholders ---
    print("Placeholders:")
    for faixa in FAIXAS_PLACEHOLDER:
        cfg = {
            "versao_schema": "2.0.0",
            "faixa": faixa,
            "nao_suportada": True,
            "quesitos": {},
        }
        _salvar_seguro(dir_faixas / f"{faixa}.json", cfg, forcar=forcar)

    # --- 3) Coordenadas: cópia do template (recalibração por faixa) ---
    print("Coordenadas:")
    dir_coord = base_cfg / "coordenadas"
    template = _carregar(dir_coord / "branca.json")
    for faixa in FAIXAS_SUPORTADAS[1:]:
        cfg = json.loads(json.dumps(template))
        cfg["faixa"] = faixa
        cfg["versao_template"] = f"{faixa}_v1"
        _salvar_seguro(dir_coord / f"{faixa}.json", cfg, forcar=forcar)

if __name__ == "__main__":
    forcar = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--force"]
    base = Path(args[0]) if args else Path("config")
    gerar(base, forcar=forcar)
    print("\nOK — processamento concluído. Divergências foram preservadas "
          "(backup .bak); use --force para sobrescrever.")