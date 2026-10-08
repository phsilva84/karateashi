"""core/relatorio_html.py - Relatorio visual Karate-Ashi v3.8 (HTML autossuficiente).
v2.x Sensei; v3.0 Master analitico; v3.2 lisura com causa; v3.3 nome real do dojo;
v3.4 atencao simples + treino direcionado; v3.5 perfil avaliadores; v3.6 sem
comparativo por dojo + obs em lista; v3.7 ranking com marcacoes expansiveis;
v3.8: sem "+N outros criterios", rotulo "Sugestao:", obs agregadas com autoria.
"""
from __future__ import annotations
import html, json, re, unicodedata
from datetime import datetime
from pathlib import Path
from core.observacoes import OBS_MELHORAR, OBS_POSITIVAS
from core.relatorios import NOME_QUESITO, gerar_relatorio_master
COR_STATUS = {"APROVADO": ("#1a7f37", "#e6f4ea"), "APROVADO_PONTO_ATENCAO": ("#b7791f", "#fdf3e7"), "RECUPERACAO": ("#b7791f", "#fdf3e7"), "REPROVADO": ("#c62828", "#fdecea"), "REVISAO_PENDENTE": ("#6a737d", "#eef1f4"), "AUSENTE": ("#6a737d", "#eef1f4")}
COR_QUESITO = {"kihon": "#1f4e79", "kata": "#7b2d8b", "bunkai": "#b45309", "kumite": "#b91c1c"}
_RAIZ = Path(__file__).resolve().parents[1]
def _esc(t): return html.escape(str(t), quote=True)
def _status_cor(s): return COR_STATUS.get(s, ("#6a737d", "#eef1f4"))
def _slug_nome(nome):
    t = unicodedata.normalize("NFKD", str(nome or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s-]", "", t).strip().lower()
    t = re.sub(r"[\s_]+", "_", t)
    return t.strip("_") or "aluno"
def _carregar_avaliadores_map():
    try:
        doc = json.loads((_RAIZ / "config" / "avaliadores.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {str(a.get("id")): str(a.get("nome") or a.get("id") or "") for a in doc.get("avaliadores", [])}
def _carregar_nomes_dojos():
    try:
        doc = json.loads((_RAIZ / "config" / "dojos.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    regs = doc
    if isinstance(doc, dict):
        for ch in ("dojos", "registros", "itens"):
            if isinstance(doc.get(ch), list):
                regs = doc[ch]; break
        else:
            if doc and all(isinstance(v, dict) for v in doc.values()):
                regs = list(doc.values())
    mapa = {}
    for reg in (regs if isinstance(regs, list) else []):
        did = reg.get("id") or reg.get("dojo_id") or reg.get("codigo") or ""
        nome = reg.get("nome") or reg.get("nome_dojo") or reg.get("dojo") or reg.get("name") or reg.get("nome_completo") or reg.get("razao_social") or ""
        if did and nome:
            mapa[str(did)] = str(nome)
    return mapa
def _nome_dojo(dojo_id, dojos_map=None):
    dojos_map = dojos_map if dojos_map is not None else _carregar_nomes_dojos()
    return (dojos_map or {}).get(str(dojo_id), "") or str(dojo_id)
def _carregar_ordem_faixas():
    padrao = ["branca", "amarela", "laranja", "verde", "azul", "roxa", "marrom", "preta"]
    try:
        doc = json.loads((_RAIZ / "config" / "faixas.json").read_text(encoding="utf-8"))
    except Exception:
        return padrao
    ordem = [str(f).strip().lower() for f in doc.get("suportadas", [])] + [str(f).strip().lower() for f in doc.get("placeholder", [])]
    return ordem or padrao
def _nova_faixa(faixa_atual, status, ordem):
    if status in ("APROVADO", "APROVADO_PONTO_ATENCAO"):
        atual = (faixa_atual or "").strip().lower()
        try:
            i = ordem.index(atual)
        except ValueError:
            return "—"
        return (ordem[i + 1].capitalize() if i + 1 < len(ordem) else "Faixa máxima")
    return ("Mantém faixa" if status == "RECUPERACAO" else "—")
_LIMITES_PADRAO = {"aprovado": 75.0, "atencao": 70.0, "recuperacao": 70.0}
def _limites_status():
    limites = dict(_LIMITES_PADRAO)
    try:
        doc = json.loads((_RAIZ / "config" / "regras_gerais.json").read_text(encoding="utf-8"))
    except Exception:
        return limites
    chaves = {"aprovado": ("aprovacao", "nota_aprovacao", "nota_min_aprovacao", "aprovado_min", "min_aprovacao"), "atencao": ("atencao", "ponto_atencao", "nota_atencao", "aprovado_ponto_atencao", "nota_ponto_atencao", "min_atencao"), "recuperacao": ("recuperacao", "nota_recuperacao", "recuperacao_min", "min_recuperacao")}
    def _buscar(nodo, alvo):
        if isinstance(nodo, dict):
            for k, v in nodo.items():
                kl = str(k).strip().lower().replace(" ", "_")
                if kl in chaves[alvo] and isinstance(v, (int, float)):
                    return float(v)
                r = _buscar(v, alvo)
                if r is not None:
                    return r
        elif isinstance(nodo, list):
            for item in nodo:
                r = _buscar(item, alvo)
                if r is not None:
                    return r
        return None
    for alvo in limites:
        v = _buscar(doc, alvo)
        if v is not None:
            limites[alvo] = v
    return limites
_OBS_POSITIVAS_TXT = tuple(t.lower() for t in OBS_POSITIVAS.values())
_OBS_MELHORAR_TXT = tuple(t.lower() for t in OBS_MELHORAR.values())
_PREFIXOS_FORTES = ("boa", "bom", "otim", "ótimo", "excelente", "bem", "grande")
_PREFIXOS_MELHORAR = ("dificuldade", "erros", "falta", "melhorar", "atenção", "nervosismo", "perda", "cabeça", "mais foco", "mais carga")
def _classificar_obs(parte):
    t = parte.lower().strip()
    if any(p in t for p in _OBS_POSITIVAS_TXT): return "fortes"
    if any(m in t for m in _OBS_MELHORAR_TXT): return "melhorar"
    if t.startswith(_PREFIXOS_FORTES): return "fortes"
    if t.startswith(_PREFIXOS_MELHORAR): return "melhorar"
    return "outras"
def _separar_obs(texto):
    grupos = {"fortes": [], "melhorar": [], "outras": []}
    for parte in texto.replace(".", ";").replace("\n", ";").split(";"):
        parte = parte.strip()
        if parte:
            grupos[_classificar_obs(parte)].append(parte)
    return grupos
def _texto_recomendacao(recomendacoes, quesito, chave):
    por_q = (recomendacoes or {}).get("por_quesito", {})
    v = por_q.get(quesito, {}).get(chave, None)
    if v is None:
        texto = str((recomendacoes or {}).get(chave, "") or "")
        if "Recomendação:" in texto:
            texto = texto.split("Recomendação:", 1)[0].strip()
        return texto
    if isinstance(v, str): return v
    if isinstance(v, dict): return (v.get("recomendacao") or v.get("motivo") or v.get("texto") or "")
    return ""
def _texto_recomendacao_detalhe(recomendacoes, quesito, chave):
    por_q = (recomendacoes or {}).get("por_quesito", {})
    v = por_q.get(quesito, {}).get(chave, None)
    if isinstance(v, dict):
        rec = v.get("recomendacao") or v.get("motivo") or v.get("texto") or ""
        plano = v.get("planejamento") or v.get("sugerido") or ""
        return str(rec), str(plano)
    if isinstance(v, str): return str(v), ""
    texto = str((recomendacoes or {}).get(chave, "") or "")
    if "Recomendação:" in texto:
        antes, depois = texto.split("Recomendação:", 1)
        return antes.strip(), depois.strip(" ()")
    return texto, ""
# ---------- SENSEI ----------
def _tabela_marcacoes(r, avaliadores_map):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    por_av = r.get("frequencias_por_avaliador") or []
    av_ids = r.get("avaliadores_ids") or [f"A{i + 1}" for i in range(len(por_av))]
    labels = [avaliadores_map.get(str(aid), "") or str(aid) or f"A{i + 1}" for i, aid in enumerate(av_ids)] or ["Avaliador 1"]
    quesitos = r.get("quesitos") or {}
    blocos = []
    for q, qnome in NOME_QUESITO.items():
        det = (quesitos.get(q) or {}).get("detalhes") or {}
        linhas, tem = [], False
        for chave, d in det.items():
            vals = [int((avp.get(q) or {}).get(chave, 0) or 0) for avp in por_av]
            if not any(vals): continue
            tem = True
            tds = "".join(f"<td>{v if v else ''}</td>" for v in vals)
            linhas.append(f'<tr><td class="crit">{_esc(d.get("nome") or chave)}</td>{tds}</tr>')
        if not tem: continue
        th = "".join(f"<th>{_esc(lb)}</th>" for lb in labels)
        blocos.append(f'<div class="marc-bloco"><span class="marc-q-nome">{_esc(qnome)}</span><table class="tab"><thead><tr><th>Critério</th>{th}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>')
    return "".join(blocos) or "<p class='vazio'>Sem critérios marcados.</p>"
def _obs_com_autoria(r, avaliadores_map):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    linhas = []
    for o in (r.get("observacoes_por_avaliador") or []):
        av = o.get("avaliador") or "Avaliador"
        nome_av = avaliadores_map.get(str(av), "") or str(av)
        texto = (o.get("observacao") or "").strip()
        if not texto: continue
        grupos = _separar_obs(texto)
        partes_html = []
        if grupos["fortes"]: partes_html.append(f'<span class="obs-forte"><b>Pontos fortes (BOM!):</b> {_esc(" · ".join(grupos["fortes"]))}</span>')
        if grupos["melhorar"]: partes_html.append(f'<span class="obs-melhorar"><b>A melhorar:</b> {_esc(" · ".join(grupos["melhorar"]))}</span>')
        if grupos["outras"]: partes_html.append(f'<span class="obs-outras"><b>Outras:</b> {_esc(" · ".join(grupos["outras"]))}</span>')
        if not partes_html: partes_html.append(_esc(texto))
        linhas.append(f'<li><span class="avaliador">{_esc(nome_av)}</span> <div class="obs-grupos">{"".join(partes_html)}</div></li>')
    return "".join(linhas) or "<li>Sem observações.</li>"
def _bloco_notas_quesito_sensei(resultados, nomes):
    ordem = _carregar_ordem_faixas()
    thead = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
    linhas = []
    for r in sorted(resultados, key=lambda x: x.get("nota_final", 0.0), reverse=True):
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        tds = "".join(f'<td>{(r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0):.1f}</td>' for q in NOME_QUESITO)
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        nova = _nova_faixa(r.get("faixa", ""), status, ordem)
        linhas.append(f'<tr><td class="aluno">{_esc(nome)}</td>{tds}<td><b>{r.get("nota_final", 0.0):.1f}</b></td><td><span class="status-mini" style="background:{fg};color:#fff">{_esc(status)}</span></td><td class="novafaixa">{_esc(nova)}</td></tr>')
    return (f'<section class="bloco"><h2>Notas por Quesito</h2><p class="sub-bloco">Ranking dos alunos — coluna "Nova Faixa" indica a faixa da próxima graduação caso aprovado.</p>'
            f'<table class="tab"><thead><tr><th>Aluno</th>{thead}<th>Nota final</th><th>Status</th><th>Nova Faixa (se aprovado)</th></tr></thead><tbody>{"".join(linhas)}</tbody></table></section>')
def _card_aluno_sensei(r, nomes, avaliadores_map):
    aluno_id = str(r.get("aluno_id", "?"))
    nome = (nomes or {}).get(aluno_id, "") or aluno_id
    faixa, nota, status = r.get("faixa", ""), r.get("nota_final", 0.0), r.get("status", "?")
    fg, _ = _status_cor(status)
    notas_q = ""
    for q, qnome in NOME_QUESITO.items():
        nq = (r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0)
        corq = COR_QUESITO.get(q, "#333")
        notas_q += f'<div class="mini-q"><span class="mini-q-nome">{_esc(qnome)}</span><div class="mini-q-bar"><div class="mini-q-fill" style="width:{min(100, nq / 25 * 100):.0f}%;background:{corq}"></div></div><span class="mini-q-val">{nq:.1f}</span></div>'
    marcacoes = _tabela_marcacoes(r, avaliadores_map)
    obs = _obs_com_autoria(r, avaliadores_map)
    return (f'<article class="card aluno" style="border-left:6px solid {fg}">'
            f'<header class="aluno-head"><div><h3>{_esc(nome)}</h3><span class="faixa">Faixa {_esc(faixa)}</span></div><div class="aluno-num"><span class="nota">{nota:.1f}</span><span class="status" style="background:{fg};color:#fff">{_esc(status)}</span></div></header>'
            f'<div class="mini-quesitos">{notas_q}</div>'
            f'<div class="secao"><h4>Marcações por quesito e avaliador</h4>{marcacoes}</div>'
            f'<div class="secao"><h4>Observações dos avaliadores</h4><ul class="obs">{obs}</ul></div></article>')
_CSS_SENSEI = """
*{box-sizing:border-box}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;margin:0;color:#222;background:#eef0f3}
.pagina{max-width:960px;margin:0 auto;padding:24px}
.capa{background:linear-gradient(135deg,#1a1a1a,#333);color:#fff;border-radius:14px;padding:28px 32px;margin-bottom:22px}
.capa h1{margin:0 0 6px;font-size:26px}
.capa .sub{color:#ccc;font-size:14px}
.capa .meta{margin-top:14px;display:flex;gap:22px;flex-wrap:wrap;font-size:13px}
.capa .meta b{color:#fff}
.resumo{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.metric{background:#fff;border-radius:12px;padding:16px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.metric-t{display:block;font-size:12px;color:#666;text-transform:uppercase;letter-spacing:.5px}
.metric-v{display:block;font-size:24px;font-weight:700;margin-top:4px}
.bloco{background:#fff;border-radius:12px;padding:20px;margin-top:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.bloco h2{margin:0 0 12px;font-size:18px;color:#1a1a1a}
.sub-bloco{color:#666;font-size:13px;margin:-6px 0 12px}
.alunos{display:grid;grid-template-columns:1fr;gap:16px}
.card{background:#fff;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.aluno-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.aluno-head h3{margin:0;font-size:18px}
.faixa{color:#666;font-size:13px}
.aluno-num{text-align:right}
.nota{font-size:26px;font-weight:800}
.status{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700}
.mini-quesitos{margin:10px 0 14px}
.mini-q{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12px}
.mini-q-nome{width:64px;color:#555}
.mini-q-bar{flex:1;height:8px;background:#eef0f3;border-radius:4px;overflow:hidden}
.mini-q-fill{height:100%;border-radius:4px}
.mini-q-val{width:34px;text-align:right;font-weight:600}
.secao{margin-top:12px}
.secao h4{margin:0 0 6px;font-size:13px;text-transform:uppercase;color:#555;letter-spacing:.5px}
ul{margin:0;padding-left:0;list-style:none}
.obs li{padding:5px 0;border-bottom:1px solid #f0f0f0;font-size:13px}
.obs li:last-child{border-bottom:none}
.obs .avaliador{font-weight:700;color:#1f4e79}
.obs-grupos{margin-top:2px;display:flex;flex-direction:column;gap:2px}
.obs-forte{color:#1a7f37}.obs-melhorar{color:#b7791f}.obs-outras{color:#666}
.marc-bloco{margin:8px 0}
.marc-q-nome{display:block;font-weight:700;color:#555;font-size:12px;text-transform:uppercase;margin-bottom:4px}
table.tab{width:100%;border-collapse:collapse;font-size:12px}
table.tab th,table.tab td{border:1px solid #e0e0e0;padding:4px 8px;text-align:center}
table.tab th{background:#f4f5f7;color:#444;font-weight:600}
table.tab td.crit{text-align:left;color:#333}
table.tab td.aluno{text-align:left;font-weight:600}
.status-mini{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}
.novafaixa{font-weight:700;color:#1f4e79}
.vazio{color:#999;font-size:12px}
@media (min-width:900px){.card{display:grid;grid-template-columns:1.25fr 1fr;column-gap:20px}.card .aluno-head,.card .mini-quesitos{grid-column:1 / -1}}
@media print{body{background:#fff}.pagina{max-width:100%;padding:0}.card,.bloco{box-shadow:none;break-inside:avoid}.capa{border-radius:0}}
@media (max-width:899px){.card{display:block}}
@media (max-width:700px){.resumo{grid-template-columns:1fr}}
"""
def gerar_html_exame(resultados, regras, recomendacoes, dojo_id="DOJO", exame_id="", titulo="Relatório do Sensei", nomes=None, sensei_responsavel="", avaliadores_map=None, dojo_nome=None):
    cards = "".join(_card_aluno_sensei(r, nomes, avaliadores_map) for r in resultados)
    ranking = _bloco_notas_quesito_sensei(resultados, nomes)
    aprovacao = _bloco_lista_aprovacao(resultados, nomes)
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    n_aprov = sum(1 for r in resultados if r.get("status") in ("APROVADO", "APROVADO_PONTO_ATENCAO"))
    n_aten = sum(1 for r in resultados if r.get("status") == "APROVADO_PONTO_ATENCAO")
    media = (sum(r.get("nota_final", 0.0) for r in resultados) / len(resultados) if resultados else 0.0)
    dojo_exib = dojo_nome or dojo_id
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
{_CSS_SENSEI}
</style>
</head>
<body>
<div class="pagina">
<header class="capa">
<h1>{_esc(titulo)}</h1>
<div class="sub">Sistema Karate-Ashi · Relatório do Sensei</div>
<div class="meta">
<div><b>Dojo:</b> {_esc(dojo_exib)}</div>
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
def salvar_html_exame(resultados, regras, recomendacoes, destino, dojo_id="DOJO", exame_id="", titulo="Relatório do Sensei", nomes=None, sensei_responsavel="", avaliadores_map=None, dojo_nome=None):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(gerar_html_exame(resultados, regras, recomendacoes, dojo_id, exame_id, titulo, nomes, sensei_responsavel, avaliadores_map, dojo_nome), encoding="utf-8")
    return destino
# ---------- MASTER ----------
def _agregar_criterios(resultados):
    n = len(resultados)
    nome_map = {}
    for r in resultados:
        for q, qd in (r.get("quesitos") or {}).items():
            for ch, d in (qd.get("detalhes") or {}).items():
                nome_map.setdefault((q, ch), d.get("nome") or ch)
    agg = {}
    for r in resultados:
        for q, blocos in (r.get("frequencias_reais") or {}).items():
            for ch, freq in blocos.items():
                if not freq: continue
                e = agg.setdefault((q, ch), {"count": 0, "soma": 0})
                e["count"] += 1
                e["soma"] += int(freq)
    itens = []
    for (q, ch), e in agg.items():
        itens.append({"quesito": q, "chave": ch, "nome": nome_map.get((q, ch), ch), "count": e["count"], "pct": e["count"] / n * 100 if n else 0.0, "intens": e["soma"] / e["count"] if e["count"] else 0.0})
    itens.sort(key=lambda x: (-x["count"], -x["intens"]))
    return itens
def _agregar_recomendacoes(resultados, recomendacoes):
    itens = _agregar_criterios(resultados)
    for it in itens:
        it["texto"] = _texto_recomendacao(recomendacoes, it["quesito"], it["chave"])
    return itens
def _status_counts(alunos):
    c = {"APROVADO": 0, "APROVADO_PONTO_ATENCAO": 0, "RECUPERACAO": 0, "REPROVADO": 0, "REVISAO_PENDENTE": 0, "AUSENTE": 0}
    for r in alunos:
        if r.get("status") in c:
            c[r["status"]] += 1
    return c
def _bloco_histograma(resultados_dojos):
    bandas = [(0, 49.99, "0 – 49,9"), (50, 59.99, "50 – 59,9"), (60, 69.99, "60 – 69,9"), (70, 74.99, "70 – 74,9"), (75, 100.01, "75 – 100")]
    todos = [a for d in resultados_dojos for a in d.get("alunos", [])]
    pres = [a for a in todos if a.get("status") != "AUSENTE"]
    if not pres: return ""
    n = len(pres)
    bars = ""
    for lo, hi, rotulo in bandas:
        qtd = sum(1 for a in pres if lo <= a.get("nota_final", 0.0) < hi)
        pct = qtd / n * 100
        cor = "#1a7f37" if lo >= 70 else ("#b7791f" if lo >= 60 else "#c62828")
        bars += f'<div class="hist-linha"><span class="hist-rot">{rotulo}</span><div class="hist-barra"><div style="width:{pct:.0f}%;background:{cor}"></div></div><span class="hist-val">{qtd} ({pct:.0f}%)</span></div>'
    return (f'<section class="bloco" id="hist"><h2>Distribuição das Notas Finais</h2>'
            f'<p class="sub-bloco">{n} alunos presentes · corte: ≥75 pleno · 70–74,9 atenção · &lt;70 recuperação.</p>'
            f'<div class="hist">{bars}</div></section>')
def _bloco_ranking_contexto(resultados_dojos, nomes, dojos_map=None, avaliadores_map=None):
    ordem = _carregar_ordem_faixas()
    n_cols = 6 + len(NOME_QUESITO)
    blocos = []
    for d in resultados_dojos:
        alunos = sorted(d.get("alunos", []), key=lambda r: r.get("nota_final", 0.0), reverse=True)
        linhas = []
        for r in alunos:
            aid = str(r.get("aluno_id", "?"))
            nome = (nomes or {}).get(aid, "") or aid
            status = r.get("status", "?")
            fg, _ = _status_cor(status)
            nova = _nova_faixa(r.get("faixa", ""), status, ordem)
            tds_q = "".join(f'<td>{(r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0):.1f}</td>' for q in NOME_QUESITO)
            macrc_html = _tabela_marcacoes(r, avaliadores_map)
            det = (f'<tr class="rank-detalhes" style="display:none"><td colspan="{n_cols}" class="rank-detalhe-cel">'
                   f'<div class="marc-detalhe"><h5>Marcações por avaliador — {_esc(nome)}</h5>{macrc_html}</div></td></tr>')
            nome_cell = (f'<td class="aluno"><button type="button" class="rank-reveal" onclick="toggleRankMarks(this)" '
                         f'title="Clique para ver as marcações dos avaliadores">{_esc(nome)}</button></td>')
            linhas.append(f'<tr class="rank-row">{nome_cell}<td>{_esc(r.get("faixa", ""))}</td>{tds_q}'
                          f'<td><b>{r.get("nota_final", 0.0):.1f}</b></td>'
                          f'<td><span class="status-mini" style="background:{fg};color:#fff">{_esc(_status_label(status))}</span></td>'
                          f'<td class="novafaixa">{_esc(nova)}</td></tr>{det}')
        thead = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
        dojo_nome = _nome_dojo(d.get("dojo_id", "?"), dojos_map)
        blocos.append(f'<div class="rank-dojo"><h4>{_esc(dojo_nome)}</h4><div class="tbl-wrap"><table class="tab">'
                      f'<thead><tr><th>Aluno</th><th>Faixa</th>{thead}<th>Nota</th><th>Status</th><th>Nova Faixa</th></tr></thead>'
                      f'<tbody>{"".join(linhas)}</tbody></table></div></div>')
    return (f'<section class="bloco" id="ranking"><h2>Ranking de Alunos</h2>'
            f'<p class="sub-bloco">Clique no <b>nome do aluno</b> para ver, na própria linha, as marcações de todos os avaliadores (quesito/critério).</p>'
            f'{"".join(blocos)}</section>')
def _bloco_criticos_recomendacoes(resultados, recomendacoes):
    itens = _agregar_recomendacoes(resultados, recomendacoes)
    if not itens:
        return ('<section class="bloco" id="criticos"><h2>Principais Pontos de Atenção do Exame</h2>'
                '<p>Nenhum critério precisou de desconto neste exame.</p></section>')
    presentes = [r for r in resultados if r.get("status") != "AUSENTE"]
    n_pres = len(presentes) or 1
    itens.sort(key=lambda x: (-x["count"], -x["intens"]))
    linhas = []
    for pos, it in enumerate(itens[:10], start=1):
        cor = COR_QUESITO.get(it["quesito"], "#333")
        rec, plano = _texto_recomendacao_detalhe(recomendacoes, it["quesito"], it["chave"])
        rec_txt = rec or it.get("texto") or ""
        cel = (f'<div>{_esc(rec_txt)}</div>' if rec_txt else '')
        if plano: cel += f'<div class="rec-motivo"><b>Sugestão:</b> {_esc(plano)}</div>'
        if not cel: cel = '<div class="vazio">Cadastrar recomendação para este ponto.</div>'
        pct = it["count"] / n_pres * 100
        linhas.append(f'<tr><td><b>{pos}º</b></td>'
                      f'<td style="text-align:left"><span class="dot" style="background:{cor}"></span>{_esc(NOME_QUESITO[it["quesito"]])}</td>'
                      f'<td style="text-align:left;font-weight:600">{_esc(it["nome"])}</td>'
                      f'<td>{it["count"]} de {n_pres} presentes ({pct:.0f}%)</td><td class="recom-texto">{cel}</td></tr>')
    return (f'<section class="bloco" id="criticos"><h2>Principais Pontos de Atenção do Exame</h2>'
            f'<p class="sub-bloco">Os pontos técnicos que mais precisaram de desconto neste exame, do mais frequente para o menos. Use esta lista para focar os próximos treinos.</p>'
            f'<div class="tbl-wrap"><table class="tab"><thead><tr><th>#</th><th>Quesito</th><th>Ponto técnico</th><th>Alunos que erraram</th><th>O que trabalhar no treino</th></tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div></section>')
def _divergencias_por_criterio(r, avaliadores_map):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    por_av = r.get("frequencias_por_avaliador") or []
    av_ids = r.get("avaliadores_ids") or []
    labels = [avaliadores_map.get(str(a), "") or str(a) or f"A{i+1}" for i, a in enumerate(av_ids)]
    if not por_av or len(por_av) < 2: return []
    quesitos = r.get("quesitos") or {}
    divergencias = []
    for q, qnome in NOME_QUESITO.items():
        det = (quesitos.get(q) or {}).get("detalhes") or {}
        for chave, d in det.items():
            marcou = []
            for i, avp in enumerate(por_av):
                if int((avp.get(q) or {}).get(chave, 0) or 0) > 0:
                    marcou.append(labels[i] if i < len(labels) else f"A{i+1}")
            if 0 < len(marcou) < len(por_av):
                divergencias.append((qnome, d.get("nome") or chave, marcou))
    return divergencias
def _bloco_consistencia(resultados_dojos, nomes, avaliadores_map=None, dojos_map=None):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    def _lab(av): return avaliadores_map.get(str(av), "") or str(av)
    linhas = []
    for d in resultados_dojos:
        dojo_nome = _nome_dojo(d.get("dojo_id", "?"), dojos_map)
        for r in d.get("alunos", []):
            aid = str(r.get("aluno_id", "?"))
            nome = (nomes or {}).get(aid, "") or aid
            notas = r.get("notas_por_avaliador")
            if notas:
                entradas = [{"av": str(no.get("avaliador") or f"A{i+1}"), "val": float(no.get("nota", 0.0))} for i, no in enumerate(notas)]
                usa_notas = True
            else:
                por_av = r.get("frequencias_por_avaliador") or []
                av_ids = r.get("avaliadores_ids") or [f"A{i+1}" for i in range(len(por_av))]
                entradas = [{"av": str(av_ids[i] if i < len(av_ids) else f"A{i+1}"), "val": float(sum(int(v) for b in (avp or {}).values() for v in b.values()))} for i, avp in enumerate(por_av)]
                usa_notas = False
            if len(entradas) < 2 or not any(e["val"] > 0 for e in entradas): continue
            vals = sorted(e["val"] for e in entradas)
            delta = vals[-1] - vals[0]
            if delta <= 3.0: continue
            outlier = max(entradas, key=lambda e: abs(e["val"] - vals[len(vals) // 2]))
            out_nome = _lab(outlier["av"])
            if usa_notas:
                notas_cell = " · ".join(f"{_esc(_lab(e['av']))}: {e['val']:.1f}" for e in entradas)
                destoante = f"<b>{_esc(out_nome)}</b> ({outlier['val']:.1f})"
            else:
                notas_cell = " · ".join(f"{_esc(_lab(e['av']))}: {int(e['val'])}" for e in entradas)
                destoante = f"<b>{_esc(out_nome)}</b> ({int(outlier['val'])})"
            divs = _divergencias_por_criterio(r, avaliadores_map)
            if divs:
                itens_div = []
                for qnome, cnome, marcou in divs[:4]:
                    nomes_txt = ", ".join((f"<b style='color:#b91c1c'>{_esc(nm)}</b>" if nm == out_nome else _esc(nm)) for nm in marcou)
                    itens_div.append(f'<div class="divg-item"><span class="divg-label">{_esc(qnome)} · {_esc(cnome)}</span> — marcado por: {nomes_txt}</div>')
                causa_html = '<div class="divg-lista">' + "".join(itens_div) + '</div>'
            else:
                causa_html = '<div class="divg-lista"><div class="divg-item divg-mais">Sem critério exclusivo — diferença pela intensidade das marcações nas folhas.</div></div>'
            linhas.append({"delta": delta, "html": (
                f'<tr><td class="aluno">{_esc(nome)}</td><td>{_esc(dojo_nome)}</td>'
                f'<td style="text-align:left;white-space:normal;font-size:11px">{notas_cell}</td>'
                f'<td><b>{delta:.1f}</b></td>'
                f'<td style="text-align:left;white-space:normal;max-width:420px;font-size:11px">{destoante}{causa_html}</td></tr>')})
    if not linhas: return ""
    linhas.sort(key=lambda x: x["delta"], reverse=True)
    return (f'<section class="bloco" id="consist"><h2>Maiores Divergências entre Avaliadores</h2>'
            f'<p class="sub-bloco">Sinalização informativa: quando um avaliador dá nota bem diferente dos outros no mesmo aluno, aparece aqui com o critério em que houve divergência. Nenhum resultado do exame é alterado — uso para acompanhamento da banca e feedback aos avaliadores.</p>'
            f'<div class="tbl-wrap"><table class="tab"><thead><tr><th>Aluno</th><th>Dojo</th><th>Nota de cada avaliador</th><th>Diferença</th><th>Avaliador que destoou (onde divergiu)</th></tr></thead>'
            f'<tbody>{"".join(x["html"] for x in linhas)}</tbody></table></div></section>')
def _bloco_perfil_avaliadores(resultados_dojos, avaliadores_map=None):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    def _lab(av): return avaliadores_map.get(str(av), "") or str(av)
    agg = {}
    for d in resultados_dojos:
        for r in d.get("alunos", []):
            por_av = r.get("frequencias_por_avaliador") or []
            av_ids = r.get("avaliadores_ids") or [f"A{i+1}" for i in range(len(por_av))]
            for i, avp in enumerate(por_av):
                av = str(av_ids[i] if i < len(av_ids) else f"A{i+1}")
                if av not in agg:
                    agg[av] = {"por_quesito": {q: 0 for q in NOME_QUESITO}, "total": 0, "alunos": 0}
                agg[av]["alunos"] += 1
                for q, blocos in (avp or {}).items():
                    if q not in NOME_QUESITO: continue
                    soma = sum(int(v) for v in blocos.values())
                    agg[av]["por_quesito"][q] += soma
                    agg[av]["total"] += soma
    if not agg: return ""
    itens = sorted(agg.items(), key=lambda x: -x[1]["total"])
    thead_q = "".join(f"<th>{_esc(qn)}</th>" for qn in NOME_QUESITO.values())
    linhas = []
    for pos, (av, ag) in enumerate(itens, start=1):
        tds_q = "".join(f"<td>{ag['por_quesito'][q]}</td>" for q in NOME_QUESITO)
        media = ag["total"] / ag["alunos"] if ag["alunos"] else 0.0
        linhas.append(f'<tr><td><b>{pos}º</b></td><td class="aluno">{_esc(_lab(av) or av)}</td>'
                      f'<td>{ag["alunos"]}</td>{tds_q}<td><b>{ag["total"]}</b></td><td>{media:.1f}</td></tr>')
    mais = _lab(itens[0][0]) if itens else "—"
    menos = _lab(itens[-1][0]) if len(itens) > 1 else "—"
    sub = (f"Volume de marcações por avaliador no exame (quesito/critério). Mais marcações = senso crítico mais apurado; menos marcações = avaliação mais flexível. "
           f"Maior volume: <b>{_esc(mais)}</b> · menor volume: <b>{_esc(menos)}</b> — use para equilibrar a banca.")
    return (f'<section class="bloco" id="perfil"><h2>Perfil dos Avaliadores (senso crítico)</h2><p class="sub-bloco">{sub}</p>'
            f'<div class="tbl-wrap"><table class="tab"><thead><tr><th>#</th><th>Avaliador</th><th>Alunos avaliados</th>{thead_q}<th>Total de marcações</th><th>Média por aluno</th></tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></div></section>')
def _bloco_treino_direcionado(resultados, recomendacoes, nomes=None):
    alvos = [r for r in resultados if r.get("status") in ("APROVADO_PONTO_ATENCAO", "RECUPERACAO")]
    if not alvos: return ""
    cards = []
    for r in alvos:
        aid = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aid, "") or aid
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        nota = r.get("nota_final", 0.0)
        freq = _freq_reais_consolidadas(r)
        agg = []
        for q, blocos in freq.items():
            for ch, total in blocos.items():
                agg.append((q, ch, int(total)))
        agg.sort(key=lambda x: -x[2])
        lis = ""
        for q, ch, total in agg[:5]:
            cor = COR_QUESITO.get(q, "#333")
            det = ((r.get("quesitos") or {}).get(q) or {}).get("detalhes") or {}
            d = det.get(ch) or {}
            nome_c = d.get("nome") or ch
            rec, plano = _texto_recomendacao_detalhe(recomendacoes, q, ch)
            partes = ""
            if rec: partes += f'<b>Recomendação:</b> {_esc(rec)}'
            if plano: partes += f'<b>Sugestão:</b> {_esc(plano)}'
            if not partes: partes = '<span class="vazio">Sem recomendação cadastrada para este critério.</span>'
            lis += (f'<li style="text-align:left"><span class="dot" style="background:{cor}"></span>'
                    f'<b>{_esc(NOME_QUESITO.get(q, q))} · {_esc(nome_c)}</b> '
                    f'<span class="rec-meta">({total} marcações)</span>'
                    f'<div class="rec-motivo">{partes}</div></li>')
        cards.append(f'<div class="treino-card"><div class="treino-head"><h4>{_esc(nome)}</h4>'
                     f'<span class="status-mini" style="background:{fg};color:#fff">{_esc(_status_label(status))}</span>'
                     f'<span class="treino-nota">nota {nota:.1f}</span></div><ul class="recs">{lis}</ul></div>')
    return (f'<section class="bloco" id="treino"><h2>Treino Direcionado</h2>'
            f'<p class="sub-bloco">Alunos com ponto de atenção ou recuperação — sugestão de treino por critério mais marcado.</p>'
            f'<div class="treino-grid">{"".join(cards)}</div></section>')
def _bloco_obs_agregadas(resultados_dojos, dojos_map=None, avaliadores_map=None):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    def _lab(av): return avaliadores_map.get(str(av), "") or str(av)
    blocos = []
    for d in resultados_dojos:
        dojo_nome = _nome_dojo(d.get("dojo_id", "?"), dojos_map)
        cont = {"fortes": 0, "melhorar": 0, "outras": 0}
        frases, por_av_total = {}, {}
        for r in d.get("alunos", []):
            for o in (r.get("observacoes_por_avaliador") or []):
                av_nome = _lab(o.get("avaliador") or "Avaliador")
                texto = (o.get("observacao") or "").strip()
                if not texto: continue
                g = _separar_obs(texto)
                for k in cont: cont[k] += len(g[k])
                por_av_total[av_nome] = por_av_total.get(av_nome, 0) + sum(len(g[k]) for k in ("fortes", "melhorar", "outras"))
                for item in g["melhorar"]:
                    frases.setdefault(item, [])
                    if av_nome not in frases[item]: frases[item].append(av_nome)
        mais_obs = ""
        if por_av_total:
            top_av, top_qtd = max(por_av_total.items(), key=lambda x: x[1])
            mais_obs = f"Quem mais observou: <b>{_esc(top_av)}</b> ({top_qtd} observações)"
        itens_html = ""
        for pos, (frase, autores) in enumerate(sorted(frases.items(), key=lambda x: -len(x[1]))):
            if pos >= 6: break
            autores_txt = ", ".join(f"({_esc(a)})" for a in autores)
            itens_html += f'<li><span class="obs-bullet">•</span>{_esc(frase)} <span class="obs-autor">{autores_txt}</span></li>'
        if len(frases) > 6: itens_html += f'<li class="obs-mais">+ {len(frases) - 6} outras menções…</li>'
        if not itens_html: itens_html = '<li class="obs-mais">Sem observações "A melhorar" registradas.</li>'
        obs_extra = f'<div class="obs-mais-obs">{mais_obs}</div>' if mais_obs else ""
        blocos.append(f'<div class="obs-dojo"><h4>{_esc(dojo_nome)}</h4>'
                      f'<div class="obs-cont"><span class="obs-forte">BOM! {cont["fortes"]}</span> · '
                      f'<span class="obs-melhorar">A melhorar {cont["melhorar"]}</span> · '
                      f'<span class="obs-outras">Outras {cont["outras"]}</span></div>{obs_extra}'
                      f'<ul class="obs-list">{itens_html}</ul></div>')
    if not blocos: return ""
    return (f'<section class="bloco" id="obs"><h2>Observações Agregadas</h2>'
            f'<p class="sub-bloco">Volume por classificação; quem mais observou; temas de "A melhorar" com o avaliador que os registrou (deduplicados).</p>'
            f'{"".join(blocos)}</section>')
_CSS_MASTER = """
*{box-sizing:border-box}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;margin:0;color:#222;background:#eef0f3;line-height:1.4}
.pagina{max-width:1080px;margin:0 auto;padding:24px}
.capa{background:linear-gradient(135deg,#1a1a1a,#333);color:#fff;border-radius:14px;padding:26px 30px;margin-bottom:16px}
.capa h1{margin:0 0 6px;font-size:24px}
.capa .sub{color:#ccc;font-size:13px}
.capa .meta{margin-top:12px;display:flex;gap:20px;flex-wrap:wrap;font-size:12px}
.capa .meta b{color:#fff}
.menu{position:sticky;top:0;z-index:5;background:#fff;border-radius:10px;padding:8px 12px;margin-bottom:16px;display:flex;gap:14px;flex-wrap:wrap;box-shadow:0 1px 3px rgba(0,0,0,.10)}
.menu a{color:#1f4e79;text-decoration:none;font-size:12px;font-weight:600}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.kpi{background:#fff;border-radius:12px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.metric-t{display:block;font-size:11px;color:#666;text-transform:uppercase;letter-spacing:.5px}
.metric-v{display:block;font-size:20px;font-weight:700;margin-top:4px}
.bloco{background:#fff;border-radius:12px;padding:20px;margin-top:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.bloco h2{margin:0 0 10px;font-size:17px;color:#1a1a1a}
.bloco h4{margin:14px 0 6px;font-size:13px;text-transform:uppercase;color:#555}
.sub-bloco{color:#666;font-size:12px;margin:-4px 0 12px}
.tbl-wrap{overflow-x:auto}
table.tab{width:100%;border-collapse:collapse;font-size:12px}
table.tab th,table.tab td{border:1px solid #e0e0e0;padding:6px 9px;text-align:center;vertical-align:middle;line-height:1.35}
table.tab th{background:#f4f5f7;color:#444;font-weight:600}
table.tab td.aluno{text-align:left;font-weight:600;white-space:normal;min-width:150px}
.status-mini{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}
.novafaixa{font-weight:700;color:#1f4e79;white-space:nowrap}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.recom-texto{white-space:normal;text-align:left;max-width:280px;min-width:160px;font-size:11px}
.divg-lista{text-align:left;margin-top:4px}
.divg-item{font-size:11px;line-height:1.35;margin:2px 0}
.divg-label{font-weight:600;color:#333}
.divg-item b{color:#b91c1c}
.divg-mais{color:#888;font-style:italic}
.hist{margin-top:6px}
.hist-linha{display:flex;align-items:center;gap:10px;margin:5px 0;font-size:12px}
.hist-rot{width:70px;color:#555;text-align:right}
.hist-barra{flex:1;height:14px;background:#eef0f3;border-radius:4px;overflow:hidden}
.hist-barra>div{height:100%;border-radius:4px}
.hist-val{width:80px;font-weight:600}
.rank-dojo{margin:10px 0}
.rank-reveal{background:none;border:none;padding:0;color:#1f4e79;font-weight:600;font-size:12px;cursor:pointer;text-align:left;font-family:inherit;border-bottom:1px dashed #1f4e79}
.rank-reveal:hover{color:#12365a;border-bottom-color:#12365a}
.rank-reveal.aberto{color:#7b2d8b;border-bottom-color:#7b2d8b}
.rank-detalhe-cel{background:#f7f8fa;padding:12px 14px}
.marc-detalhe h5{margin:0 0 8px;font-size:12px;text-transform:uppercase;color:#555;letter-spacing:.5px}
.marc-detalhe .marc-bloco{margin:6px 0}
.marc-detalhe table.tab{font-size:11px}
.treino-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.treino-card{border:1px solid #e4e6ea;border-radius:10px;padding:12px 14px}
.treino-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.treino-head h4{margin:0}
.treino-nota{margin-left:auto;font-weight:700;color:#555;font-size:12px}
.treino-card ul.recs li{margin-bottom:6px;padding-bottom:6px;border-bottom:1px dashed #eef0f3;font-size:12px}
.treino-card ul.recs li:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.obs-dojo{margin:6px 0}
.obs-cont{font-size:12px;margin:2px 0}
.obs-mais-obs{font-size:12px;margin:4px 0;color:#333}
.obs-list{list-style:none;margin:6px 0 0;padding:0}
.obs-list li{font-size:12px;line-height:1.4;padding:3px 0;border-bottom:1px dashed #f0f0f0}
.obs-list li:last-child{border-bottom:none}
.obs-list .obs-bullet{color:#b7791f;margin-right:6px}
.obs-list .obs-mais{color:#888;font-style:italic}
.obs-autor{color:#1f4e79;font-weight:600;font-size:11px;margin-left:4px}
.obs-forte{color:#1a7f37}.obs-melhorar{color:#b7791f}.obs-outras{color:#666}
.rec-meta{color:#888;font-size:11px}
.rec-motivo,.rec-plano{color:#555;font-size:12px;margin-top:2px}
ul{margin:0;padding-left:0;list-style:none}
@media (max-width:820px){.kpi-grid{grid-template-columns:repeat(2,1fr)}.menu{position:static}.treino-grid{grid-template-columns:1fr}}
@media print{body{background:#fff}.pagina{max-width:100%;padding:0}.bloco{box-shadow:none;break-inside:avoid}.capa{border-radius:0}.menu{display:none}.obs-dojo,.treino-card{break-inside:avoid}.rank-detalhes{display:none!important}}
"""
_JS_RANK = """<script>
function toggleRankMarks(btn){var tr=btn.closest('tr');var det=tr.nextElementSibling;if(!det||det.className.indexOf('rank-detalhes')<0){return;}if(det.style.display==='none'){det.style.display='table-row';btn.classList.add('aberto');}else{det.style.display='none';btn.classList.remove('aberto');}}
</script>"""
def gerar_html_master(resultados_dojos, regras, recomendacoes, titulo="Relatório Master Consolidado", exame_id="", nomes=None, avaliadores_map=None, dojos_map=None):
    dojos_map = dojos_map if dojos_map is not None else _carregar_nomes_dojos()
    todos = [a for d in resultados_dojos for a in d.get("alunos", [])]
    pres = [a for a in todos if a.get("status") != "AUSENTE"]
    n, np_ = len(todos), len(pres)
    c = _status_counts(todos)
    aprov = c["APROVADO"] + c["APROVADO_PONTO_ATENCAO"]
    media = (sum(a.get("nota_final", 0.0) for a in pres) / np_) if np_ else 0.0
    ordem = _carregar_ordem_faixas()
    novas = sum(1 for a in pres if _nova_faixa(a.get("faixa", ""), a.get("status", ""), ordem) not in ("—", "Faixa máxima"))
    pct_pres = (np_ / n * 100) if n else 0.0
    pct_aprov = (aprov / n * 100) if n else 0.0
    dojo_capa = (f"<div><b>Dojo:</b> {_esc(_nome_dojo(resultados_dojos[0].get('dojo_id', '?'), dojos_map))}</div>" if len(resultados_dojos) == 1 else f"<div><b>Dojos:</b> {len(resultados_dojos)}</div>")
    treino_html = _bloco_treino_direcionado(todos, recomendacoes, nomes)
    menu_items = [("topo", "Resumo"), ("hist", "Notas"), ("ranking", "Ranking"), ("criticos", "Atenção"), ("consist", "Divergências"), ("perfil", "Perfil")]
    if treino_html: menu_items.append(("treino", "Treino"))
    menu_items.append(("obs", "Observações"))
    menu = "<nav class='menu'>" + "".join(f"<a href='#{k}'>{v}</a>" for k, v in menu_items) + "</nav>"
    kpi = (f"<div class='kpi'><span class='metric-t'>Alunos</span><span class='metric-v'>{n}</span></div>"
           f"<div class='kpi'><span class='metric-t'>Presentes</span><span class='metric-v'>{np_} ({pct_pres:.0f}%)</span></div>"
           f"<div class='kpi'><span class='metric-t'>Aprovados</span><span class='metric-v' style='color:#1a7f37'>{aprov} ({pct_aprov:.0f}%)</span></div>"
           f"<div class='kpi'><span class='metric-t'>C/ atenção</span><span class='metric-v' style='color:#b7791f'>{c['APROVADO_PONTO_ATENCAO']}</span></div>"
           f"<div class='kpi'><span class='metric-t'>Recuperação</span><span class='metric-v' style='color:#c62828'>{c['RECUPERACAO']}</span></div>"
           f"<div class='kpi'><span class='metric-t'>Ausentes</span><span class='metric-v' style='color:#6a737d'>{c['AUSENTE']}</span></div>"
           f"<div class='kpi'><span class='metric-t'>Média</span><span class='metric-v' style='color:#1f4e79'>{media:.1f}</span></div>"
           f"<div class='kpi'><span class='metric-t'>Novas faixas</span><span class='metric-v' style='color:#7b2d8b'>{novas}</span></div>")
    blocos = "".join([_bloco_histograma(resultados_dojos),
                      _bloco_ranking_contexto(resultados_dojos, nomes, dojos_map, avaliadores_map),
                      _bloco_criticos_recomendacoes(todos, recomendacoes),
                      _bloco_consistencia(resultados_dojos, nomes, avaliadores_map, dojos_map),
                      _bloco_perfil_avaliadores(resultados_dojos, avaliadores_map),
                      treino_html,
                      _bloco_obs_agregadas(resultados_dojos, dojos_map, avaliadores_map)])
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(titulo)}</title>
<style>
{_CSS_MASTER}
</style>
</head>
<body id="topo">
<div class="pagina">
<header class="capa">
<h1>{_esc(titulo)}</h1>
<div class="sub">Sistema Karate-Ashi · Visão Estratégica Multi-Dojo (v3.8)</div>
<div class="meta">
<div><b>Exame(s):</b> {_esc(exame_id) or '—'}</div>
{dojo_capa}
<div><b>Alunos presentes:</b> {np_}</div>
</div>
</header>
{menu}
<div class="kpi-grid">{kpi}</div>
{blocos}
</div>
{_JS_RANK}
</body>
</html>"""
def salvar_html_master(resultados_dojos, regras, recomendacoes, destino, exame_id="", titulo="Relatório Master Consolidado", nomes=None, avaliadores_map=None, dojos_map=None):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(gerar_html_master(resultados_dojos, regras, recomendacoes, titulo, exame_id, nomes, avaliadores_map, dojos_map), encoding="utf-8")
    return destino
# ---------- INDIVIDUAL ----------
_STATUS_LABEL = {"APROVADO": "Aprovado", "APROVADO_PONTO_ATENCAO": "Aprovado (com atenção)", "RECUPERACAO": "Recuperação", "REPROVADO": "Reprovado", "REVISAO_PENDENTE": "Revisão pendente", "AUSENTE": "Ausente"}
def _status_label(status): return _STATUS_LABEL.get(status, status or "?")
def _freq_reais_consolidadas(r):
    freq = r.get("frequencias_reais") or {}
    if freq:
        return {q: {c: int(f) for c, f in b.items() if f} for q, b in freq.items()}
    cons = {}
    for av in (r.get("frequencias_por_avaliador") or []):
        for q, blocos in (av or {}).items():
            for ch, f in (blocos or {}).items():
                if f:
                    cons.setdefault(q, {})[ch] = cons[q].get(ch, 0) + int(f)
    return cons
def _tabela_marcacoes_individual(r, avaliadores_map):
    avaliadores_map = avaliadores_map or _carregar_avaliadores_map()
    por_av = r.get("frequencias_por_avaliador") or []
    av_ids = r.get("avaliadores_ids") or [f"A{i + 1}" for i in range(len(por_av))]
    labels = [avaliadores_map.get(str(aid), "") or str(aid) or f"A{i + 1}" for i, aid in enumerate(av_ids)] or ["Avaliador 1"]
    tem_av = bool(por_av)
    freq_cons = _freq_reais_consolidadas(r)
    quesitos = r.get("quesitos") or {}
    blocos = []
    for q, qnome in NOME_QUESITO.items():
        det = (quesitos.get(q) or {}).get("detalhes") or {}
        linhas, tem_marcacao = [], False
        for chave, d in det.items():
            vals = [int((avp.get(q) or {}).get(chave, 0) or 0) for avp in por_av] if tem_av else []
            total = int((freq_cons.get(q) or {}).get(chave, 0) or 0)
            if tem_av and total == 0: total = sum(vals)
            if total == 0: continue
            tem_marcacao = True
            nome_c = d.get("nome") or chave
            if tem_av:
                tds = "".join(f"<td>{v if v else ''}</td>" for v in vals)
                linhas.append(f'<tr><td class="crit">{_esc(nome_c)}</td>{tds}<td class="freq-total">{total}</td></tr>')
            else:
                linhas.append(f'<tr><td class="crit">{_esc(nome_c)}</td><td class="freq-total">{total}</td></tr>')
        if not tem_marcacao: continue
        th = "".join(f"<th>{_esc(lb)}</th>" for lb in labels) if tem_av else ""
        cabecalho = f"<th>Critério</th>{th}<th>Frequência</th>" if tem_av else "<th>Critério</th><th>Frequência</th>"
        blocos.append(f'<div class="marc-bloco"><span class="marc-q-nome">{_esc(qnome)}</span>'
                      f'<table class="tab tab-ind"><thead><tr>{cabecalho}</tr></thead><tbody>{"".join(linhas)}</tbody></table></div>')
    return "".join(blocos) or "<p class='vazio'>Sem marcações.</p>"
_CSS_INDIV = """
*{box-sizing:border-box}
body{font-family:'Segoe UI',Roboto,Arial,sans-serif;margin:0;color:#222;background:#eef0f3}
.pagina{max-width:1000px;margin:0 auto;padding:32px}
.capa{background:linear-gradient(135deg,#1a1a1a,#333);color:#fff;border-radius:14px;padding:24px 28px;margin-bottom:20px}
.capa h1{margin:0 0 4px;font-size:22px}
.capa .sub{color:#ccc;font-size:13px}
.capa .meta{margin-top:12px;display:flex;gap:18px;flex-wrap:wrap;font-size:12px}
.capa .meta b{color:#fff}
.individual-card{display:flex;flex-direction:column;gap:16px}
.bloco{background:#fff;border-radius:12px;padding:18px 20px;border:1px solid #e4e6ea}
.bloco h2{margin:0 0 10px;font-size:16px;color:#1a1a1a}
.bloco-topo{display:grid;grid-template-columns:auto 1fr;gap:12px 28px;align-items:center}
.bloco-topo h2{grid-column:1 / -1;margin-bottom:2px}
.nota-wrap{display:flex;align-items:center;gap:14px}
.nota-final{font-size:38px;font-weight:800;line-height:1}
.status{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700;color:#fff}
.ref-limites{font-size:12px;color:#555}
.ref-limites h4{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#555}
.ref-limites .ref-linha{display:flex;align-items:center;gap:8px;margin:3px 0}
.ref-limites .ref-dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
.ref-limites b{color:#333}
.ind-grid{display:grid;grid-template-columns:0.9fr 1.35fr;gap:16px;align-items:start}
.mini-q{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12px}
.mini-q-nome{width:70px;color:#555}
.mini-q-bar{flex:1;height:9px;background:#eef0f3;border-radius:4px;overflow:hidden}
.mini-q-fill{height:100%;border-radius:4px}
.mini-q-val{width:36px;text-align:right;font-weight:600}
.marc-bloco{margin:8px 0}
.marc-q-nome{display:block;font-weight:700;color:#555;font-size:12px;text-transform:uppercase;margin-bottom:4px}
table.tab{width:100%;border-collapse:collapse;font-size:12px}
table.tab th,table.tab td{border:1px solid #e0e0e0;padding:4px 8px;text-align:center}
table.tab th{background:#f4f5f7;color:#444;font-weight:600}
table.tab td.crit{text-align:left;color:#333}
.freq-total{font-weight:700;color:#1f4e79}
.obs-forte{color:#1a7f37}.obs-melhorar{color:#b7791f}.obs-outras{color:#666}
.vazio{color:#999;font-size:12px}
.rodape{margin-top:26px;padding-top:12px;border-top:1px solid #e4e6ea;font-size:11px;color:#888;text-align:center}
@media (max-width:920px){.ind-grid{grid-template-columns:1fr}.bloco-topo{grid-template-columns:1fr;gap:12px}}
@media print{body{background:#fff}.pagina{max-width:100%;padding:16px}.bloco{break-inside:avoid;border:none}.capa{border-radius:0}}
"""
def gerar_html_individual(r, nomes=None, exame_id="", dojo_id="", dojo_nome=None):
    aluno_id = str(r.get("aluno_id", "?"))
    nome = (nomes or {}).get(aluno_id, "") or aluno_id
    faixa, nota, status = r.get("faixa", ""), r.get("nota_final", 0.0), r.get("status", "?")
    fg, _ = _status_cor(status)
    dojo_exib = dojo_nome or dojo_id
    bars = ""
    for q, qnome in NOME_QUESITO.items():
        nq = (r.get("quesitos", {}).get(q, {}) or {}).get("nota", 0.0)
        cor = COR_QUESITO.get(q, "#333")
        pct = min(100.0, nq / 25.0 * 100.0)
        bars += f'<div class="mini-q"><span class="mini-q-nome">{_esc(qnome)}</span><div class="mini-q-bar"><div class="mini-q-fill" style="width:{pct:.0f}%;background:{cor}"></div></div><span class="mini-q-val">{nq:.1f}</span></div>'
    marc_html = _tabela_marcacoes_individual(r, None)
    textos = []
    for o in (r.get("observacoes_por_avaliador") or []):
        t = (o.get("observacao") or "").strip()
        if t and t not in textos: textos.append(t)
    grupos = {"fortes": [], "melhorar": [], "outras": []}
    for t in textos:
        g = _separar_obs(t)
        for k in grupos: grupos[k].extend(g[k])
    for k in grupos:
        vistos, saida = set(), []
        for item in grupos[k]:
            if item not in vistos:
                vistos.add(item); saida.append(item)
        grupos[k] = saida
    obs_partes = []
    if grupos["fortes"]: obs_partes.append(f'<p class="obs-forte"><b>Pontos fortes (BOM!):</b> {_esc(" · ".join(grupos["fortes"]))}</p>')
    if grupos["melhorar"]: obs_partes.append(f'<p class="obs-melhorar"><b>A melhorar:</b> {_esc(" · ".join(grupos["melhorar"]))}</p>')
    if grupos["outras"]: obs_partes.append(f'<p class="obs-outras"><b>Outras:</b> {_esc(" · ".join(grupos["outras"]))}</p>')
    obs_html = "".join(obs_partes) or "<p class='vazio'>Sem observações.</p>"
    lim = _limites_status()
    aprov, atenc, rec = lim["aprovado"], lim["atencao"], lim["recuperacao"]
    atenc_txt = (f"{aprov:.1f} a {atenc - 0.1:.1f}" if atenc > aprov else f"a partir de {aprov:.1f} (com ressalvas)")
    rec_txt = (f"{rec:.1f} a {aprov - 0.1:.1f}" if rec < aprov else f"abaixo de {aprov:.1f}")
    ref_lim = (f'<div class="ref-limites"><h4>Referência para a nota</h4>'
               f'<div class="ref-linha"><span class="ref-dot" style="background:#1a7f37"></span><span><b>Aprovado:</b> a partir de {atenc:.1f}</span></div>'
               f'<div class="ref-linha"><span class="ref-dot" style="background:#b7791f"></span><span><b>Aprovado com atenção:</b> {atenc_txt}</span></div>'
               f'<div class="ref-linha"><span class="ref-dot" style="background:#c62828"></span><span><b>Recuperação:</b> {rec_txt}</span></div></div>')
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Relatório Individual — {_esc(nome)}</title>
<style>
{_CSS_INDIV}
</style>
</head>
<body>
<div class="pagina">
<header class="capa">
<h1>{_esc(nome)}</h1>
<div class="sub">Sistema Karate-Ashi · Relatório Individual do Aluno</div>
<div class="meta">
<div><b>Dojo:</b> {_esc(dojo_exib)}</div>
<div><b>Exame:</b> {_esc(exame_id) or '—'}</div>
<div><b>Faixa:</b> {_esc(faixa)}</div>
<div><b>Gerado em:</b> {_esc(data)}</div>
</div>
</header>
<div class="individual-card">
<section class="bloco bloco-topo">
<h2>Nota Final</h2>
<div class="nota-wrap"><span class="nota-final">{nota:.1f}</span><span class="status" style="background:{fg}">{_esc(_status_label(status))}</span></div>
{ref_lim}
</section>
<div class="ind-grid">
<section class="bloco"><h2>Notas por Quesito</h2>{bars}</section>
<section class="bloco"><h2>Marcações do Exame</h2>{marc_html}</section>
</div>
<section class="bloco"><h2>Observações</h2>{obs_html}</section>
</div>
<div class="rodape">Documento gerado automaticamente pelo Sistema Karate-Ashi.</div>
</div>
</body>
</html>"""
def salvar_individuais_exame(resultados, destino_dir, exame_id="", dojo_id="", nomes=None, dojo_nome=None):
    destino_dir = Path(destino_dir)
    destino_dir.mkdir(parents=True, exist_ok=True)
    salvos = []
    for r in resultados:
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        arquivo = destino_dir / f"relatorio_individual_{_slug_nome(nome)}.html"
        arquivo.write_text(gerar_html_individual(r, nomes, exame_id, dojo_id, dojo_nome), encoding="utf-8")
        salvos.append(arquivo)
    return salvos
def _bloco_lista_aprovacao(resultados, nomes=None):
    ordem = _carregar_ordem_faixas()
    aprovados = [r for r in resultados if r.get("status") in ("APROVADO", "APROVADO_PONTO_ATENCAO")]
    if not aprovados:
        return ('<section class="bloco"><h2>Resultado do Exame — Lista de Aprovação</h2>'
                '<p class="vazio">Nenhum aluno aprovado neste exame.</p></section>')
    aprovados.sort(key=lambda r: str((nomes or {}).get(str(r.get("aluno_id", "?")), r.get("aluno_id", "?"))))
    linhas = []
    for r in aprovados:
        aluno_id = str(r.get("aluno_id", "?"))
        nome = (nomes or {}).get(aluno_id, "") or aluno_id
        status = r.get("status", "?")
        fg, _ = _status_cor(status)
        nova = _nova_faixa(r.get("faixa", ""), status, ordem)
        linhas.append(f'<tr><td class="aluno">{_esc(nome)}</td>'
                      f'<td>{_esc(r.get("faixa", ""))}</td>'
                      f'<td class="novafaixa">{_esc(nova)}</td>'
                      f'<td><span class="status-mini" style="background:{fg};color:#fff">{_esc(_status_label(status))}</span></td></tr>')
    return (f'<section class="bloco"><h2>Resultado do Exame — Lista de Aprovação</h2>'
            f'<table class="tab"><thead><tr><th>Aluno</th><th>Faixa</th><th>Nova Faixa</th><th>Status</th></tr></thead>'
            f'<tbody>{"".join(linhas)}</tbody></table></section>')