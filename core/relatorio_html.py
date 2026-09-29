"""core/relatorio_html.py — Relatório visual (HTML autossuficiente) do Karate-Ashi v2.0.

Gera HTML com CSS embutido (sem dependências externas), pronto para preview no
Google Drive, impressão em A4 e arquivamento. Reutiliza os dados estruturados
do core.relatorios (resultado do processa_aluno e funções de relatório).

Repartição de responsabilidades:
  - Sensei (dojo): nota, notas por quesito (mini-barras), tabela de marcações
    por quesito × avaliador (frequência real) e observações POR AVALIADOR
    (com autoria). SEM recomendações, SEM agregados de dojo, SEM tendências.
    Nome do aluno exibido COMPLETO (no relatório não há limite de espaço).
  - Master (consolidado): o mais completo — desempenho por dojo, notas por
    quesito por aluno, % de marcações dos critérios por quesito (intensidade
    média 1 a 5), recomendações sugeridas (nº de alunos, %, intensidade média
    e motivo) e observações dos avaliadores.
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from core.relatorios import NOME_QUESITO, gerar_relatorio_master

# --- Cores ----------------------------------------------------------------
COR_STATUS = {
    "APROVADO": ("#1a7f37", "#e6f4ea"),
    "APROVADO_PONTO_ATENCAO": ("#b7791f", "#fdf3e7"),
    "RECUPERACAO": ("#b7791f", "#fdf3e7"),
    "REPROVADO": ("#c62828", "#fdecea"),
    "REVISAO_PENDENTE": ("#6a737d", "#eef1f4"),
    "AUSENTE": ("#6a737d", "#eef1f4"),
}
COR_QUESITO = {
    "kihon": "#1f4e79",
    "kata": "#7b2d8b",
    "bunkai": "#b45309",
    "kumite": "#b91c1c",
}


def _esc(t) -> str:
    return html.escape(str(t), quote=True)


def _status_cor(status: str) -> tuple[str, str]:
    return COR_STATUS.get(status, ("#6a737d", "#eef1f4"))


def _texto_recomendacao(recomendacoes: dict, chave: str) -> str:
    """Texto da recomendação de forma tolerante (str ou dict)."""
    v = (recomendacoes or {}).get(chave, "")
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return v.get("texto") or v.get("recomendacao") or ""
    return ""


# ═══════════════════════════════ SENSEI (dojo) ═══════════════════════════════

def _tabela_marcacoes(r: dict, avaliadores_map: dict | None) -> str:
    """Tabela de marcações: linhas = critérios, colunas = avaliadores.

    Usa a FREQUÊNCIA REAL (escala 1 a 5) que cada avaliador marcou.
    """
    por_av = r.get("frequencias_por_avaliador") or []
    av_ids = r.get("avaliadores_ids") or [f"A{i + 1}" for i in range(len(por_av))]
    labels = []
    for aid in av_ids:
        nome = (avaliadores_map or {}).get(str(aid), "") or aid
        labels.append(nome)
    if not labels:
        labels = ["Avaliador 1"]

    quesitos = r.get("quesitos") or {}
    blocos = []
    for q, qnome in NOME_QUESITO.items():
        det = (quesitos.get(q) or {}).get("detalhes") or {}
        linhas = []
        tem_marcacao = False
        for chave, d in det.items():
            vals = []
            marcou = False
            for avp in por_av:
                f = int((avp.get(q) or {}).get(chave, 0) or 0)
                vals.append(f)
                if f:
                    marcou = True
            if not marcou:
                continue
            tem_marcacao = True
            tds = "".join(f"<td>{v if v else ''}</td>" for v in vals)
            linhas.append(
                f'<tr><td class="crit">{_esc(d.get("nome") or chave)}</td>{tds}</tr>'
            )
        if not tem_marcacao:
            continue
        th = "".join(f"<th>{_esc(lb)}</th>" for lb in labels)
        blocos.append(
            f'<div class="marc-bloco"><span class="marc-q-nome">{_esc(qnome)}</span>'
            f'<table class="tab"><thead><tr><th>Critério</th>{th}</tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div>'
        )
    return "".join(blocos) or "<p class='vazio'>Sem critérios marcados.</p>"


def _obs_com_autoria(r: dict, avaliadores_map: dict | None) -> str:
    """Observações dos avaliadores com o nome de quem marcou."""
    obs = r.get("observacoes_por_avaliador") or []
    linhas = []
    for o in obs:
        av = o.get("avaliador") or "Avaliador"
        nome_av = (avaliadores_map or {}).get(str(av), "") or av
        texto = (o.get("observacao") or "").strip() or "Sem observação"
        linhas.append(
            f'<li><span class="avaliador">{_esc(nome_av)}</span>: {_esc(texto)}</li>'
        )
    return "".join(linhas) or "<li>Sem observações.</li>"


def _card_aluno_sensei(r: dict, nomes: dict | None, avaliadores_map: dict | None) -> str:
    aluno_id = str(r.get("aluno_id", "?"))
    nome = (nomes or {}).get(aluno_id, "") or aluno_id
    faixa = r.get("faixa", "")
    nota = r.get("nota_final", 0.0)
    status = r.get("status", "?")
    fg, bg = _status_cor(status)

    # Notas por quesito (mini-barras)
    notas_q = []
    for q, qnome in NOME_QUESITO.items():
        nq = (r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0)
        corq = COR_QUESITO.get(q, "#333")
        notas_q.append(
            f'<div class="mini-q"><span class="mini-q-nome">{_esc(qnome)}</span>'
            f'<div class="mini-q-bar"><div class="mini-q-fill" '
            f'style="width:{min(100, nq / 25 * 100):.0f}%;background:{corq}"></div></div>'
            f'<span class="mini-q-val">{nq:.1f}</span></div>'
        )

    marcacoes = _tabela_marcacoes(r, avaliadores_map)
    obs = _obs_com_autoria(r, avaliadores_map)

    return f"""
    <article class="card aluno" style="border-left:6px solid {fg}">
      <header class="aluno-head">
        <div>
          <h3>{_esc(nome)}</h3>
          <span class="faixa">Faixa {_esc(faixa)}</span>
        </div>
        <div class="aluno-num">
          <span class="nota">{nota:.1f}</span>
          <span class="status" style="background:{fg};color:#fff">{_esc(status)}</span>
        </div>
      </header>
      <div class="mini-quesitos">{''.join(notas_q)}</div>
      <div class="secao">
        <h4>Marcações por quesito e avaliador</h4>
        {marcacoes}
      </div>
      <div class="secao">
        <h4>Observações dos avaliadores</h4>
        <ul class="obs">{obs}</ul>
      </div>
    </article>"""


def gerar_html_exame(
    resultados: list[dict],
    regras: dict,
    recomendacoes: dict,
    dojo_id: str = "DOJO",
    exame_id: str = "",
    titulo: str = "Relatório do Sensei",
    nomes: dict | None = None,
    sensei_responsavel: str = "",
    avaliadores_map: dict | None = None,
) -> str:
    """HTML do relatório do Sensei (dojo) — enxuto, sem recomendações."""
    cards = "".join(_card_aluno_sensei(r, nomes, avaliadores_map) for r in resultados)

    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_aprov = sum(1 for r in resultados
                  if r.get("status") in ("APROVADO", "APROVADO_PONTO_ATENCAO"))
    media = (sum(r.get("nota_final", 0.0) for r in resultados) / len(resultados)
             if resultados else 0.0)
    n_faixas = len({_esc(r.get("faixa", "")) for r in resultados})

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
  :root {{ --preto:#1a1a1a; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',Roboto,Arial,sans-serif; margin:0; color:#222; background:#eef0f3; }}
  .pagina {{ max-width:960px; margin:0 auto; padding:24px; }}
  .capa {{ background:linear-gradient(135deg,var(--preto),#333); color:#fff; border-radius:14px;
           padding:28px 32px; margin-bottom:22px; }}
  .capa h1 {{ margin:0 0 6px; font-size:26px; }}
  .capa .sub {{ color:#ccc; font-size:14px; }}
  .capa .meta {{ margin-top:14px; display:flex; gap:22px; flex-wrap:wrap; font-size:13px; }}
  .capa .meta b {{ color:#fff; }}
  .resumo {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:22px; }}
  .metric {{ background:#fff; border-radius:12px; padding:16px; text-align:center;
             box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .metric-t {{ display:block; font-size:12px; color:#666; text-transform:uppercase; letter-spacing:.5px; }}
  .metric-v {{ display:block; font-size:24px; font-weight:700; margin-top:4px; }}
  .alunos {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .card {{ background:#fff; border-radius:12px; padding:18px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .aluno-head {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px; }}
  .aluno-head h3 {{ margin:0; font-size:18px; }}
  .faixa {{ color:#666; font-size:13px; }}
  .aluno-num {{ text-align:right; }}
  .nota {{ font-size:26px; font-weight:800; }}
  .status {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:700; }}
  .mini-quesitos {{ margin:10px 0 14px; }}
  .mini-q {{ display:flex; align-items:center; gap:8px; margin:4px 0; font-size:12px; }}
  .mini-q-nome {{ width:64px; color:#555; }}
  .mini-q-bar {{ flex:1; height:8px; background:#eef0f3; border-radius:4px; overflow:hidden; }}
  .mini-q-fill {{ height:100%; border-radius:4px; }}
  .mini-q-val {{ width:34px; text-align:right; font-weight:600; }}
  .secao {{ margin-top:12px; }}
  .secao h4 {{ margin:0 0 6px; font-size:13px; text-transform:uppercase; color:#555; letter-spacing:.5px; }}
  ul {{ margin:0; padding-left:0; list-style:none; }}
  .obs li {{ padding:5px 0; border-bottom:1px solid #f0f0f0; font-size:13px; }}
  .obs li:last-child {{ border-bottom:none; }}
  .obs .avaliador {{ font-weight:700; color:#1f4e79; }}
  .marc-bloco {{ margin:8px 0; }}
  .marc-q-nome {{ display:block; font-weight:700; color:#555; font-size:12px; text-transform:uppercase; margin-bottom:4px; }}
  table.tab {{ width:100%; border-collapse:collapse; font-size:12px; }}
  table.tab th, table.tab td {{ border:1px solid #e0e0e0; padding:4px 8px; text-align:center; }}
  table.tab th {{ background:#f4f5f7; color:#444; font-weight:600; }}
  table.tab td.crit {{ text-align:left; color:#333; }}
  .vazio {{ color:#999; font-size:12px; }}
  @media print {{ body {{ background:#fff; }} .pagina {{ max-width:100%; padding:0; }}
                 .card {{ box-shadow:none; break-inside:avoid; }} .capa {{ border-radius:0; }} }}
  @media (max-width:700px) {{ .alunos, .resumo {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
  <div class="pagina">
    <header class="capa">
      <h1>{_esc(titulo)}</h1>
      <div class="sub">Sistema Karate-Ashi · Relatório do Sensei</div>
      <div class="meta">
        <div><b>Dojo:</b> {_esc(dojo_id)}</div>
        <div><b>Sensei responsável:</b> {_esc(sensei_responsavel) or '—'}</div>
        <div><b>Exame:</b> {_esc(exame_id) or '—'}</div>
        <div><b>Alunos:</b> {len(resultados)}</div>
        <div><b>Gerado em:</b> {_esc(data)}</div>
      </div>
    </header>

    <div class="resumo">
      <div class="metric"><span class="metric-t">Alunos</span><span class="metric-v">{len(resultados)}</span></div>
      <div class="metric"><span class="metric-t">Aprovados</span><span class="metric-v" style="color:#1a7f37">{n_aprov}</span></div>
      <div class="metric"><span class="metric-t">Média</span><span class="metric-v" style="color:#1f4e79">{media:.1f}</span></div>
      <div class="metric"><span class="metric-t">Faixas</span><span class="metric-v" style="color:#b45309">{n_faixas}</span></div>
    </div>

    <div class="alunos">{cards}</div>
  </div>
</body>
</html>"""


def salvar_html_exame(
    resultados: list[dict],
    regras: dict,
    recomendacoes: dict,
    destino: Path,
    dojo_id: str = "DOJO",
    exame_id: str = "",
    titulo: str = "Relatório do Sensei",
    nomes: dict | None = None,
    sensei_responsavel: str = "",
    avaliadores_map: dict | None = None,
) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        gerar_html_exame(resultados, regras, recomendacoes, dojo_id, exame_id,
                         titulo, nomes, sensei_responsavel, avaliadores_map),
        encoding="utf-8",
    )
    return destino


# ═══════════════════════════════ MASTER (consolidado) ═══════════════════════════════

def _agregar_criterios(resultados: list[dict]) -> list[dict]:
    """Agrega critérios marcados com frequência REAL: nº de alunos, % e intensidade.

    frequencias_reais é gravada pelo pipeline (modo_presenca=False) — soma das
    marcações reais (escala 1 a 5) por critério em cada aluno.
    """
    n = len(resultados)
    nome_map: dict[tuple, str] = {}
    for r in resultados:
        for q, qd in (r.get("quesitos") or {}).items():
            for ch, d in (qd.get("detalhes") or {}).items():
                nome_map.setdefault((q, ch), d.get("nome") or ch)
    agg: dict[tuple, dict] = {}
    for r in resultados:
        for q, blocos in (r.get("frequencias_reais") or {}).items():
            for ch, freq in blocos.items():
                if not freq:
                    continue
                e = agg.setdefault((q, ch), {"count": 0, "soma": 0})
                e["count"] += 1
                e["soma"] += int(freq)
    itens = []
    for (q, ch), e in agg.items():
        itens.append({
            "quesito": q, "chave": ch,
            "nome": nome_map.get((q, ch), ch),
            "count": e["count"],
            "pct": e["count"] / n * 100 if n else 0.0,
            "intens": e["soma"] / e["count"] if e["count"] else 0.0,
        })
    itens.sort(key=lambda x: (-x["count"], -x["intens"]))
    return itens


def _agregar_recomendacoes(resultados: list[dict], recomendacoes: dict) -> list[dict]:
    itens = _agregar_criterios(resultados)
    for it in itens:
        it["texto"] = _texto_recomendacao(recomendacoes, it["chave"])
    return itens


def _bloco_marcacoes_quesito(resultados: list[dict]) -> str:
    """% de marcações dos critérios por quesito + intensidade média (1 a 5)."""
    itens = _agregar_criterios(resultados)
    if not itens:
        return ('<section class="bloco"><h2>Critérios Marcados por Quesito</h2>'
                '<p>Nenhum critério marcado neste exame.</p></section>')
    n = len(resultados)
    blocos = []
    for q, qnome in NOME_QUESITO.items():
        sub = [it for it in itens if it["quesito"] == q]
        if not sub:
            continue
        linhas = "".join(
            f'<tr><td>{_esc(it["nome"])}</td>'
            f'<td>{it["count"]} de {n} alunos ({it["pct"]:.0f}%)</td>'
            f'<td>{it["intens"]:.1f}</td></tr>'
            for it in sub
        )
        blocos.append(
            f'<div class="marc-quesito"><h4>{_esc(qnome)}</h4>'
            f'<table class="tab"><thead><tr>'
            f'<th>Critério</th><th>Marcado em</th><th>Intensidade média (1–5)</th>'
            f'</tr></thead><tbody>{linhas}</tbody></table></div>'
        )
    return f"""<section class="bloco">
      <h2>Critérios Marcados por Quesito</h2>
      <p class="sub-bloco">% de alunos cujo avaliador marcou o critério e intensidade média da marcação (1 = raro, 5 = ocorre sempre).</p>
      {''.join(blocos)}
    </section>"""


def _bloco_recomendacoes_master(resultados: list[dict], recomendacoes: dict) -> str:
    itens = _agregar_recomendacoes(resultados, recomendacoes)
    if not itens:
        return ('<section class="bloco"><h2>Recomendações Sugeridas</h2>'
                '<p>Nenhum critério de atenção identificado no exame.</p></section>')
    n = len(resultados)
    linhas = []
    for it in itens:
        cor = COR_QUESITO.get(it["quesito"], "#333")
        linhas.append(
            f'<li class="rec-item">'
            f'<div class="rec-head"><span class="dot" style="background:{cor}"></span>'
            f'<b>{_esc(NOME_QUESITO[it["quesito"]])} — {_esc(it["nome"])}</b>'
            f'<span class="rec-meta">marcado em {it["count"]} de {n} alunos '
            f'({it["pct"]:.0f}%) · intensidade média {it["intens"]:.1f} (1 a 5)</span></div>'
            f'<div class="rec-motivo"><b>Motivo:</b> {_esc(it["texto"]) or "—"}</div>'
            f'</li>'
        )
    return f"""<section class="bloco">
      <h2>Recomendações Sugeridas</h2>
      <p class="sub-bloco">Critérios com problemas identificados no exame: em quantos alunos foi marcado, com que intensidade e o motivo da recomendação.</p>
      <ul class="recs">{''.join(linhas)}</ul>
    </section>"""


def _bloco_notas_quesito(resultados: list[dict], nomes: dict | None) -> str:
    """Tabela de notas por quesito por aluno (ponto 9)."""
    thead = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
    linhas = []
    for r in resultados:
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        tds = "".join(
            f'<td>{(r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0):.1f}</td>'
            for q in NOME_QUESITO
        )
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        linhas.append(
            f'<tr><td class="aluno">{_esc(nome)}</td>{tds}'
            f'<td><b>{r.get("nota_final", 0.0):.1f}</b></td>'
            f'<td><span class="status-mini" style="background:{fg};color:#fff">{_esc(status)}</span></td></tr>'
        )
    return f"""<section class="bloco">
      <h2>Notas por Quesito</h2>
      <table class="tab">
        <thead><tr><th>Aluno</th>{thead}<th>Nota final</th><th>Status</th></tr></thead>
        <tbody>{''.join(linhas)}</tbody>
      </table>
    </section>"""


def _bloco_observacoes_master(resultados: list[dict], nomes: dict | None,
                              avaliadores_map: dict | None) -> str:
    """Observações dos avaliadores por aluno (ponto 8)."""
    blocos = []
    for r in resultados:
        obs = [o for o in (r.get("observacoes_por_avaliador") or [])
               if (o.get("observacao") or "").strip()]
        if not obs:
            continue
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        linhas = "".join(
            f'<li><span class="avaliador">{_esc(((avaliadores_map or {}).get(str(o.get("avaliador") or ""), "")) or o.get("avaliador") or "Avaliador")}</span>: {_esc(o["observacao"])}</li>'
            for o in obs
        )
        blocos.append(
            f'<div class="obs-aluno"><h4>{_esc(nome)}</h4><ul class="obs">{linhas}</ul></div>'
        )
    if not blocos:
        return ""
    return f"""<section class="bloco">
      <h2>Observações dos Avaliadores</h2>
      {''.join(blocos)}
    </section>"""


def gerar_html_master(resultados_dojos: list[dict], regras: dict,
                      recomendacoes: dict, titulo: str = "Relatório Master Consolidado",
                      exame_id: str = "",
                      nomes: dict | None = None,
                      avaliadores_map: dict | None = None) -> str:
    """HTML do Master consolidado — o relatório mais completo (para os mestres)."""
    _, dados = gerar_relatorio_master(resultados_dojos, regras, recomendacoes)
    if not dados.get("dojos"):
        return (f"<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
                f"<title>{_esc(titulo)}</title></head><body>"
                f"<h1>{_esc(titulo)}</h1><p>Sem dados de dojos.</p></body></html>")

    # Alunos vêm do INPUT (o dados do master não carrega a lista)
    todos_alunos = []
    for d in resultados_dojos:
        todos_alunos.extend(d.get("alunos", []))

    linhas_dojo = "".join(
        f'<li><b>{_esc(d["dojo_id"])}</b> — média {d["media"]} · aprovação '
        f'{d["taxa_aprovacao"]:.0f}% (sendo {d["taxa_atencao"]:.0f}% c/ atenção) · '
        f'{d["presentes"]}/{d["total_alunos"]} presentes</li>'
        for d in dados["dojos"]
    ) or "<li>—</li>"

    notas_html = _bloco_notas_quesito(todos_alunos, nomes)
    marcacoes_html = _bloco_marcacoes_quesito(todos_alunos)
    recomendacoes_html = _bloco_recomendacoes_master(todos_alunos, recomendacoes)
    observacoes_html = _bloco_observacoes_master(todos_alunos, nomes, avaliadores_map)

    total_presentes = dados.get("n_presentes_total", 0)
    media_geral = (sum(r.get("nota_final", 0.0) for r in todos_alunos) / len(todos_alunos)
                   if todos_alunos else 0.0)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',Roboto,Arial,sans-serif; margin:0; color:#222; background:#eef0f3; }}
  .pagina {{ max-width:960px; margin:0 auto; padding:24px; }}
  .capa {{ background:linear-gradient(135deg,#1a1a1a,#333); color:#fff; border-radius:14px;
           padding:28px 32px; margin-bottom:22px; }}
  .capa h1 {{ margin:0 0 6px; font-size:26px; }}
  .capa .sub {{ color:#ccc; font-size:14px; }}
  .capa .meta {{ margin-top:14px; display:flex; gap:22px; flex-wrap:wrap; font-size:13px; }}
  .resumo {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin-bottom:22px; }}
  .metric {{ background:#fff; border-radius:12px; padding:16px; text-align:center; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .metric-t {{ display:block; font-size:12px; color:#666; text-transform:uppercase; letter-spacing:.5px; }}
  .metric-v {{ display:block; font-size:24px; font-weight:700; margin-top:4px; }}
  .bloco {{ background:#fff; border-radius:12px; padding:20px; margin-top:18px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .bloco h2 {{ margin:0 0 12px; font-size:18px; color:#1a1a1a; }}
  .bloco h4 {{ margin:14px 0 6px; font-size:13px; text-transform:uppercase; color:#555; }}
  .sub-bloco {{ color:#666; font-size:13px; margin:-6px 0 12px; }}
  ul {{ margin:0; padding-left:0; list-style:none; }}
  li {{ padding:8px 0; border-bottom:1px solid #f0f0f0; font-size:14px; }}
  li:last-child {{ border-bottom:none; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:8px; }}
  .rec-item {{ padding:10px 0; }}
  .rec-head {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
  .rec-meta {{ color:#888; font-size:12px; margin-left:auto; }}
  .rec-motivo {{ color:#555; font-size:13px; margin-top:4px; padding-left:18px; }}
  .marc-quesito {{ margin:10px 0; }}
  .obs-aluno {{ margin:10px 0; }}
  .obs-aluno h4 {{ margin:0 0 4px; }}
  .obs .avaliador {{ font-weight:700; color:#1f4e79; }}
  .obs li {{ padding:5px 0; font-size:13px; }}
  table.tab {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.tab th, table.tab td {{ border:1px solid #e0e0e0; padding:6px 10px; text-align:center; }}
  table.tab th {{ background:#f4f5f7; color:#444; font-weight:600; }}
  table.tab td.aluno {{ text-align:left; font-weight:600; }}
  .status-mini {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }}
  @media print {{ body {{ background:#fff; }} .pagina {{ max-width:100%; padding:0; }}
                 .bloco {{ box-shadow:none; break-inside:avoid; }} }}
</style>
</head>
<body>
  <div class="pagina">
    <header class="capa">
      <h1>{_esc(titulo)}</h1>
      <div class="sub">Sistema Karate-Ashi · Visão Estratégica Multi-Dojo</div>
      <div class="meta">
        <div><b>Exame:</b> {_esc(exame_id) or '—'}</div>
        <div><b>Dojos:</b> {len(dados.get('dojos', []))}</div>
        <div><b>Alunos presentes:</b> {total_presentes}</div>
      </div>
    </header>

    <div class="resumo">
      <div class="metric"><span class="metric-t">Dojos</span><span class="metric-v">{len(dados.get('dojos', []))}</span></div>
      <div class="metric"><span class="metric-t">Alunos presentes</span><span class="metric-v">{total_presentes}</span></div>
      <div class="metric"><span class="metric-t">Média geral</span><span class="metric-v" style="color:#1f4e79">{media_geral:.1f}</span></div>
    </div>

    <section class="bloco">
      <h2>Desempenho por Dojo</h2>
      <ul>{linhas_dojo}</ul>
    </section>

    {notas_html}
    {marcacoes_html}
    {recomendacoes_html}
    {observacoes_html}
  </div>
</body>
</html>"""


def salvar_html_master(resultados_dojos: list[dict], regras: dict,
                       recomendacoes: dict, destino: Path,
                       exame_id: str = "",
                       titulo: str = "Relatório Master Consolidado",
                       nomes: dict | None = None,
                       avaliadores_map: dict | None = None) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        gerar_html_master(resultados_dojos, regras, recomendacoes, titulo, exame_id,
                          nomes, avaliadores_map),
        encoding="utf-8",
    )
    return destino