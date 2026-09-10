FASE 05 — Relatórios em 3 Camadas + Recomendações e Elogios0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE
Dev Python Sênior — geração de relatórios (texto/JSON), estrutura de dados.
Analista Pedagógico de Karatê / Redator — textos de recomendação e elogios com linguagem adequada.
Engenheiro SRE/DevOps — idempotência, consolidação estatística, roteamento por canal.
Regras de conduta: use SEMPRE os valores das Fases 00 a 02; nunca invente textos fora da biblioteca da seção 5; se algo não estiver especificado, PERGUNTE antes de assumir; ao final, preencha o checklist.1. ObjetivoCriar core/relatorios.py com 3 camadas de relatório: Individual (por aluno), Consolidado do Dojo (por exame) e Master Multi-Dojo. Inclui a biblioteca de recomendações por critério, os elogios por avaliação positiva (transversal, quesito perfeito, destaque ≥ 85) e as regras de recorrência (50%/80% no Dojo; 50% entre Dojos). Também cria config/recomendacoes.json com os textos oficiais.2. Contexto mínimo do projetoO motor (Fase 01) devolve o resultado por aluno; o parser (Fase 02) e o OMR (Fase 03) produzem os JSONs de entrada. Os relatórios consomem os resultados e são roteados: Relatórios 1 e 2 → grupo do Telegram do Dojo e pasta do Drive do Dojo; Relatório 3 → canal privado dos 4 Mestres e pasta restrita /Mestres/. A idempotência (hash MD5) garante envio apenas quando há mudança real.3. Decisões aprovadas (não reabrir)
Níveis de recomendação (por fc do critério no relatório individual): CRÍTICO (fc ≥ 4,5 ou saturação 7) · ATENÇÃO (2,6–4,5) · OBSERVAÇÃO (0,1–2,5) · FORÇA (fc = 0 no quesito ou nota final ≥ 85).
Ajustes por consenso: consenso total (100% dos avaliadores marcaram o critério) → sobe 1 nível; percepção isolada (1 de 3) → desce 1 nível.
ALERTA ÉTICO (Falta de Controle em Bunkai/Kumite sem consenso): seção destacada no topo, sem travar a nota.
Elogios (avaliação positiva): critério com 0 marcações de todos os avaliadores em 2+ quesitos → elogio transversal; quesito inteiro zerado → quesito perfeito; nota final ≥ 85 → destaque geral.
Ordem no relatório individual: 1º alerta ético → 2º recomendações CRÍTICAS → 3º ATENÇÃO → 4º OBSERVAÇÃO → 5º elogios e pontos fortes.
Recorrência do Dojo: critério presente em ≥ 50% dos alunos → "Prioridade de treino do Dojo"; ≥ 80% → "Prioridade máxima"; quesito com pior média → foco do ciclo. Master: critério em ≥ 50% dos Dojos → "Diretriz pedagógica global"; queda de média entre exames → alerta de acompanhamento.
Recorte por aluno: Relatório 1 sai para TODOS os alunos avaliados.
4. Tarefas
 Criar config/recomendacoes.json com a biblioteca da seção 5.
 Criar core/relatorios.py conforme código de referência (seção 5).
 Criar tests/test_relatorios.py cobrindo: níveis, ajuste de consenso, elogio transversal, ordem de exibição, recorrência 50/80.
 Gerar 1 exemplo de cada relatório a partir dos dados de teste.
 Executar testes e registrar no Status.
5. Código de referênciaconfig/recomendacoes.json (biblioteca oficial — usar ESTES textos):

{
  "base_incorreta": "Reforçar fundamentos de postura: largura, profundidade e distribuição de peso (Kiba-dachi, Zenkutsu-dachi).",
  "execucao_tecnica_incorreta": "Revisar trajetória dos golpes, rotação de punho e recolhimento.",
  "movimento_sem_carga": "Trabalhar transferência de peso e contração final (Kime).",
  "falta_foco": "Treinar direcionamento do olhar (Metsuke) e concentração no alvo.",
  "perda_equilibrio": "Exercícios de estabilidade, centro de gravidade e transições de base.",
  "ausencia_kiai": "Praticar expiração forte e projeção vocal sincronizada com a técnica.",
  "embusen_incorreto": "Reestudar o traçado do Kata e os pontos de retorno.",
  "falta_ritmo": "Trabalhar cadência, pausas e fluidez respeitando o embusen.",
  "distancia_inadequada": "Treinar controle de Ma-ai: distância de engajamento e recuo.",
  "falta_combatividade": "Estimular atitude ofensiva, entrada e contra-ataque sem passividade.",
  "falta_controle": "Reforçar controle de impacto e segurança do parceiro — prioridade absoluta.",
  "elogio_transversal": "Base exemplar: nenhuma marcação de {criterio} em {quesitos}.",
  "elogio_quesito_perfeito": "{quesito} impecável: nenhuma falha registrada pelos avaliadores.",
  "destaque_geral": "Destaque do exame: excelência técnica consistente em todas as categorias."
}


`core/relatorios.py`:


"""core/relatorios.py — Relatórios em 3 camadas do Karate-Ashi v2.0.

Camada 1: Individual (por aluno).
Camada 2: Consolidado do Dojo (por exame).
Camada 3: Master Multi-Dojo (estratégico, 4 Mestres).

Inclui biblioteca de recomendações, elogios e regras de recorrência.
A saída é texto (para Telegram/relatório) e o resultado também fica
disponível em JSON para o pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOME_QUESITO = {"kihon": "Kihon", "kata": "Kata",
                "bunkai": "Bunkai", "kumite": "Kumite"}

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def nivel_recomendacao(fc: float, marcacoes: list[int],
                       n_avaliadores: int) -> str:
    """Nível base por fc + ajustes por consenso/percepção isolada."""
    if fc >= 4.5 or any(m >= 7 for m in marcacoes):
        nivel = "CRITICO"
    elif fc >= 2.6:
        nivel = "ATENCAO"
    elif fc > 0:
        nivel = "OBSERVACAO"
    else:
        return "FORCA"

    presentes = [m for m in marcacoes if m > 0]
    if n_avaliadores >= 3 and len(presentes) == 1:
        nivel = {"CRITICO": "ATENCAO", "ATENCAO": "OBSERVACAO"}.get(
            nivel, nivel)  # percepção isolada desce um nível
    elif n_avaliadores >= 2 and len(presentes) == n_avaliadores:
        nivel = {"OBSERVACAO": "ATENCAO", "ATENCAO": "CRITICO"}.get(
            nivel, nivel)  # consenso total sobe um nível
    return nivel

def gerar_recomendacoes(resultado: dict, recomendacoes: dict) -> list[dict]:
    """Gera a lista priorizada de recomendações do aluno."""
    itens = []
    for quesito, q in resultado["quesitos"].items():
        for chave, det in q["detalhes"].items():
            if det["fc"] == 0:
                continue
            nivel = nivel_recomendacao(det["fc"], det["marcacoes"],
                                       len(det["marcacoes"]))
            itens.append({
                "nivel": nivel,
                "quesito": NOME_QUESITO[quesito],
                "criterio": det["nome"],
                "texto": recomendacoes.get(chave, ""),
            })
    ordem = {"CRITICO": 0, "ATENCAO": 1, "OBSERVACAO": 2, "FORCA": 3}
    return sorted(itens, key=lambda x: ordem[x["nivel"]])

def gerar_elogios(resultado: dict, regras: dict,
                  recomendacoes: dict) -> list[str]:
    """Elogios: critério transversal zerado, quesito perfeito, destaque."""
    elogios = []
    # Transversal: critério zerado em 2+ quesitos onde aparece
    presenca: dict[str, list[str]] = {}
    for quesito, q in resultado["quesitos"].items():
        for chave, det in q["detalhes"].items():
            presenca.setdefault(chave, []).append(
                (NOME_QUESITO[quesito], det["marcacoes"]))
    for chave, ocorrencias in presenca.items():
        zerados = [nome for nome, ms in ocorrencias if all(m == 0 for m in ms)]
        if len(zerados) >= regras["elogios"]["criterio_transversal_min_quesitos"]:
            elogios.append(recomendacoes["elogio_transversal"].replace(
                "{criterio}", chave).replace("{quesitos}", ", ".join(zerados)))
            break  # um elogio transversal por relatório
    # Quesito perfeito
    for quesito, q in resultado["quesitos"].items():
        if all(det["fc"] == 0 for det in q["detalhes"].values()):
            elogios.append(recomendacoes["elogio_quesito_perfeito"].replace(
                "{quesito}", NOME_QUESITO[quesito]))
    # Destaque geral
    if resultado["nota_final"] >= regras["elogios"]["destaque_geral_min"]:
        elogios.append(recomendacoes["destaque_geral"])
    return elogios

def relatorio_individual(resultado: dict, regras: dict,
                         recomendacoes: dict, aluno: dict) -> str:
    """Relatório 1 — texto formatado, na ordem normativa definida."""
    linhas = [f"ALUNO: {aluno.get('nome', '')}",
              f"NOTA FINAL: {resultado['nota_final']}  STATUS: {resultado['status']}",
              ""]

    # 1º Alerta ético
    for quesito, q in resultado["quesitos"].items():
        if q["alerta"] == "ALERTA_ETICO":
            linhas.append("** ALERTA ETICO **")
            linhas.append(f"{NOME_QUESITO[quesito]}: falta de controle "
                          "sinalizada sem consenso — atenção máxima.")
            linhas.append("")

    # 2º a 4º Recomendações por nível
    linhas.append("RECOMENDACOES:")
    for item in gerar_recomendacoes(resultado, recomendacoes):
        linhas.append(f"[{item['nivel']}] {item['quesito']} - "
                      f"{item['criterio']}: {item['texto']}")
    linhas.append("")

    # 5º Elogios
    elogios = gerar_elogios(resultado, regras, recomendacoes)
    if elogios:
        linhas.append("PONTOS FORTES:")
        linhas.extend(f"- {e}" for e in elogios)

    return "\n".join(linhas)

def consolidar_dojo(resultados_alunos: list[dict],
                    regras: dict) -> dict:
    """Relatório 2 — agregações do Dojo (recorrência 50%/80%)."""
    n = len(resultados_alunos)
    taxa = {"APROVADO": 0, "RECUPERACAO": 0, "REPROVADO": 0}
    for r in resultados_alunos:
        taxa[r["status"]] += 1

    presenca_criterio: dict[tuple, int] = {}
    for r in resultados_alunos:
        for quesito, q in r["quesitos"].items():
            for chave, det in q["detalhes"].items():
                if det["fc"] > 0:
                    presenca_criterio[(quesito, chave)] = 
                        presenca_criterio.get((quesito, chave), 0) + 1

    prioridades = []
    for (quesito, chave), count in presenca_criterio.items():
        fracao = count / n if n else 0
        if fracao >= 0.80:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}",
                                "Prioridade máxima de treino"))
        elif fracao >= 0.50:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}",
                                "Prioridade de treino do Dojo"))

    return {
        "total_alunos": n,
        "taxa": {k: round(v / n * 100, 1) if n else 0.0
                 for k, v in taxa.items()},
        "prioridades_treino": prioridades,
    }

def relatorio_master(resultados_dojos: list[dict],
                     regras: dict) -> str:
    """Relatório 3 — visão estratégica multi-Dojo (texto resumido)."""
    linhas = ["RELATORIO MASTER MULTI-DOJO", ""]
    for d in resultados_dojos:
        media = sum(r["nota_final"] for r in d["alunos"]) / len(d["alunos"]) 
            if d["alunos"] else 0.0
        aprovados = sum(1 for r in d["alunos"]
                        if r["status"] == "APROVADO")
        taxa_aprov = aprovados / len(d["alunos"]) * 100 if d["alunos"] else 0
        linhas.append(f"Dojo {d['dojo_id']}: média {media:.1f} | "
                      f"aprovação {taxa_aprov:.0f}%")
    linhas.append("")
    linhas.append("DIRETRIZES: critérios recorrentes em 50%+ dos Dojos "
                  "devem virar diretriz pedagógica global (validar com "
                  "dados reais).")
    return "\n".join(linhas)



6. Critérios de aceite
   nivel_recomendacao correto: fc 5,0 → CRITICO; fc 3,0 → ATENCAO; fc 1,0 → OBSERVACAO; percepção isolada desce; consenso total sobe.
   Elogio transversal dispara quando critério zerado em 2+ quesitos; quesito perfeito e destaque ≥ 85 funcionam.
   Relatório individual segue a ordem: alerta ético → CRÍTICO → ATENÇÃO → OBSERVAÇÃO → elogios.
   Consolidação do Dojo: recorrência 50% e 80% geram as prioridades corretas; taxa de status correta.
   Relatório Master consolida nota média e taxa de aprovação por Dojo.
   tests/test_relatorios.py criado e passando; 1 exemplo de cada relatório gerado.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
