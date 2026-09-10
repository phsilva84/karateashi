
FASE 01 — Motor de Cálculo Híbrido Progressivo0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Dev Python Sênior — código limpo, idiomático, funções pequenas e testáveis.
Engenheiro SRE/DevOps — validação de entradas, logs claros, tratamento de borda, testes.
Analista Pedagógico de Karatê — domínio de Kihon, Kata, Bunkai e Kumite; ética marcial.
Regras de conduta:
Use SEMPRE os valores deste documento e os da Fase 00 (config/). Nunca invente pesos, faixas ou regras.
Se algo não estiver especificado, PERGUNTE antes de assumir.
Não reabra decisões marcadas como aprovadas.
Ao final, preencha o checklist de aceite com o resultado real dos testes.

1. ObjetivoImplementar o motor de cálculo em core/engine.py com a fórmula híbrida progressiva v2.0: média das marcações dos avaliadores por critério, multiplicador progressivo por faixa de frequência, piso 0,0 por quesito, trava de segurança por consenso e classificação de status.2. Contexto mínimo do projetoO Karate-Ashi processa exames de Karatê com até 3 avaliadores. Cada aluno tem 4 quesitos (Kihon, Kata, Bunkai, Kumite), cada um valendo 25,0 pontos. Cada avaliador gera um JSON intermediário (schema v2.0) com a frequência de falha por critério (0 a 7 marcações). O motor consolida os avaliadores, calcula as notas e devolve o resultado para os relatórios (Fase 05).3. Decisões aprovadas (não reabrir)
   A9 (Defesa Incompleta) e A12 (Tensão/Respiração) removidos. Códigos relativos ao quesito.
   Frequência média do critério: fc = soma das marcações ÷ N avaliadores presentes.
   Multiplicadores progressivos por faixa de fc: 0 → ×0 · 0,1–1,0 → ×1,0 · 1,1–2,5 → ×1,5 · 2,6–4,5 → ×2,0 · 4,6–7,0 → ×2,5.
   Desconto do critério: fc × peso × multiplicador.
   Nota do quesito: max(0,0; 25,0 − soma dos descontos) — piso 0,0.
   Nota final: soma dos 4 quesitos, arredondada a 1 casa decimal.
   Status: Aprovado ≥ 70,0 · Recuperação 60,0–69,9 · Reprovado < 60,0.
   Trava de segurança (Bunkai e Kumite, critério falta_controle): apenas com consenso total dos avaliadores presentes (3 de 3, 2 de 2 ou 1 de 1) → nota do quesito limitada a 10,0. Sem consenso, mas com ao menos 1 marcação → alerta ético (não trava a nota).
2. Tarefas
   Criar core/engine.py com as funções abaixo (código de referência na seção 5).
   Criar tests/test_engine.py cobrindo os cenários da seção 6.
   Executar os testes e registrar resultado no Status (seção 7).
3. Código de referência



"""core/engine.py — Motor de cálculo do Karate-Ashi v2.0.

Modelo híbrido progressivo:

- frequência média por critério (média das marcações dos avaliadores);
- multiplicador progressivo por faixa de frequência;
- desconto = fc * peso * multiplicador;
- nota do quesito = max(0; 25 - soma dos descontos);
- trava de segurança por consenso (Bunkai/Kumite);
- nota final e status.
  """
  from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOTA_MAX_QUESITO = 25.0

def carregar_json(caminho: Path) -> dict:
    """Lê um JSON de configuração. Falha com mensagem clara se inválido."""
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

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

def processa_aluno(avaliacoes: list[dict], base_cfg: Path) -> dict:
    """Recebe os JSONs de cada avaliador e devolve o resultado do aluno.

    avaliacoes: lista com um dict por avaliador, no schema v2.0:
      {"avaliacoes": {"kihon": {"frequencias": {...}, "observacao": "..."}, ...}}
    """
    cfg = carregar_json(base_cfg / "criterios_por_quesito.json")
    regras = carregar_json(base_cfg / "regras_gerais.json")

    resultados = {}
    soma = 0.0
    for quesito in QUESTOS_ORDEM:
        r = nota_quesito(avaliacoes, quesito,
                         cfg["quesitos"][quesito]["criterios"], regras)
        resultados[quesito] = r
        soma += r["nota"]

    nota_final = round(soma, 1)
    return {
        "nota_final": nota_final,
        "status": classificar_status(nota_final, regras),
        "quesitos": resultados,
    }


6. Critérios de aceite (testar de verdade — pytest)
   Zero faltas em todos os critérios (3 avaliadores) → nota final 100.0 · APROVADO.
   Saturação máxima (7 em todos os critérios, 3 avaliadores) → todos os quesitos 0.0 · nota final 0.0 · REPROVADO.
   Trava: Bunkai com falta_controle marcado por 3 de 3 avaliadores → quesito limitado a 10.0 · alerta TRAVA_ATIVADA.
   Trava parcial: 1 de 3 marcou falta_controle → quesito NÃO trava, alerta ALERTA_ETICO.
   Variação de bancas: mesmo padrão de marcações com 1, 2 e 3 avaliadores → divisor N correto nas médias.
   Código em core/engine.py + tests/test_engine.py criados; testes passando.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
8.
