"""core/relatorios.py — Relatórios do Karate-Ashi v2.0.

Duas camadas de geração (novas, usadas pelo pipeline):
  - gerar_relatorio_sensei : operacional, por dojo/exame (menos detalhe).
  - gerar_relatorio_master : estratégico, multi-dojo (incidência %, ranking,
    recomendações + exercícios corretivos).

Cada gerador devolve (texto, json): o texto vai para Telegram/leitura e o
JSON estruturado fica disponível para o pipeline. Os diretórios de saída são
distintos (sensei/ vs master/) — definidos pelo chamador (core/pipeline.py).

Funções LEGADAS (relatorio_individual, consolidar_dojo,
formatar_consolidado_dojo, relatorio_tendencias, relatorio_master) são
mantidas por compatibilidade com tests/test_relatorios.py — o pipeline v2.0
não as emite mais.

Consome os resultados do motor (Fase 01): dict por aluno com
"quesitos" -> {kihon|kata|bunkai|kumite} -> {"alerta", "detalhes"}, onde
"detalhes" mapeia a chave semântica do critério (ex.: "base_incorreta")
para {"fc", "marcacoes", "nome"}.
"""
from __future__ import annotations

from core.config import QUESITOS as QUESITOS_ORDEM, carregar_json  # fonte única (Fase 4)

NOME_QUESITO = {
    "kihon": "Kihon",
    "kata": "Kata",
    "bunkai": "Bunkai",
    "kumite": "Kumite",
}

# Mapeamento de códigos técnicos A1-A12 -> chave semântica.
# A9 (defesa_incompleta) e A12 (tensao_respiracao) foram EXTINTOS na v2.0 e
# não existem em config/faixas/*.json. Sem migração de dados legados, não há
# motivo para mantê-los — foram removidos.
CODIGO_CHAVE = {
    "A1": "base_incorreta",
    "A2": "execucao_tecnica_incorreta",
    "A3": "movimento_sem_carga",
    "A4": "ausencia_kiai",
    "A5": "embusen_incorreto",
    "A6": "falta_foco",
    "A7": "perda_equilibrio",
    "A8": "falta_ritmo",
    "A10": "falta_controle",
    "A11": "distancia_inadequada",
}

# Somente critérios vigentes na tabela v2.0 (config/faixas/*.json).
NOME_CRITERIO = {
    "base_incorreta": "Base incorreta",
    "execucao_tecnica_incorreta": "Execução técnica incorreta",
    "movimento_sem_carga": "Movimento sem carga",
    "ausencia_kiai": "Ausência de kiai",
    "embusen_incorreto": "Embusen incorreto",
    "falta_foco": "Falta de foco",
    "perda_equilibrio": "Perda de equilíbrio",
    "falta_ritmo": "Falta de ritmo",
    "falta_controle": "Falta de controle",
    "distancia_inadequada": "Distância inadequada",
    "falta_combatividade": "Falta de combatividade",
}

STATUS_ORDEM = ["APROVADO", "RECUPERACAO", "REPROVADO",
                "AUSENTE", "REVISAO_PENDENTE"]

NIVEL_ORDEM = {"CRITICO": 0, "ATENCAO": 1, "OBSERVACAO": 2, "FORCA": 3}


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
        nivel = {"CRITICO": "ATENCAO", "ATENCAO": "OBSERVACAO"}.get(nivel, nivel)
    elif n_avaliadores >= 2 and len(presentes) == n_avaliadores:
        nivel = {"OBSERVACAO": "ATENCAO", "ATENCAO": "CRITICO"}.get(nivel, nivel)
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
                "criterio": det.get("nome") or NOME_CRITERIO.get(chave, chave),
                "texto": recomendacoes.get(chave, ""),
            })
    return sorted(itens, key=lambda x: NIVEL_ORDEM[x["nivel"]])


def gerar_elogios(resultado: dict, regras: dict, recomendacoes: dict) -> list[str]:
    """Elogios: critério transversal zerado, quesito perfeito, destaque geral."""
    elogios = []
    presenca: dict[str, list[tuple[str, list[int]]]] = {}
    for quesito, q in resultado["quesitos"].items():
        for chave, det in q["detalhes"].items():
            presenca.setdefault(chave, []).append(
                (NOME_QUESITO[quesito], det["marcacoes"]))
    for chave, ocorrencias in presenca.items():
        zerados = [nome for nome, ms in ocorrencias if all(m == 0 for m in ms)]
        if len(zerados) >= regras["elogios"]["criterio_transversal_min_quesitos"]:
            nome_criterio = NOME_CRITERIO.get(chave, chave)
            elogios.append(
                recomendacoes["elogio_transversal"]
                .replace("{criterio}", nome_criterio)
                .replace("{quesitos}", ", ".join(zerados)))
            break
    for quesito, q in resultado["quesitos"].items():
        if all(det["fc"] == 0 for det in q["detalhes"].values()):
            elogios.append(recomendacoes["elogio_quesito_perfeito"]
                           .replace("{quesito}", NOME_QUESITO[quesito]))
    if resultado["nota_final"] >= regras["elogios"]["destaque_geral_min"]:
        elogios.append(recomendacoes["destaque_geral"])
    return elogios


def _grupo_por_status(resultados: list[dict]) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {s: [] for s in STATUS_ORDEM}
    for r in resultados:
        grupos.setdefault(r.get("status") or "REVISAO_PENDENTE", []).append(r)
    return grupos


def _observacoes_aluno(r: dict) -> dict:
    obs = r.get("observacoes") or {}
    manuais = list(obs.get("gerais") or [])
    for lista in (obs.get("por_quesito") or {}).values():
        manuais.extend(lista)
    automaticas = [o.get("texto", "")
                   for o in (r.get("observacoes_automaticas") or [])]
    return {"manuais": manuais, "automaticas": automaticas}


def _resumo_aluno(r: dict) -> dict:
    return {"aluno_id": r.get("aluno_id", "?"),
            "faixa": r.get("faixa", ""),
            "nota_final": r.get("nota_final", 0.0)}


# --------------------------------------------------------------------------
# Camada SENSEI — operacional, por dojo/exame (menos detalhe)
# --------------------------------------------------------------------------
def gerar_relatorio_sensei(resultados: list[dict], regras: dict,
                           recomendacoes: dict,
                           dojo_id: str = "D01",
                           exame_id: str = "") -> tuple[str, dict]:
    """Relatório do Sensei: status agregado + observações gerais.

    Devolve (texto, json). Ausentes aparecem em lista própria e são
    identificados com clareza (sem nota que afete médias).
    """
    n_total = len(resultados)
    presentes = [r for r in resultados if r.get("status") != "AUSENTE"]
    grupos = _grupo_por_status(resultados)

    dados = {
        "tipo": "sensei",
        "dojo_id": dojo_id,
        "exame_id": exame_id,
        "total_alunos": n_total,
        "total_presentes": len(presentes),
        "status": {s: len(grupos[s]) for s in STATUS_ORDEM},
        "aprovados": [_resumo_aluno(r) for r in grupos["APROVADO"]],
        "recuperacao": [_resumo_aluno(r) for r in grupos["RECUPERACAO"]],
        "reprovados": [_resumo_aluno(r) for r in grupos["REPROVADO"]],
        "ausentes": [_resumo_aluno(r) for r in grupos["AUSENTE"]],
        "revisao_pendente": [r.get("aluno_id", "?")
                             for r in grupos["REVISAO_PENDENTE"]],
        "observacoes": [
            {"aluno_id": r.get("aluno_id", "?"),
             "status": r.get("status", "?"),
             **_observacoes_aluno(r)}
            for r in resultados
        ],
    }

    linhas = [f"RELATORIO DO SENSEI — DOJO {dojo_id}"]
    if exame_id:
        linhas.append(f"Exame: {exame_id}")
    linhas.append(f"Total de alunos: {n_total} | Presentes: {len(presentes)} | "
                  f"Ausentes: {len(grupos['AUSENTE'])}")
    linhas.append("")
    linhas.append(
        f"STATUS: Aprovado {len(grupos['APROVADO'])} | "
        f"Recuperacao {len(grupos['RECUPERACAO'])} | "
        f"Reprovado {len(grupos['REPROVADO'])} | "
        f"Revisao pendente {len(grupos['REVISAO_PENDENTE'])} | "
        f"Ausente {len(grupos['AUSENTE'])}")
    linhas.append("")

    def _bloco(titulo: str, lista: list[dict]) -> None:
        linhas.append(titulo)
        if not lista:
            linhas.append("- (nenhum)")
        for r in lista:
            linhas.append(f"- {r['aluno_id']} ({r['faixa']}) — {r['nota_final']}")
        linhas.append("")

    _bloco("APROVADOS:", dados["aprovados"])
    _bloco("EM RECUPERACAO:", dados["recuperacao"])
    _bloco("REPROVADOS:", dados["reprovados"])
    _bloco("AUSENTES:", dados["ausentes"])

    linhas.append("OBSERVACOES GERAIS:")
    for obs in dados["observacoes"]:
        linhas.append(f"- {obs['aluno_id']} ({obs['status']}):")
        if obs["manuais"]:
            linhas.append(f"    Avaliador: {'; '.join(obs['manuais'])}")
        if obs["automaticas"]:
            linhas.append(f"    Automaticas: {'; '.join(obs['automaticas'])}")
        if not obs["manuais"] and not obs["automaticas"]:
            linhas.append("    (sem observações)")

    return "\n".join(linhas), dados


# --------------------------------------------------------------------------
# Camada MASTER — estratégico, multi-dojo (mais detalhe)
# --------------------------------------------------------------------------
def gerar_relatorio_master(resultados_dojos: list[dict], regras: dict,
                           recomendacoes: dict) -> tuple[str, dict]:
    """Relatório Master: incidência %, ranking e recomendações por critério.

    Percentuais calculados sobre o total de PRESENTES (ausentes não são
    avaliados). Devolve (texto, json).
    """
    if not resultados_dojos:
        return ("RELATORIO MASTER MULTI-DOJO\n\nSem dados de dojos.",
                {"tipo": "master", "dojos": [], "ranking": [],
                 "diretrizes": []})

    incid: dict[tuple, dict] = {}
    n_presentes_total = 0
    dojos_json = []

    for d in resultados_dojos:
        alunos = d.get("alunos") or []
        presentes = [r for r in alunos if r.get("status") != "AUSENTE"]
        n_presentes_total += len(presentes)
        media = (sum(r.get("nota_final", 0.0) for r in presentes) / len(presentes)
                 if presentes else 0.0)
        aprov = sum(1 for r in presentes if r.get("status") == "APROVADO")
        taxa = aprov / len(presentes) * 100 if presentes else 0.0
        dojos_json.append({
            "dojo_id": d.get("dojo_id", "D01"),
            "total_alunos": len(alunos),
            "presentes": len(presentes),
            "media": round(media, 1),
            "taxa_aprovacao": round(taxa, 1),
        })
        for r in presentes:
            for quesito, q in (r.get("quesitos") or {}).items():
                for chave, det in (q or {}).get("detalhes", {}).items():
                    if det and det.get("fc", 0) > 0:
                        cell = incid.setdefault(
                            (quesito, chave),
                            {"contagem": 0, "soma_fc": 0.0})
                        cell["contagem"] += 1
                        cell["soma_fc"] += det["fc"]

    if n_presentes_total == 0:
        return ("RELATORIO MASTER MULTI-DOJO\n\n"
                "Nenhum aluno presente para análise.",
                {"tipo": "master", "dojos": dojos_json,
                 "n_presentes_total": 0, "ranking": [], "diretrizes": []})

    ranking = sorted(
        ((q, c, cell) for (q, c), cell in incid.items()),
        key=lambda x: (-x[2]["contagem"], -x[2]["soma_fc"]),
    )
    ranking_json = [
        {
            "quesito": NOME_QUESITO[q],
            "criterio": chave,
            "alunos_com_marcacao": cell["contagem"],
            "incidencia_pct": round(cell["contagem"] / n_presentes_total * 100, 1),
            "soma_fc": round(cell["soma_fc"], 1),
            "media_fc": round(cell["soma_fc"] / cell["contagem"], 1),
            "nivel": nivel_por_fc(cell["soma_fc"] / cell["contagem"]),
        }
        for q, chave, cell in ranking
    ]

    diretrizes_json = [
        e for e in ranking_json if e["incidencia_pct"] >= 50.0
    ]
    for e in diretrizes_json:
        e["recomendacao"] = recomendacoes.get(e["criterio"], "")
        e["exercicio"] = recomendacoes.get("exercicios", {}).get(e["criterio"], "")

    dados = {
        "tipo": "master",
        "dojos": dojos_json,
        "n_presentes_total": n_presentes_total,
        "ranking": ranking_json,
        "diretrizes": diretrizes_json,
    }

    linhas = ["RELATORIO MASTER MULTI-DOJO",
              f"Dojos considerados: {len(resultados_dojos)}",
              f"Alunos presentes: {n_presentes_total}",
              ""]
    for dj in dojos_json:
        linhas.append(f"Dojo {dj['dojo_id']}: média {dj['media']} | "
                      f"aprovação {dj['taxa_aprovacao']:.0f}% "
                      f"({dj['presentes']} presentes / {dj['total_alunos']} total)")
    linhas.append("")
    linhas.append("RANKING DE CRITERIOS MAIS MARCADOS:")
    for i, e in enumerate(ranking_json, 1):
        linhas.append(
            f"{i}. {e['quesito']} - {NOME_CRITERIO.get(e['criterio'], e['criterio'])} "
            f"({e['incidencia_pct']:.0f}% dos presentes, média fc {e['media_fc']:.1f})")
    linhas.append("")
    linhas.append("DIRETRIZES PEDAGOGICAS (incidencia >= 50%):")
    if diretrizes_json:
        for e in diretrizes_json:
            linhas.append(f"- {e['quesito']} - "
                          f"{NOME_CRITERIO.get(e['criterio'], e['criterio'])} "
                          f"({e['incidencia_pct']:.0f}%): {e['recomendacao']}")
            if e["exercicio"]:
                linhas.append(f"    Exercicio corretivo: {e['exercicio']}")
    else:
        linhas.append("- Nenhum critério atingiu 50% de incidência.")

    return "\n".join(linhas), dados


# --------------------------------------------------------------------------
# Funções LEGADAS — mantidas por compatibilidade com tests/test_relatorios.py
# (o pipeline v2.0 não as emite mais)
# --------------------------------------------------------------------------
def relatorio_individual(resultado: dict, regras: dict, recomendacoes: dict,
                         aluno: dict) -> str:
    """Relatório 1 (legado) — texto por aluno, na ordem normativa."""
    linhas = [
        f"ALUNO: {aluno.get('nome', '')}",
        f"NOTA FINAL: {resultado['nota_final']} STATUS: {resultado['status']}",
        "",
    ]
    for quesito, q in resultado["quesitos"].items():
        if q.get("alerta") == "ALERTA_ETICO":
            linhas.append("** ALERTA ETICO **")
            linhas.append(f"{NOME_QUESITO[quesito]}: falta de controle "
                          "sinalizada sem consenso — atenção máxima.")
            linhas.append("")
    linhas.append("RECOMENDACOES:")
    for item in gerar_recomendacoes(resultado, recomendacoes):
        linhas.append(f"[{item['nivel']}] {item['quesito']} - "
                      f"{item['criterio']}: {item['texto']}")
    linhas.append("")
    elogios = gerar_elogios(resultado, regras, recomendacoes)
    if elogios:
        linhas.append("PONTOS FORTES:")
        linhas.extend(f"- {e}" for e in elogios)
    obs_auto = resultado.get("observacoes_automaticas", [])
    if obs_auto:
        linhas.append("")
        linhas.append("OBSERVACOES AUTOMATICAS (baseadas nas marcações):")
        for obs in obs_auto:
            linhas.append(f"- {obs.get('texto', '')}")
    return "\n".join(linhas)


def consolidar_dojo(resultados_alunos: list[dict], regras: dict) -> dict:
    """Agregações do Dojo (recorrência 50%/80%) — tolerante a AUSENTE."""
    resultados_alunos = [r for r in resultados_alunos
                         if r.get("status") != "AUSENTE"]
    n = len(resultados_alunos)
    taxa = {s: 0 for s in STATUS_ORDEM}
    for r in resultados_alunos:
        taxa[r["status"]] = taxa.get(r["status"], 0) + 1
    presenca_criterio: dict[tuple, int] = {}
    for r in resultados_alunos:
        for quesito, q in r["quesitos"].items():
            for chave, det in q["detalhes"].items():
                if det["fc"] > 0:
                    presenca_criterio[(quesito, chave)] = (
                        presenca_criterio.get((quesito, chave), 0) + 1)
    prioridades = []
    for (quesito, chave), count in presenca_criterio.items():
        fracao = count / n if n else 0
        if fracao >= 0.80:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}",
                                "Prioridade máxima de treino"))
        elif fracao >= 0.50:
            prioridades.append((f"{NOME_QUESITO[quesito]}.{chave}",
                                "Prioridade de treino do Dojo"))
    medias_quesito = {q: [] for q in QUESITOS_ORDEM}
    for r in resultados_alunos:
        for q in QUESITOS_ORDEM:
            medias_quesito[q].append(r["quesitos"][q].get("nota", 25.0))
    foco = min(medias_quesito, key=lambda q: (
        sum(medias_quesito[q]) / len(medias_quesito[q])
        if medias_quesito[q] else 25.0))
    return {
        "total_alunos": n,
        "taxa": {k: round(v / n * 100, 1) if n else 0.0
                 for k, v in taxa.items()},
        "prioridades_treino": prioridades,
        "foco_ciclo": NOME_QUESITO[foco],
    }


def formatar_consolidado_dojo(consolidado: dict) -> str:
    """Texto do Consolidado do Dojo (legado)."""
    linhas = ["RELATORIO CONSOLIDADO DO DOJO", ""]
    linhas.append(f"Total de alunos avaliados: {consolidado['total_alunos']}")
    taxa = consolidado["taxa"]
    linhas.append(
        f"Taxa de status: Aprovado {taxa['APROVADO']}% | "
        f"Recuperação {taxa['RECUPERACAO']}% | "
        f"Reprovado {taxa['REPROVADO']}% | "
        f"Revisão pendente {taxa['REVISAO_PENDENTE']}% | "
        f"Ausente {taxa['AUSENTE']}%")
    linhas.append(f"Foco do ciclo: {consolidado['foco_ciclo']} (pior média)")
    linhas.append("")
    linhas.append("PRIORIDADES DE TREINO:")
    for item, rotulo in consolidado["prioridades_treino"]:
        quesito, chave = item.split(".", 1)
        linhas.append(f"- {quesito} - {NOME_CRITERIO.get(chave, chave)}: {rotulo}")
    return "\n".join(linhas)


def relatorio_tendencias(resultados_alunos: list[dict], recomendacoes: dict) -> str:
    """Tendências (legado) — agregação em %, moda e narrativa por intensidade."""
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
            linhas.append(f" Exercício corretivo: {exercicio}")
    return "\n".join(linhas)


def relatorio_master(resultados_dojos: list[dict], regras: dict,
                     recomendacoes: dict) -> str:
    """Master (legado) — visão estratégica multi-Dojo (texto resumido)."""
    if not resultados_dojos:
        return "RELATORIO MASTER MULTI-DOJO\n\nSem dados de dojos."
    linhas = ["RELATORIO MASTER MULTI-DOJO", ""]
    n_dojos = len(resultados_dojos)
    presenca_global: dict[tuple, int] = {}
    for d in resultados_dojos:
        criterios_dojo = set()
        for r in d.get("alunos") or []:
            quesitos = r.get("quesitos") or {}
            for quesito, q in quesitos.items():
                detalhes = (q or {}).get("detalhes") or {}
                for chave, det in detalhes.items():
                    if det and det.get("fc", 0) > 0:
                        criterios_dojo.add((quesito, chave))
        for c in criterios_dojo:
            presenca_global[c] = presenca_global.get(c, 0) + 1
    for d in resultados_dojos:
        alunos = d.get("alunos") or []
        media = (sum(r.get("nota_final", 0.0) for r in alunos) / len(alunos)
                 if alunos else 0.0)
        aprovados = sum(1 for r in alunos if r.get("status") == "APROVADO")
        taxa_aprov = aprovados / len(alunos) * 100 if alunos else 0.0
        linhas.append(f"Dojo {d['dojo_id']}: média {media:.1f} | "
                      f"aprovação {taxa_aprov:.0f}%")
        anterior = d.get("media_anterior")
        if anterior is not None and media < anterior:
            linhas.append(f" -> Alerta de acompanhamento: média caiu de "
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
                              f"({count}/{n_dojos} Dojos): "
                              f"{recomendacoes.get(chave, '')}")
        else:
            linhas.append("- Nenhum critério atingiu 50% de recorrência entre Dojos.")
    else:
        linhas.append("- Sem dados suficientes.")
    return "\n".join(linhas)