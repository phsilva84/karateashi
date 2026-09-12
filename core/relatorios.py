"""core/relatorios.py — Relatórios em 3 camadas do Karate-Ashi v2.0.

Camada 1: Individual (por aluno).
Camada 2: Consolidado do Dojo (por exame) + Tendências.
Camada 3: Master Multi-Dojo (estratégico, 4 Mestres).

Inclui biblioteca de recomendações, elogios e regras de recorrência
(50%/80% no Dojo; 50% entre Dojos). A saída é texto (para Telegram/relatório)
e o resultado também fica disponível em JSON para o pipeline.

Consome os resultados do motor (Fase 01): dict por aluno com
"quesitos" -> {kihon|kata|bunkai|kumite} -> {"alerta", "detalhes"},
onde "detalhes" mapeia a chave semântica do critério (ex.: "base_incorreta")
para {"fc", "marcacoes", "nome"}.
"""
from __future__ import annotations

import json
from pathlib import Path

QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOME_QUESITO = {
    "kihon": "Kihon",
    "kata": "Kata",
    "bunkai": "Bunkai",
    "kumite": "Kumite",
}

# Códigos técnicos A1-A12 -> chave semântica usada em config/recomendacoes.json
CODIGO_CHAVE = {
    "A1": "base_incorreta",
    "A2": "execucao_tecnica_incorreta",
    "A3": "movimento_sem_carga",
    "A4": "ausencia_kiai",
    "A5": "embusen_incorreto",
    "A6": "falta_foco",
    "A7": "perda_equilibrio",
    "A8": "falta_ritmo",
    "A9": "defesa_incompleta",
    "A10": "falta_controle",
    "A11": "distancia_inadequada",
    "A12": "tensao_respiracao",
}

NOME_CRITERIO = {
    "base_incorreta": "Base incorreta",
    "execucao_tecnica_incorreta": "Execução técnica incorreta",
    "movimento_sem_carga": "Movimento sem carga",
    "ausencia_kiai": "Ausência de kiai",
    "embusen_incorreto": "Embusen incorreto",
    "falta_foco": "Falta de foco",
    "perda_equilibrio": "Perda de equilíbrio",
    "falta_ritmo": "Falta de ritmo",
    "defesa_incompleta": "Defesa incompleta",
    "falta_controle": "Falta de controle",
    "distancia_inadequada": "Distância inadequada",
    "tensao_respiracao": "Tensão/respiração inadequada",
    "falta_combatividade": "Falta de combatividade",
}

NIVEL_ORDEM = {"CRITICO": 0, "ATENCAO": 1, "OBSERVACAO": 2, "FORCA": 3}

def carregar_json(caminho: Path) -> dict:
    """Carrega um JSON com encoding UTF-8 (textos acentuados)."""
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def nivel_por_fc(fc: float) -> str:
    """Nível base apenas pela frequência (sem ajustes de consenso)."""
    if fc >= 4.5:
        return "CRITICO"
    if fc >= 2.6:
        return "ATENCAO"
    if fc > 0:
        return "OBSERVACAO"
    return "FORCA"

def nivel_recomendacao(fc: float, marcacoes: list[int], n_avaliadores: int) -> str:
    """Nível base por fc + saturação + ajustes por consenso/percepção isolada.

    Saturação (7+ marcações de um mesmo avaliador) é sinal forte o bastante
    para manter CRITICO mesmo com percepção isolada (1 de 3).
    """
    saturado = any(m >= 7 for m in marcacoes)
    if saturado:
        nivel = "CRITICO"
    else:
        nivel = nivel_por_fc(fc)
    if nivel == "FORCA":
        return nivel
    presentes = [m for m in marcacoes if m > 0]
    if n_avaliadores >= 3 and len(presentes) == 1 and not saturado:
        # percepção isolada (1 de 3) desce um nível
        nivel = {"CRITICO": "ATENCAO", "ATENCAO": "OBSERVACAO"}.get(nivel, nivel)
    elif n_avaliadores >= 2 and len(presentes) == n_avaliadores:
        # consenso total (100% dos avaliadores) sobe um nível
        nivel = {"OBSERVACAO": "ATENCAO", "ATENCAO": "CRITICO"}.get(nivel, nivel)
    return nivel

def gerar_recomendacoes(resultado: dict, recomendacoes: dict) -> list[dict]:
    """Gera a lista priorizada de recomendações do aluno."""
    itens = []
    for quesito, q in resultado["quesitos"].items():
        for chave, det in q["detalhes"].items():
            if det["fc"] == 0:
                continue
            nivel = nivel_recomendacao(det["fc"], det["marcacoes"], len(det["marcacoes"]))
            itens.append({
                "nivel": nivel,
                "quesito": NOME_QUESITO[quesito],
                "criterio": det.get("nome") or NOME_CRITERIO.get(chave, chave),
                "texto": recomendacoes.get(chave, ""),
            })
    return sorted(itens, key=lambda x: NIVEL_ORDEM[x["nivel"]])

def gerar_elogios(resultado: dict, regras: dict, recomendacoes: dict) -> list[str]:
    """Elogios: critério transversal zerado, quesito perfeito, destaque geral."""
    elogios = []
    # Transversal: critério zerado em 2+ quesitos
    presenca: dict[str, list[tuple[str, list[int]]]] = {}
    for quesito, q in resultado["quesitos"].items():
        for chave, det in q["detalhes"].items():
            presenca.setdefault(chave, []).append((NOME_QUESITO[quesito], det["marcacoes"]))
    for chave, ocorrencias in presenca.items():
        zerados = [nome for nome, ms in ocorrencias if all(m == 0 for m in ms)]
        if len(zerados) >= regras["elogios"]["criterio_transversal_min_quesitos"]:
            nome_criterio = NOME_CRITERIO.get(chave, chave)
            elogios.append(recomendacoes["elogio_transversal"]
                           .replace("{criterio}", nome_criterio)
                           .replace("{quesitos}", ", ".join(zerados)))
            break  # um elogio transversal por relatório
    # Quesito perfeito
    for quesito, q in resultado["quesitos"].items():
        if all(det["fc"] == 0 for det in q["detalhes"].values()):
            elogios.append(recomendacoes["elogio_quesito_perfeito"]
                           .replace("{quesito}", NOME_QUESITO[quesito]))
    # Destaque geral
    if resultado["nota_final"] >= regras["elogios"]["destaque_geral_min"]:
        elogios.append(recomendacoes["destaque_geral"])
    return elogios

def relatorio_individual(resultado: dict, regras: dict, recomendacoes: dict, aluno: dict) -> str:
    """Relatório 1 — texto formatado, na ordem normativa definida."""
    linhas = [
        f"ALUNO: {aluno.get('nome', '')}",
        f"NOTA FINAL: {resultado['nota_final']} STATUS: {resultado['status']}",
        "",
    ]
    # 1º Alerta ético
    for quesito, q in resultado["quesitos"].items():
        if q.get("alerta") == "ALERTA_ETICO":
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

def consolidar_dojo(resultados_alunos: list[dict], regras: dict) -> dict:
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
                    presenca_criterio[(quesito, chave)] = presenca_criterio.get((quesito, chave), 0) + 1
    prioridades = []
    for (quesito, chave), count in presenca_criterio.items():
        fracao = count / n if n else 0
        if fracao >= 0.80:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}", "Prioridade máxima de treino"))
        elif fracao >= 0.50:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}", "Prioridade de treino do Dojo"))
    # Foco do ciclo: quesito com pior média de nota
    medias_quesito = {q: [] for q in QUESITOS_ORDEM}
    for r in resultados_alunos:
        for q in QUESITOS_ORDEM:
            medias_quesito[q].append(r["quesitos"][q].get("nota", 25.0))
    foco = min(medias_quesito, key=lambda q: (
        sum(medias_quesito[q]) / len(medias_quesito[q]) if medias_quesito[q] else 25.0))
    return {
        "total_alunos": n,
        "taxa": {k: round(v / n * 100, 1) if n else 0.0 for k, v in taxa.items()},
        "prioridades_treino": prioridades,
        "foco_ciclo": NOME_QUESITO[foco],
    }

def formatar_consolidado_dojo(consolidado: dict) -> str:
    """Texto do Relatório 2 (Telegram/relatório)."""
    linhas = ["RELATORIO CONSOLIDADO DO DOJO", ""]
    linhas.append(f"Total de alunos avaliados: {consolidado['total_alunos']}")
    taxa = consolidado["taxa"]
    linhas.append(f"Taxa de status: Aprovado {taxa['APROVADO']}% | "
                  f"Recuperação {taxa['RECUPERACAO']}% | Reprovado {taxa['REPROVADO']}%")
    linhas.append(f"Foco do ciclo: {consolidado['foco_ciclo']} (pior média)")
    linhas.append("")
    linhas.append("PRIORIDADES DE TREINO:")
    for item, rotulo in consolidado["prioridades_treino"]:
        quesito, chave = item.split(".", 1)
        linhas.append(f"- {quesito} - {NOME_CRITERIO.get(chave, chave)}: {rotulo}")
    return "\n".join(linhas)

def relatorio_tendencias(resultados_alunos: list[dict], recomendacoes: dict) -> str:
    """Proposta de tendências: agregação em %, moda e narrativa por intensidade.

    A intensidade narrativa reutiliza os níveis existentes (OBSERVACAO,
    ATENCAO, CRITICO) via média de fc por critério — sem criar faixas de %
    paralelas. Inclui exercício corretivo da biblioteca.
    """
    n = len(resultados_alunos)
    if n == 0:
        return "RELATORIO DE TENDENCIAS\n\nSem alunos avaliados."
    presenca: dict[tuple, int] = {}
    soma_fc: dict[tuple, float] = {}
    for r in resultados_alunos:
        for quesito, q in r["quesitos"].items():
            for chave, det in q["detalhes"].items():
                if det["fc"] > 0:
                    presenca[(quesito, chave)] = presenca.get((quesito, chave), 0) + 1
                    soma_fc[(quesito, chave)] = soma_fc.get((quesito, chave), 0.0) + det["fc"]
    if not presenca:
        return "RELATORIO DE TENDENCIAS\n\nNenhum critério recorrente identificado."
    moda = max(presenca, key=presenca.get)
    linhas = ["RELATORIO DE TENDENCIAS", ""]
    linhas.append(f"Alunos considerados: {n}")
    linhas.append(f"Moda do exame: {NOME_QUESITO[moda[0]]} - "
                  f"{NOME_CRITERIO.get(moda[1], moda[1])} "
                  f"({presenca[moda]}/{n} alunos)")
    linhas.append("")
    linhas.append("CRITERIOS RECORRENTES (por intensidade):")
    for (quesito, chave), count in sorted(presenca.items(), key=lambda x: -x[1]):
        media_fc = soma_fc[(quesito, chave)] / count
        nivel = nivel_por_fc(media_fc)
        exercicio = recomendacoes.get("exercicios", {}).get(chave, "")
        linhas.append(f"[{nivel}] {NOME_QUESITO[quesito]} - "
                      f"{NOME_CRITERIO.get(chave, chave)} "
                      f"({count}/{n} alunos, média fc {media_fc:.1f})")
        if exercicio:
            linhas.append(f"    Exercício corretivo: {exercicio}")
    return "\n".join(linhas)

def relatorio_master(resultados_dojos: list[dict], regras: dict, recomendacoes: dict) -> str:
    """Relatório 3 — visão estratégica multi-Dojo (texto resumido)."""
    linhas = ["RELATORIO MASTER MULTI-DOJO", ""]
    n_dojos = len(resultados_dojos)
    presenca_global: dict[tuple, int] = {}
    for d in resultados_dojos:
        criterios_dojo = set()
        for r in d.get("alunos", []):
            for quesito, q in r["quesitos"].items():
                for chave, det in q["detalhes"].items():
                    if det["fc"] > 0:
                        criterios_dojo.add((quesito, chave))
        for c in criterios_dojo:
            presenca_global[c] = presenca_global.get(c, 0) + 1
    for d in resultados_dojos:
        alunos = d.get("alunos", [])
        media = sum(r["nota_final"] for r in alunos) / len(alunos) if alunos else 0.0
        aprovados = sum(1 for r in alunos if r["status"] == "APROVADO")
        taxa_aprov = aprovados / len(alunos) * 100 if alunos else 0.0
        linhas.append(f"Dojo {d['dojo_id']}: média {media:.1f} | "
                      f"aprovação {taxa_aprov:.0f}%")
        anterior = d.get("media_anterior")
        if anterior is not None and media < anterior:
            linhas.append(f"  -> Alerta de acompanhamento: média caiu de "
                          f"{anterior:.1f} para {media:.1f} (exame anterior).")
    linhas.append("")
    linhas.append("DIRETRIZES PEDAGOGICAS GLOBAIS (critério em 50%+ dos Dojos):")
    if n_dojos and presenca_global:
        diretrizes = sorted(
            ((c, count) for c, count in presenca_global.items()
             if count / n_dojos >= 0.5),
            key=lambda x: -x[1],
        )
        if diretrizes:
            for (quesito, chave), count in diretrizes:
                linhas.append(f"- {NOME_QUESITO[quesito]} - "
                              f"{NOME_CRITERIO.get(chave, chave)} "
                              f"({count}/{n_dojos} Dojos): {recomendacoes.get(chave, '')}")
        else:
            linhas.append("- Nenhum critério atingiu 50% de recorrência entre Dojos.")
    else:
        linhas.append("- Sem dados suficientes.")
    return "\n".join(linhas)