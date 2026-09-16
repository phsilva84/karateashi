"""core/engine.py — Motor de cálculo do Karate-Ashi v2.0. Modelo híbrido progressivo:
- frequência média por critério (média das marcações dos avaliadores);
- multiplicador progressivo por faixa de frequência;
- desconto = fc * peso * multiplicador;
- nota do quesito = max(0; 25 - soma dos descontos);
- trava de segurança por consenso (Bunkai/Kumite);
- nota final e status.

Fase 06 — multi-faixa:
- a tabela de critérios passa a vir de config/faixas/<faixa>.json (branca,
  amarela, laranja, verde e azul compartilham a tabela v2.0);
- roxa, marrom e preta são placeholders (nao_suportada: true);
- processa_aluno recebe `faixa` (opcional; se ausente, deriva de
  aluno.faixa_atual no primeiro bloco que a declarar).

Item 4 — dados legados:
- se algum bloco do aluno tiver "dados_legados": true (códigos fora da tabela
  v2.0 descartados pelo parser), o status vira REVISAO_PENDENTE: código
  descartado = penalidade não aplicada = nota maior que a real. A decisão
  automática nunca vale sobre nota inflada.

RL-03 — precedência de arredondamento (Fase 3):
- a nota final é arredondada para 1 casa decimal ANTES de classificar o status;
- o arredondamento é ROUND_HALF_UP com Decimal — NUNCA round() nativo do
  float, que por representação binária pode arredondar 69.95 para 69.9,
  jogando a fronteira de aprovação para o lado errado;
- regra resultante: soma 69,95 ou 69,96 -> nota exibida 70,0 -> APROVADO;
  soma 69,94 -> 69,9 -> RECUPERACAO.

RL-04 — normalização de faixa (Fase 3):
- carregar_faixa normaliza com .strip().lower(): 'Branca'/'BRANCA'/' branca '
  resolvem para o mesmo arquivo em disco (lower-case), sem FileNotFoundError
  no Linux do GitHub Actions.

Fase 4 — centralização:
- carregar_json, QUESITOS e FAIXAS_SUPORTADAS vêm de core.config (fonte única);
- a função carregar_json local foi removida; QUESTOS_ORDEM permanece como
  alias legado para QUESITOS.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from core.config import (
    FAIXAS_SUPORTADAS,
    QUESITOS,
    carregar_json,
)

QUESTOS_ORDEM = QUESITOS  # alias legado (Fase 4) — fonte única em core.config
NOTA_MAX_QUESITO = 25.0

def carregar_faixa(base_cfg: Path, faixa: str) -> dict:
    """Carrega a tabela de critérios da faixa (config/faixas/<faixa>.json).

    Devolve o dict de quesitos (mesma forma do critérios_por_quesito.json).
    Levanta ValueError se o arquivo não existir ou a faixa for placeholder.

    RL-04: normaliza a grafia da faixa antes de resolver o arquivo.
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

def nota_quesito(avaliacoes: list[dict], quesito: str, criterios_q: list[dict],
                 regras: dict) -> dict:
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

def _validar_entrada(avaliacoes: list[dict], faixa: str | None) -> None:
    """Recusa blocos ausentes ou incompletos antes de qualquer cálculo.

    Sem isto, a ausência de dados zera a soma de descontos e o aluno sai com
    nota 100.0 e APROVADO — sem erro. Falha de leitura nunca pode virar
    aprovação máxima.
    """
    if avaliacoes is None:
        raise ValueError(
            f"avaliacoes=None para a faixa '{faixa}': nenhum bloco de "
            "avaliador foi fornecido"
        )
    if not isinstance(avaliacoes, (list, tuple)):
        raise TypeError(
            f"avaliacoes deve ser list, veio {type(avaliacoes).__name__}"
        )
    if len(avaliacoes) == 0:
        raise ValueError(
            f"nenhum bloco de avaliador para a faixa '{faixa}'. "
            "Ausência de dados não é ausência de falhas: sem blocos, a soma "
            "de descontos seria 0 e o aluno sairia com 100.0 / APROVADO."
        )
    for i, bloco in enumerate(avaliacoes):
        if not isinstance(bloco, dict):
            raise TypeError(
                f"avaliacoes[{i}] deveria ser dict, "
                f"veio {type(bloco).__name__}"
            )
        detalhe = bloco.get("avaliacoes")
        if not isinstance(detalhe, dict) or not detalhe:
            raise ValueError(
                f"avaliacoes[{i}] sem a chave 'avaliacoes' preenchida — "
                "bloco de avaliador incompleto"
            )
        faltando = [q for q in QUESITOS if q not in detalhe]
        if faltando:
            raise ValueError(
                f"avaliacoes[{i}] sem os quesitos: {', '.join(faltando)}"
            )

def _derivar_faixa(avaliacoes: list[dict]) -> str:
    """Obtém a faixa do primeiro bloco que a declarar (aluno.faixa_atual)."""
    for bloco in avaliacoes:
        faixa = (bloco.get("aluno") or {}).get("faixa_atual")
        if faixa:
            return faixa
    raise ValueError(
        "faixa não informada pelo chamador nem presente nos blocos de "
        "avaliador (aluno.faixa_atual)"
    )

def processa_aluno(avaliacoes: list[dict], base_cfg: Path,
                   faixa: str | None = None) -> dict:
    """Consolida os blocos dos avaliadores e devolve o resultado do aluno.

    GUARD v2.0: recusa entrada vazia ou malformada. Ausência de dados jamais
    produz nota máxima silenciosa. A faixa pode vir do chamador ou ser
    derivada do primeiro bloco que a declarar (aluno.faixa_atual).
    """
    _validar_entrada(avaliacoes, faixa)
    if faixa is None:
        faixa = _derivar_faixa(avaliacoes)
    quesitos_cfg = carregar_faixa(base_cfg, faixa)
    regras = carregar_json(base_cfg / "regras_gerais.json")
    resultados = {}
    soma = 0.0
    for quesito in QUESTOS_ORDEM:
        r = nota_quesito(avaliacoes, quesito,
                         quesitos_cfg[quesito]["criterios"], regras)
        resultados[quesito] = r
        soma += r["nota"]

    # --- RL-03: precedência de arredondamento antes da classificação ---
    # A norma define a nota final com 1 casa decimal e o status sobre ESSA
    # nota. Decimal ROUND_HALF_UP evita o viés de ponto flutuante do round()
    # nativo (round(69.95, 1) == 69.9 no float, mas 70.0 em aritmética
    # decimal). Regra: soma >= 69.95 -> 70,0 -> APROVADO; 69.94 -> 69,9 ->
    # RECUPERACAO.
    nota_final = float(
        Decimal(str(round(soma, 2))).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP)
    )
    status_bruto = classificar_status(nota_final, regras)

    # --- Item 4: dados legados ---
    blocos_legados = [av for av in avaliacoes if av.get("dados_legados")]
    descartados: dict[str, list[int]] = {}
    for av in blocos_legados:
        for quesito, codigos in av.get("codigos_descartados", {}).items():
            descartados.setdefault(quesito, []).extend(codigos)
    if blocos_legados:
        status = "REVISAO_PENDENTE"
        alerta_legado = {
            "motivo": ("registro contém códigos do formato antigo; "
                       "nota pode estar incompleta"),
            "codigos_descartados": descartados,
        }
    else:
        status = status_bruto
        alerta_legado = None

    # --- Item 3: repassa observações para o relatório (Fase 05) ---
    observacoes_por_quesito: dict[str, list[str]] = {}
    observacoes_gerais: list[str] = []
    for av in avaliacoes:
        for quesito in QUESTOS_ORDEM:
            texto = (av.get("avaliacoes", {}).get(quesito, {}) or {}).get(
                "observacao", "")
            if texto:
                observacoes_por_quesito.setdefault(quesito, []).append(texto)
        if av.get("observacao_geral"):
            observacoes_gerais.append(av["observacao_geral"])

    return {
        "nota_final": nota_final,
        "status": status,
        "status_bruto": status_bruto,
        "quesitos": resultados,
        "faixa": faixa,
        "dados_legados": bool(blocos_legados),
        "alerta_legado": alerta_legado,
        "observacoes": {
            "por_quesito": observacoes_por_quesito,
            "gerais": observacoes_gerais,
        },
    }