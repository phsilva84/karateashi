"""core/relatorio_html.py — Relatório visual (HTML autossuficiente) do Karate-Ashi v2.3.
Gera HTML com CSS embutido (sem dependências externas), pronto para preview no
Google Drive, impressão em A4 e arquivamento.
Mudanças v2.1 (revisão do usuário):
  1-2) Nome do AVALIADOR (não o ID) nas colunas de marcações e nas observações,
       via config/avaliadores.json (avaliadores_map). Com 3 avaliadores, a
       tabela de marcações ganha automaticamente 3 colunas.
  3)   Observações separadas em "Pontos fortes (BOM!)" / "A melhorar" / "Outras"
       por avaliador (classificação pelo vocabulário oficial de core/observacoes).
  4)   Relatório do Sensei ganha bloco "Notas por Quesito" (ranking) + coluna
       "Nova Faixa (se aprovado)" — progressão de faixas em config/faixas.json.
  7)   Master: coluna "Intensidade média (1–5)" REMOVIDA de Critérios por Quesito.
  8)   Master: "Recomendações Sugeridas" → rótulos únicos "Recomendação:" e
       "Planejamento Sugerido:" por (quesito, critério). Lê a estrutura
       'por_quesito' de config/recomendacoes.json (textos distintos por
       quesito — ex.: Perda de Equilíbrio no Kihon ≠ no Kata), com fallback
       para as chaves antigas na raiz.
  9)   Master: novo bloco "Análise de Desempenho" (média por quesito + ranking,
       foco do treino, alunos em atenção e destaque do exame).
Mudanças v2.2:
  10)  Relatório INDIVIDUAL por aluno (HTML dedicado p/ imprimir/exportar PDF),
       SEM citar avaliadores: nota final + status, nota por quesito, marcações
       consolidadas por critério e observações resumidas (BOM!/A melhorar/Outras).
       gravado no MESMO diretório do relatório do exame.
  11)  Relatório do Sensei ganha bloco "Resultado do Exame — Lista de Aprovação"
       (tabela Aluno | Faixa | Status, SEM nota e SEM ranking) para divulgação
       ao grupo de alunos/pais.
Mudanças v2.3 (nova revisão do usuário):
  12)  Bloco "Resultado do Exame — Lista de Aprovação" passa a exibir SOMENTE
       alunos aprovados (APROVADO/APROVADO_PONTO_ATENCAO), SEM o subtítulo de
       divulgação e com a coluna "Nova Faixa" (mesma progressão de faixas do
       ranking). Serve como lista oficial de divulgação ao grupo/pais.
  13)  Disposição dos cards de alunos do Sensei em 4 colunas (antes 2), com
       breakpoint responsivo (2 colunas em telas médias, 1 em telas pequenas).
"""
from __future__ import annotations
import html
import json
from datetime import datetime
from pathlib import Path
from core.observacoes import OBS_MELHORAR, OBS_POSITIVAS
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
_RAIZ = Path(__file__).resolve().parents[1]
def _esc(t) -> str:
    return html.escape(str(t), quote=True)
def _status_cor(status: str) -> tuple[str, str]:
    return COR_STATUS.get(status, ("#6a737d", "#eef1f4"))
# --- Config auxiliar (avaliadores + faixas) ---------------------------------
def _carregar_avaliadores_map() -> dict[str, str]:
    """{'S02': 'Sensei Fabio', ...} a partir de config/avaliadores.json."""
    p = _RAIZ / "config" / "avaliadores.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return {str(a.get("id")): str(a.get("nome") or a.get("id") or "")
            for a in doc.get("avaliadores", [])}
def _carregar_ordem_faixas() -> list[str]:
    """Ordem de progressão de faixas a partir de config/faixas.json.
    Usa a estrutura JÁ existente: 'suportadas' + 'placeholder' (nessa
    ordem). marrom/preta podem ficar habilitadas na ordem sem matriz
    própria por enquanto — entram na coluna 'Nova Faixa' quando um aluno
    da faixa anterior for aprovado. Fallback: sequência padrão.
    """
    padrao = ["branca", "amarela", "laranja", "verde", "azul", "roxa",
              "marrom", "preta"]
    try:
        doc = json.loads((_RAIZ / "config" / "faixas.json")
                         .read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — config ausente/inválida não quebra
        return padrao
    suportadas = [str(f).strip().lower() for f in doc.get("suportadas", [])]
    placeholder = [str(f).strip().lower() for f in doc.get("placeholder", [])]
    ordem = suportadas + placeholder
    return ordem or padrao
def _nova_faixa(faixa_atual: str, status: str, ordem: list[str]) -> str:
    """Próxima faixa se APROVADO; 'Mantém faixa' se Recuperação; '—' senão."""
    if status in ("APROVADO", "APROVADO_PONTO_ATENCAO"):
        atual = (faixa_atual or "").strip().lower()
        try:
            i = ordem.index(atual)
        except ValueError:
            return "—"
        if i + 1 < len(ordem):
            return ordem[i + 1].capitalize()
        return "Faixa máxima"
    if status == "RECUPERACAO":
        return "Mantém faixa"
    return "—"
# --- Observações (classificação BOM! / A MELHORAR) --------------------------
_OBS_POSITIVAS_TXT = tuple(t.lower() for t in OBS_POSITIVAS.values())
_OBS_MELHORAR_TXT = tuple(t.lower() for t in OBS_MELHORAR.values())
_PREFIXOS_FORTES = ("boa", "bom", "otim", "ótimo", "excelente", "bem", "grande")
_PREFIXOS_MELHORAR = ("dificuldade", "erros", "falta", "melhorar", "atenção",
                      "nervosismo", "perda", "cabeça", "mais foco", "mais carga")
def _classificar_obs(parte: str) -> str:
    """Retorna 'fortes' | 'melhorar' | 'outras' (chaves de _separar_obs)."""
    t = parte.lower().strip()
    if any(p in t for p in _OBS_POSITIVAS_TXT):
        return "fortes"
    if any(m in t for m in _OBS_MELHORAR_TXT):
        return "melhorar"
    if t.startswith(_PREFIXOS_FORTES):
        return "fortes"
    if t.startswith(_PREFIXOS_MELHORAR):
        return "melhorar"
    return "outras"
def _separar_obs(texto: str) -> dict[str, list[str]]:
    """Divide o texto montado em fortes / melhorar / outras."""
    grupos = {"fortes": [], "melhorar": [], "outras": []}
    for parte in texto.replace(".", ";").replace("\n", ";").split(";"):
        parte = parte.strip()
        if not parte:
            continue
        grupos[_classificar_obs(parte)].append(parte)
    return grupos
def _texto_recomendacao(recomendacoes: dict, quesito: str, chave: str) -> str:
    """Recomendação por (quesito, critério) — lê 'por_quesito' com fallback.
    Se a estrutura 'por_quesito' não tiver a entrada, usa a chave antiga na
    raiz (texto único) e remove um eventual rótulo 'Recomendação:' embutido.
    """
    por_q = (recomendacoes or {}).get("por_quesito", {})
    v = por_q.get(quesito, {}).get(chave, None)
    if v is None:
        texto = str((recomendacoes or {}).get(chave, "") or "")
        if "Recomendação:" in texto:
            texto = texto.split("Recomendação:", 1)[0].strip()
        return texto
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return (v.get("recomendacao") or v.get("motivo")
                or v.get("texto") or "")
    return ""
def _texto_recomendacao_detalhe(recomendacoes: dict, quesito: str,
                                chave: str) -> tuple[str, str]:
    """(Recomendação, Planejamento Sugerido) por (quesito, critério).
    Estrutura nova: dict com 'recomendacao' e 'planejamento'. Fallback para
    a chave antiga na raiz, separando o texto antes/depois de 'Recomendação:'.
    """
    por_q = (recomendacoes or {}).get("por_quesito", {})
    v = por_q.get(quesito, {}).get(chave, None)
    if isinstance(v, dict):
        rec = (v.get("recomendacao") or v.get("motivo") or v.get("texto") or "")
        plano = v.get("planejamento") or v.get("sugerido") or ""
        return str(rec), str(plano)
    if isinstance(v, str):
        return str(v), ""
    # Fallback: chave antiga na raiz (texto único com rótulo embutido)
    texto = str((recomendacoes or {}).get(chave, "") or "")
    if "Recomendação:" in texto:
        antes, depois = texto.split("Recomendação:", 1)
        return antes.strip(), depois.strip(" ()")
    return texto, ""
# ═══════════════════════════════ SENSEI (dojo) ═══════════════════════════════
def _tabela_marcacoes(r: dict, avaliadores_map: dict | None) -> str:
    """Tabela de marcações: linhas = critérios, colunas = avaliadores (nome)."""
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    por_av = r.get("frequencias_por_avaliador") or []
    av_ids = r.get("avaliadores_ids") or [f"A{i + 1}" for i in range(len(por_av))]
    labels = [avaliadores_map.get(str(aid), "") or str(aid) or f"A{i + 1}"
              for i, aid in enumerate(av_ids)] or ["Avaliador 1"]
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
    """Observações dos avaliadores com nome + separação BOM! / A MELHORAR."""
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    obs = r.get("observacoes_por_avaliador") or []
    linhas = []
    for o in obs:
        av = o.get("avaliador") or "Avaliador"
        nome_av = avaliadores_map.get(str(av), "") or str(av)
        texto = (o.get("observacao") or "").strip()
        if not texto:
            continue
        grupos = _separar_obs(texto)
        partes_html = []
        if grupos["fortes"]:
            partes_html.append(
                f'<span class="obs-forte"><b>Pontos fortes (BOM!):</b> '
                f'{_esc(" · ".join(grupos["fortes"]))}</span>')
        if grupos["melhorar"]:
            partes_html.append(
                f'<span class="obs-melhorar"><b>A melhorar:</b> '
                f'{_esc(" · ".join(grupos["melhorar"]))}</span>')
        if grupos["outras"]:
            partes_html.append(
                f'<span class="obs-outras"><b>Outras:</b> '
                f'{_esc(" · ".join(grupos["outras"]))}</span>')
        if not partes_html:
            partes_html.append(_esc(texto))
        linhas.append(
            f'<li><span class="avaliador">{_esc(nome_av)}</span> '
            f'<div class="obs-grupos">{"".join(partes_html)}</div></li>'
        )
    return "".join(linhas) or "<li>Sem observações.</li>"
def _bloco_notas_quesito_sensei(resultados: list[dict], nomes: dict | None) -> str:
    """Ranking de Notas por Quesito + coluna 'Nova Faixa (se aprovado)' (ponto 4)."""
    ordem = _carregar_ordem_faixas()
    thead = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
    linhas = []
    for r in sorted(resultados, key=lambda x: x.get("nota_final", 0.0), reverse=True):
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        tds = "".join(
            f'<td>{(r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0):.1f}</td>'
            for q in NOME_QUESITO
        )
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        nova = _nova_faixa(r.get("faixa", ""), status, ordem)
        linhas.append(
            f'<tr><td class="aluno">{_esc(nome)}</td>{tds}'
            f'<td><b>{r.get("nota_final", 0.0):.1f}</b></td>'
            f'<td><span class="status-mini" style="background:{fg};color:#fff">{_esc(status)}</span></td>'
            f'<td class="novafaixa">{_esc(nova)}</td></tr>'
        )
    return f"""<section class="bloco">
      <h2>Notas por Quesito</h2>
      <p class="sub-bloco">Ranking dos alunos — coluna "Nova Faixa" indica a faixa da próxima graduação caso aprovado.</p>
      <table class="tab">
        <thead><tr><th>Aluno</th>{thead}<th>Nota final</th><th>Status</th><th>Nova Faixa (se aprovado)</th></tr></thead>
        <tbody>{''.join(linhas)}</tbody>
      </table>
    </section>"""
def _card_aluno_sensei(r: dict, nomes: dict | None, avaliadores_map: dict | None) -> str:
    aluno_id = str(r.get("aluno_id", "?"))
    nome = (nomes or {}).get(aluno_id, "") or aluno_id
    faixa = r.get("faixa", "")
    nota = r.get("nota_final", 0.0)
    status = r.get("status", "?")
    fg, bg = _status_cor(status)
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
    """HTML do relatório do Sensei (dojo) — com ranking + nova faixa (ponto 4)
    + Lista de Aprovação (ponto 12, só aprovados, com Nova Faixa)."""
    cards = "".join(_card_aluno_sensei(r, nomes, avaliadores_map) for r in resultados)
    ranking = _bloco_notas_quesito_sensei(resultados, nomes)
    aprovacao = _bloco_lista_aprovacao(resultados, nomes)
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_aprov = sum(1 for r in resultados
                  if r.get("status") in ("APROVADO", "APROVADO_PONTO_ATENCAO"))
    n_aten = sum(1 for r in resultados
                 if r.get("status") == "APROVADO_PONTO_ATENCAO")
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
  .bloco {{ background:#fff; border-radius:12px; padding:20px; margin-top:18px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .bloco h2 {{ margin:0 0 12px; font-size:18px; color:#1a1a1a; }}
  .sub-bloco {{ color:#666; font-size:13px; margin:-6px 0 12px; }}
  /* v2.3: cards dos alunos em 4 colunas (antes 1fr 1fr) */
  .alunos {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
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
  .obs-grupos {{ margin-top:2px; display:flex; flex-direction:column; gap:2px; }}
  .obs-forte {{ color:#1a7f37; }}
  .obs-melhorar {{ color:#b7791f; }}
  .obs-outras {{ color:#666; }}
  .marc-bloco {{ margin:8px 0; }}
  .marc-q-nome {{ display:block; font-weight:700; color:#555; font-size:12px; text-transform:uppercase; margin-bottom:4px; }}
  table.tab {{ width:100%; border-collapse:collapse; font-size:12px; }}
  table.tab th, table.tab td {{ border:1px solid #e0e0e0; padding:4px 8px; text-align:center; }}
  table.tab th {{ background:#f4f5f7; color:#444; font-weight:600; }}
  table.tab td.crit {{ text-align:left; color:#333; }}
  table.tab td.aluno {{ text-align:left; font-weight:600; }}
  .status-mini {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }}
  .novafaixa {{ font-weight:700; color:#1f4e79; }}
  .vazio {{ color:#999; font-size:12px; }}
  @media print {{ body {{ background:#fff; }} .pagina {{ max-width:100%; padding:0; }}
                 .card, .bloco {{ box-shadow:none; break-inside:avoid; }} .capa {{ border-radius:0; }} }}
  /* v2.3: breakpoints responsivos da grade de alunos */
  @media (max-width:1100px) {{ .alunos {{ grid-template-columns:repeat(2,1fr); }} }}
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
      <div class="metric"><span class="metric-t">C/ atenção</span><span class="metric-v" style="color:#b7791f">{n_aten}</span></div>
      <div class="metric"><span class="metric-t">Média</span><span class="metric-v" style="color:#1f4e79">{media:.1f}</span></div>
    </div>
    {ranking}
    {aprovacao}
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
    """Agrega critérios marcados: nº de alunos, % e intensidade média."""
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
        it["texto"] = _texto_recomendacao(recomendacoes, it["quesito"], it["chave"])
    return itens
def _bloco_marcacoes_quesito(resultados: list[dict]) -> str:
    """% de marcações dos critérios por quesito — SEM intensidade (ponto 7)."""
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
            f'<td>{it["count"]} de {n} alunos ({it["pct"]:.0f}%)</td></tr>'
            for it in sub
        )
        blocos.append(
            f'<div class="marc-quesito"><h4>{_esc(qnome)}</h4>'
            f'<table class="tab"><thead><tr>'
            f'<th>Critério</th><th>Marcado em</th>'
            f'</tr></thead><tbody>{linhas}</tbody></table></div>'
        )
    return f"""<section class="bloco">
      <h2>Critérios Marcados por Quesito</h2>
      <p class="sub-bloco">% de alunos cujo avaliador marcou cada critério.</p>
      {''.join(blocos)}
    </section>"""
def _bloco_recomendacoes_master(resultados: list[dict], recomendacoes: dict) -> str:
    """Recomendações com rótulos únicos 'Recomendação:' e 'Planejamento Sugerido:'
    por (quesito, critério) — ponto 8, sem repetição entre quesitos."""
    itens = _agregar_recomendacoes(resultados, recomendacoes)
    if not itens:
        return ('<section class="bloco"><h2>Recomendações Sugeridas</h2>'
                '<p>Nenhum critério de atenção identificado no exame.</p></section>')
    n = len(resultados)
    linhas = []
    for it in itens:
        cor = COR_QUESITO.get(it["quesito"], "#333")
        rec, plano = _texto_recomendacao_detalhe(recomendacoes,
                                                 it["quesito"], it["chave"])
        partes = []
        if rec:
            partes.append(
                f'<div class="rec-motivo"><b>Recomendação:</b> {_esc(rec)}</div>')
        if plano:
            partes.append(
                f'<div class="rec-plano"><b>Planejamento Sugerido:</b> {_esc(plano)}</div>')
        if not partes:
            partes.append(
                f'<div class="rec-motivo"><b>Recomendação:</b> {_esc(it["texto"]) or "—"}</div>')
        linhas.append(
            f'<li class="rec-item">'
            f'<div class="rec-head"><span class="dot" style="background:{cor}"></span>'
            f'<b>{_esc(NOME_QUESITO[it["quesito"]])} — {_esc(it["nome"])}</b>'
            f'<span class="rec-meta">marcado em {it["count"]} de {n} alunos ({it["pct"]:.0f}%)</span></div>'
            f'{"".join(partes)}'
            f'</li>'
        )
    return f"""<section class="bloco">
      <h2>Recomendações Sugeridas</h2>
      <p class="sub-bloco">Critérios de maior incidência no exame, com recomendação e planejamento para os treinos.</p>
      <ul class="recs">{''.join(linhas)}</ul>
    </section>"""
def _bloco_analise_desempenho(resultados: list[dict], nomes: dict | None) -> str:
    """Análise de desempenho geral (ponto 9): média por quesito, foco, atenção, destaque."""
    presentes = [r for r in resultados if r.get("status") != "AUSENTE"]
    if not presentes:
        return ""
    n = len(presentes)
    medias: dict[str, float] = {}
    for q in NOME_QUESITO:
        vals = [(r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0)
                for r in presentes]
        medias[q] = sum(vals) / n
    ranking = sorted(medias.items(), key=lambda x: x[1])
    bars = ""
    for q, media in ranking:
        cor = COR_QUESITO.get(q, "#333")
        pct = min(100.0, media / 25 * 100)
        bars += (
            f'<div class="mini-q"><span class="mini-q-nome">{_esc(NOME_QUESITO[q])}</span>'
            f'<div class="mini-q-bar"><div class="mini-q-fill" style="width:{pct:.0f}%;background:{cor}"></div></div>'
            f'<span class="mini-q-val">{media:.1f}</span></div>'
        )
    foco = NOME_QUESITO[ranking[0][0]] if ranking else "—"
    risco = sorted(
        [r for r in presentes
         if r.get("nota_final", 0.0) <= 75.0
         or r.get("status") == "APROVADO_PONTO_ATENCAO"],
        key=lambda r: r.get("nota_final", 0.0),
    )
    risco_linhas = "".join(
        f'<li>{_esc((nomes or {}).get(str(r.get("aluno_id")), r.get("aluno_id", "?")))}'
        f' — nota {r.get("nota_final", 0.0):.1f} ({_esc(r.get("status", "?"))})</li>'
        for r in risco
    ) or "<li>Nenhum aluno em zona de atenção.</li>"
    topo = max(presentes, key=lambda r: r.get("nota_final", 0.0))
    nome_topo = (nomes or {}).get(str(topo.get("aluno_id")), topo.get("aluno_id", "?"))
    return f"""<section class="bloco">
      <h2>Análise de Desempenho</h2>
      <div class="analise-grid">
        <div>
          <h4>Média da turma por quesito</h4>
          {bars}
        </div>
        <div>
          <h4>Foco do treino</h4>
          <p>Quesito com menor média: <b>{_esc(foco)}</b> ({medias[ranking[0][0]]:.1f} pts).</p>
          <h4>Alunos em zona de atenção (nota ≤ 75,0)</h4>
          <ul>{risco_linhas}</ul>
          <h4>Destaque do exame</h4>
          <p><b>{_esc(nome_topo)}</b> — nota {topo.get("nota_final", 0.0):.1f}.</p>
        </div>
      </div>
    </section>"""
def _bloco_notas_quesito(resultados: list[dict], nomes: dict | None) -> str:
    """Tabela de notas por quesito por aluno (master) — ranking descrescente."""
    thead = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
    linhas = []
    for r in sorted(resultados, key=lambda x: x.get("nota_final", 0.0), reverse=True):
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
    """Observações dos avaliadores por aluno, com nome e separação (pontos 2–3)."""
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    blocos = []
    for r in resultados:
        obs = [o for o in (r.get("observacoes_por_avaliador") or [])
               if (o.get("observacao") or "").strip()]
        if not obs:
            continue
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        linhas = []
        for o in obs:
            av = o.get("avaliador") or "Avaliador"
            nome_av = avaliadores_map.get(str(av), "") or str(av)
            grupos = _separar_obs(o["observacao"])
            partes = []
            if grupos["fortes"]:
                partes.append(f'<span class="obs-forte"><b>Pontos fortes (BOM!):</b> {_esc(" · ".join(grupos["fortes"]))}</span>')
            if grupos["melhorar"]:
                partes.append(f'<span class="obs-melhorar"><b>A melhorar:</b> {_esc(" · ".join(grupos["melhorar"]))}</span>')
            if grupos["outras"]:
                partes.append(f'<span class="obs-outras"><b>Outras:</b> {_esc(" · ".join(grupos["outras"]))}</span>')
            if not partes:
                partes.append(_esc(o["observacao"]))
            linhas.append(
                f'<li><span class="avaliador">{_esc(nome_av)}</span> '
                f'<div class="obs-grupos">{"".join(partes)}</div></li>'
            )
        blocos.append(
            f'<div class="obs-aluno"><h4>{_esc(nome)}</h4><ul class="obs">{"".join(linhas)}</ul></div>'
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
    analise_html = _bloco_analise_desempenho(todos_alunos, nomes)
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
  .rec-motivo, .rec-plano {{ color:#555; font-size:13px; margin-top:4px; padding-left:18px; }}
  .marc-quesito {{ margin:10px 0; }}
  .analise-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  .mini-q {{ display:flex; align-items:center; gap:8px; margin:4px 0; font-size:12px; }}
  .mini-q-nome {{ width:70px; color:#555; }}
  .mini-q-bar {{ flex:1; height:8px; background:#eef0f3; border-radius:4px; overflow:hidden; }}
  .mini-q-fill {{ height:100%; border-radius:4px; }}
  .mini-q-val {{ width:34px; text-align:right; font-weight:600; }}
  .obs-aluno {{ margin:10px 0; }}
  .obs-aluno h4 {{ margin:0 0 4px; }}
  .obs .avaliador {{ font-weight:700; color:#1f4e79; }}
  .obs li {{ padding:5px 0; font-size:13px; }}
  .obs-grupos {{ margin-top:2px; display:flex; flex-direction:column; gap:2px; }}
  .obs-forte {{ color:#1a7f37; }}
  .obs-melhorar {{ color:#b7791f; }}
  .obs-outras {{ color:#666; }}
  table.tab {{ width:100%; border-collapse:collapse; font-size:13px; }}
  table.tab th, table.tab td {{ border:1px solid #e0e0e0; padding:6px 10px; text-align:center; }}
  table.tab th {{ background:#f4f5f7; color:#444; font-weight:600; }}
  table.tab td.aluno {{ text-align:left; font-weight:600; }}
  .status-mini {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:700; }}
  @media print {{ body {{ background:#fff; }} .pagina {{ max-width:100%; padding:0; }}
                 .bloco {{ box-shadow:none; break-inside:avoid; }} }}
  @media (max-width:700px) {{ .alunos, .resumo, .analise-grid {{ grid-template-columns:1fr; }} }}
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
    {analise_html}
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
# ═══════════════════════════════ v2.2+ (individual + aprovação) ═══════════════
_STATUS_LABEL = {
    "APROVADO": "Aprovado",
    "APROVADO_PONTO_ATENCAO": "Aprovado (com atenção)",
    "RECUPERACAO": "Recuperação",
    "REPROVADO": "Reprovado",
    "REVISAO_PENDENTE": "Revisão pendente",
    "AUSENTE": "Ausente",
}
def _status_label(status: str) -> str:
    return _STATUS_LABEL.get(status, status or "?")
def _freq_reais_consolidadas(r: dict) -> dict[str, dict[str, int]]:
    """Frequências por critério SEM distinção de avaliador.
    Usa 'frequencias_reais' quando existir; senão soma
    'frequencias_por_avaliador' (robusto p/ qualquer origem do dict)."""
    freq = r.get("frequencias_reais") or {}
    if freq:
        return {q: {c: int(f) for c, f in b.items() if f}
                for q, b in freq.items()}
    cons: dict[str, dict[str, int]] = {}
    for av in (r.get("frequencias_por_avaliador") or []):
        for q, blocos in (av or {}).items():
            for ch, f in (blocos or {}).items():
                if f:
                    cons.setdefault(q, {})[ch] = cons[q].get(ch, 0) + int(f)
    return cons
def gerar_html_individual(r: dict, nomes: dict | None = None,
                          exame_id: str = "", dojo_id: str = "") -> str:
    """HTML individual por aluno (imprimir/exportar como PDF) — SEM citar
    avaliadores. Mostra: nota final, status, nota por quesito, marcações
    consolidadas por critério e observações resumidas (BOM!/A melhorar/Outras)
    sem autoria."""
    aluno_id = str(r.get("aluno_id", "?"))
    nome = (nomes or {}).get(aluno_id, "") or aluno_id
    faixa = r.get("faixa", "")
    nota = r.get("nota_final", 0.0)
    status = r.get("status", "?")
    fg, _ = _status_cor(status)
    # Notas por quesito
    bars = ""
    for q, qnome in NOME_QUESITO.items():
        nq = (r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0)
        cor = COR_QUESITO.get(q, "#333")
        pct = min(100.0, nq / 25.0 * 100.0)
        bars += (f'<div class="mini-q"><span class="mini-q-nome">{_esc(qnome)}</span>'
                 f'<div class="mini-q-bar"><div class="mini-q-fill" '
                 f'style="width:{pct:.0f}%;background:{cor}"></div></div>'
                 f'<span class="mini-q-val">{nq:.1f}</span></div>')
    # Marcações consolidadas (sem avaliador)
    freq_reais = _freq_reais_consolidadas(r)
    blocos_marc = []
    for q, qnome in NOME_QUESITO.items():
        det = (r.get("quesitos", {}).get(q, {}) or {}).get("detalhes") or {}
        linhas = []
        tem = False
        for chave, f in (freq_reais.get(q) or {}).items():
            if not f:
                continue
            tem = True
            nome_c = (det.get(chave) or {}).get("nome") or chave
            linhas.append(
                f'<tr><td class="crit">{_esc(nome_c)}</td><td>{int(f)}</td></tr>')
        if not tem:
            continue
        blocos_marc.append(
            f'<div class="marc-bloco"><span class="marc-q-nome">{_esc(qnome)}</span>'
            f'<table class="tab"><thead><tr><th>Critério</th><th>Frequência</th></tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div>')
    marc_html = "".join(blocos_marc) or "<p class='vazio'>Sem marcações.</p>"
    # Observações consolidadas (sem autoria)
    textos = []
    for o in (r.get("observacoes_por_avaliador") or []):
        t = (o.get("observacao") or "").strip()
        if t and t not in textos:
            textos.append(t)
    grupos = {"fortes": [], "melhorar": [], "outras": []}
    for t in textos:
        g = _separar_obs(t)
        for k in grupos:
            grupos[k].extend(g[k])
    for k in grupos:  # dedupe por grupo
        vistos, saida = set(), []
        for item in grupos[k]:
            if item not in vistos:
                vistos.add(item)
                saida.append(item)
        grupos[k] = saida
    obs_partes = []
    if grupos["fortes"]:
        obs_partes.append(
            f'<p class="obs-forte"><b>Pontos fortes (BOM!):</b> '
            f'{_esc(" · ".join(grupos["fortes"]))}</p>')
    if grupos["melhorar"]:
        obs_partes.append(
            f'<p class="obs-melhorar"><b>A melhorar:</b> '
            f'{_esc(" · ".join(grupos["melhorar"]))}</p>')
    if grupos["outras"]:
        obs_partes.append(
            f'<p class="obs-outras"><b>Outras:</b> '
            f'{_esc(" · ".join(grupos["outras"]))}</p>')
    obs_html = "".join(obs_partes) or "<p class='vazio'>Sem observações.</p>"
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório Individual — {_esc(nome)}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',Roboto,Arial,sans-serif; margin:0; color:#222; background:#fff; }}
  .pagina {{ max-width:800px; margin:0 auto; padding:32px; }}
  .capa {{ background:linear-gradient(135deg,#1a1a1a,#333); color:#fff; border-radius:14px;
           padding:24px 28px; margin-bottom:20px; }}
  .capa h1 {{ margin:0 0 4px; font-size:22px; }}
  .capa .sub {{ color:#ccc; font-size:13px; }}
  .capa .meta {{ margin-top:12px; display:flex; gap:18px; flex-wrap:wrap; font-size:12px; }}
  .capa .meta b {{ color:#fff; }}
  .bloco {{ background:#fff; border-radius:12px; padding:18px 20px; margin-top:16px;
            border:1px solid #e4e6ea; }}
  .bloco h2 {{ margin:0 0 10px; font-size:16px; color:#1a1a1a; }}
  .nota-final {{ font-size:34px; font-weight:800; }}
  .status {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:12px;
             font-weight:700; color:#fff; margin-left:10px; }}
  .mini-q {{ display:flex; align-items:center; gap:8px; margin:4px 0; font-size:12px; }}
  .mini-q-nome {{ width:70px; color:#555; }}
  .mini-q-bar {{ flex:1; height:8px; background:#eef0f3; border-radius:4px; overflow:hidden; }}
  .mini-q-fill {{ height:100%; border-radius:4px; }}
  .mini-q-val {{ width:34px; text-align:right; font-weight:600; }}
  .marc-bloco {{ margin:8px 0; }}
  .marc-q-nome {{ display:block; font-weight:700; color:#555; font-size:12px;
                  text-transform:uppercase; margin-bottom:4px; }}
  table.tab {{ width:100%; border-collapse:collapse; font-size:12px; }}
  table.tab th, table.tab td {{ border:1px solid #e0e0e0; padding:4px 8px; text-align:center; }}
  table.tab th {{ background:#f4f5f7; color:#444; font-weight:600; }}
  table.tab td.crit {{ text-align:left; color:#333; }}
  .obs-forte {{ color:#1a7f37; }}
  .obs-melhorar {{ color:#b7791f; }}
  .obs-outras {{ color:#666; }}
  .vazio {{ color:#999; font-size:12px; }}
  .rodape {{ margin-top:26px; padding-top:12px; border-top:1px solid #e4e6ea;
             font-size:11px; color:#888; text-align:center; }}
  @media print {{ body {{ background:#fff; }} .pagina {{ max-width:100%; padding:16px; }}
    .bloco {{ break-inside:avoid; border:none; }} .capa {{ border-radius:0; }} }}
</style>
</head>
<body>
  <div class="pagina">
    <header class="capa">
      <h1>{_esc(nome)}</h1>
      <div class="sub">Sistema Karate-Ashi · Relatório Individual do Aluno</div>
      <div class="meta">
        <div><b>Dojo:</b> {_esc(dojo_id) or '—'}</div>
        <div><b>Exame:</b> {_esc(exame_id) or '—'}</div>
        <div><b>Faixa:</b> {_esc(faixa)}</div>
        <div><b>Gerado em:</b> {_esc(data)}</div>
      </div>
    </header>
    <section class="bloco">
      <h2>Nota Final</h2>
      <div><span class="nota-final">{nota:.1f}</span>
           <span class="status" style="background:{fg}">{_esc(_status_label(status))}</span></div>
    </section>
    <section class="bloco">
      <h2>Notas por Quesito</h2>
      {bars}
    </section>
    <section class="bloco">
      <h2>Marcações do Exame</h2>
      {marc_html}
    </section>
    <section class="bloco">
      <h2>Observações</h2>
      {obs_html}
    </section>
    <div class="rodape">Documento gerado automaticamente pelo Sistema Karate-Ashi.</div>
  </div>
</body>
</html>"""
def salvar_individuais_exame(resultados: list[dict],
                             destino_dir: Path,
                             exame_id: str = "",
                             dojo_id: str = "",
                             nomes: dict | None = None) -> list[Path]:
    """Gera um HTML individual por aluno (imprimir/exportar PDF) no MESMO
    diretório do relatório do exame (destino_dir = pasta do exame)."""
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    salvos = []
    for r in resultados:
        aluno_id = str(r.get("aluno_id", "?"))
        arquivo = destino_dir / f"relatorio_individual_{aluno_id}.html"
        arquivo.write_text(
            gerar_html_individual(r, nomes, exame_id, dojo_id),
            encoding="utf-8")
        salvos.append(arquivo)
    return salvos
def _bloco_lista_aprovacao(resultados: list[dict],
                           nomes: dict | None = None) -> str:
    """Lista de divulgação (v2.3) — SOMENTE aprovados, com a Nova Faixa.
    Para o sensei divulgar o resultado ao grupo de alunos/pais: sem notas,
    sem subtítulo, sem ausentes/recuperação/reprovados."""
    ordem = _carregar_ordem_faixas()
    aprovados = [r for r in resultados
                 if r.get("status") in ("APROVADO", "APROVADO_PONTO_ATENCAO")]
    if not aprovados:
        return ('<section class="bloco">'
                '<h2>Resultado do Exame — Lista de Aprovação</h2>'
                '<p class="vazio">Nenhum aluno aprovado neste exame.</p>'
                '</section>')
    aprovados.sort(
        key=lambda r: str((nomes or {}).get(str(r.get("aluno_id", "?")),
                                            r.get("aluno_id", "?"))))
    linhas = []
    for r in aprovados:
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        nova = _nova_faixa(r.get("faixa", ""), status, ordem)
        linhas.append(
            f'<tr><td class="aluno">{_esc(nome)}</td>'
            f'<td>{_esc(r.get("faixa", ""))}</td>'
            f'<td class="novafaixa">{_esc(nova)}</td>'
            f'<td><span class="status-mini" style="background:{fg};color:#fff">'
            f'{_esc(_status_label(status))}</span></td></tr>'
        )
    return f"""<section class="bloco">
      <h2>Resultado do Exame — Lista de Aprovação</h2>
      <table class="tab">
        <thead><tr><th>Aluno</th><th>Faixa</th><th>Nova Faixa</th><th>Status</th></tr></thead>
        <tbody>{''.join(linhas)}</tbody>
      </table>
    </section>"""