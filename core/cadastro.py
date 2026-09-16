"""core/cadastro.py — Ciclo de vida do aluno (Karate-Ashi v2col-4.0).

O cadastro (data/cadastro/alunos.json) é o ESTADO ATUAL do aluno, com o
histórico de promoções embutido. Este módulo concentra a leitura, o filtro de
elegibilidade para exame e os utilitários de faixa — assim o tools/pre_exame.py
e o tools/promover_alunos.py compartilham a MESMA regra (folha e promoção nunca
divergem).

Campos do aluno:
    id, nome, dojo_id       — identidade
    faixa_atual             — faixa hoje (define o layout da folha)
    faixa_pretendida        — alvo do próximo exame (vazio = não examina)
    novo                    — primeira avaliação no sistema
    ativo                   — false = fora do dojo (não gera folha; mantém histórico)
    ultima_promocao         — data ISO da última promoção (ou null)
    historico_promocoes     — lista append-only de promoções
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from core.config import carregar_json  # fonte única (Fase 4 — item 1 do playbook)

FAIXA_TERMINAL_PADRAO = "Preta"

def chave(texto) -> str:
    """Normaliza para comparação: sem acento, minúsculo, sem espaços nas pontas."""
    if texto is None:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto))
        if not unicodedata.combining(c))
    return sem_acento.strip().casefold()

def salvar_json(caminho: Path, dados) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

def carregar_cadastro(caminho) -> list[dict]:
    """Aceita o caminho do alunos.json e também o da pasta que o contém."""
    caminho = Path(caminho)
    if caminho.is_dir():
        caminho = caminho / "alunos.json"
    dados = carregar_json(caminho)
    if isinstance(dados, dict):
        dados = dados.get("alunos", [])
    return list(dados)

def carregar_ordem_faixas(config_dir) -> list[str]:
    """Ordem canônica das faixas (config/faixas.json)."""
    caminho = Path(config_dir) / "faixas.json"
    if not caminho.exists():
        raise ValueError(
            f"config/faixas.json não encontrado em {caminho} — sem a ordem das "
            f"faixas não é possível validar promoção")
    ordem = carregar_json(caminho).get("ordem", [])
    if len(ordem) < 2:
        raise ValueError("config/faixas.json sem a lista 'ordem' preenchida")
    return ordem

def proxima_faixa(faixa_atual, ordem) -> str | None:
    """Faixa seguinte na ordem; None se for a última (terminal) ou desconhecida."""
    alvo = chave(faixa_atual)
    for i, faixa in enumerate(ordem):
        if chave(faixa) == alvo:
            return ordem[i + 1] if i + 1 < len(ordem) else None
    return None

def faixa_e_terminal(faixa, ordem) -> bool:
    return bool(ordem) and chave(faixa) == chave(ordem[-1])

def alunos_para_exame(cadastro: list[dict], faixa=None) -> list[dict]:
    """Alunos elegíveis a gerar folha (usado pelo tools/pre_exame.py).

    Critérios (v2col-4.0):
      1. ativo (campo ausente conta como True);
      2. tem faixa_pretendida preenchida — quem não tem alvo não examina;
      3. se 'faixa' foi informada, a faixa_atual bate (sem acento/maiúsculas).
    """
    selecionados = []
    for aluno in cadastro:
        if not aluno.get("ativo", True):
            continue
        if not str(aluno.get("faixa_pretendida") or "").strip():
            continue
        if faixa is not None and chave(aluno.get("faixa_atual")) != chave(faixa):
            continue
        selecionados.append(aluno)
    return selecionados