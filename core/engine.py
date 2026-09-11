"""core/engine.py — Motor de cálculo do Karate-Ashi v2.0.

Modelo híbrido progressivo:
- frequência média por critério (média das marcações dos avaliadores);
- multiplicador progressivo por faixa de frequência;
- desconto = fc * peso * multiplicador;
- nota do quesito = max(0; 25 - soma dos descontos);
- trava de segurança por consenso (Bunkai/Kumite);
- nota final e status.

Fase 06 — multi-faixa:
- a tabela de critérios passa a vir de config/faixas/<faixa>.json
  (branca, amarela, laranja, verde e azul compartilham a tabela v2.0);
- roxa, marrom e preta são placeholders (nao_suportada: true);
- processa_aluno passa a receber o parâmetro `faixa`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOTA_MAX_QUESITO = 25.0
FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]

def carregar_json(caminho: Path) -> dict:
    """Lê um JSON de configuração. Falha com mensagem clara se inválido."""
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Configuração não encontrada: {caminho}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido em {caminho}: {exc}") from exc

def carregar_faixa(base_cfg: Path, faixa: str) -> dict:
    """Carrega a tabela de critérios da faixa (config/faixas/<faixa>.json).

    Devolve o dict de quesitos (mesma forma do critérios_por_quesito.json).
    Levanta ValueError se o arquivo não existir ou a faixa for placeholder.
    """
    faixa = str(faixa or "").strip().lower()
    caminho = base_cfg / "faixas" / f"{faixa}.json"
    if not caminho.exists():
        raise ValueError(f"faixa '{faixa}' não possui arquivo de configuração")

    cfg = carregar_json(caminho)

    if cfg.get("nao_suportada", False):
        raise ValueError(
            f"faixa '{faixa}' não suportada nesta versão "
            f"(Roxa/Marrom/Preta) — sem processamento"
        )
    return cfg["quesitos"]

def frequencia_media(marcacoes: list[int]) -> float:
    """Média simples das marcações (0 a 7) dos avaliadores presentes."""
    n = len(marcacoes)
    if n == 0:
        return 0.0
    return sum(marcacoes) / n

def multiplicador_progressivo(fc: float, faixas: list[dict]) -> float:
    """Retorna o multiplicador correspondente à faixa de fc."""
    for faixa in faixas:
        if faixa["fc_min"] <= fc <= faixa["fc_max"]:
            return faixa["multiplicador"]
    return 0.0  # fc == 0 ou fora das faixas

def desconto_criterio(fc: float, peso: float, mult: float) -> float:
    """Desconto do critério: fc * |peso| * multiplicador (2 casas)."""
    return round(fc * abs(peso) * mult, 2)

def consenso_controle(marcacoes_controle: list[int]) -> bool:
    """True quando TODOS os avaliadores presentes marcaram >= 1 ocorrência."""
    n = len(marcacoes_controle)
    if n == 0:
        return False
    return all(m >= 1 for m in marcacoes_controle)

def nota_quesito(avaliacoes: list[dict], quesito: str,
                 criterios_q: list[dict], regras: dict) -> dict:
    """Consolida um quesito entre avaliadores e devolve nota + detalhes."""
    total_desconto = 0.0
    detalhes: dict[str, Any] = {}
    controles: list[int] = []
    trava = regras["trava_seguranca"]

    for criterio in criterios_q:
        chave = criterio["chave"]
        marcacoes = [av["avaliacoes"][quesito]["frequencias"].get(chave, 0)
                     for av in avaliacoes]
        fc = frequencia_media(marcacoes)
        mult = multiplicador_progressivo(fc, regras["progressivo"])
        desc = desconto_criterio(fc, criterio["peso"], mult)
        total_desconto += desc
        detalhes[chave] = {
            "nome": criterio["nome"],
            "peso": criterio["peso"],
            "marcacoes": marcacoes,
            "fc": round(fc, 2),
            "multiplicador": mult,
            "desconto": desc,
        }
        if chave == trava["criterio"]:
            controles = marcacoes

    nota = round(max(0.0, NOTA_MAX_QUESITO - total_desconto), 2)

    if quesito in trava["quesitos"] and consenso_controle(controles):
        nota = min(nota, trava["teto"])
        alerta = "TRAVA_ATIVADA"
    elif quesito in trava["quesitos"] and any(m >= 1 for m in controles):
        alerta = "ALERTA_ETICO"
    else:
        alerta = None

    return {
        "quesito": quesito,
        "nota": nota,
        "desconto_total": round(total_desconto, 2),
        "detalhes": detalhes,
        "alerta": alerta,
        "controle_marcacoes": controles,
    }

def classificar_status(nota_final: float, regras: dict) -> str:
    """Classifica a nota final segundo as faixas da configuração."""
    if nota_final >= regras["status"]["aprovado_min"]:
        return "APROVADO"
    if nota_final >= regras["status"]["recuperacao_min"]:
        return "RECUPERACAO"
    return "REPROVADO"

def processa_aluno(avaliacoes: list[dict], base_cfg: Path, faixa: str) -> dict:
    """Recebe os JSONs de cada avaliador e devolve o resultado do aluno.

    avaliacoes: lista com um dict por avaliador, no schema v2.0:
      {"avaliacoes": {"kihon": {"frequencias": {...}, "observacao": "..."}, ...}}

    Fase 06: a tabela de critérios vem de config/faixas/<faixa>.json.
    """
    quesitos_cfg = carregar_faixa(base_cfg, faixa)
    regras = carregar_json(base_cfg / "regras_gerais.json")

    resultados = {}
    soma = 0.0
    for quesito in QUESTOS_ORDEM:
        r = nota_quesito(avaliacoes, quesito,
                         quesitos_cfg[quesito]["criterios"], regras)
        resultados[quesito] = r
        soma += r["nota"]

    nota_final = round(soma, 1)
    return {
        "nota_final": nota_final,
        "status": classificar_status(nota_final, regras),
        "quesitos": resultados,
        "faixa": faixa,
    }