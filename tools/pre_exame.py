#!/usr/bin/env python3
"""tools/pre_exame.py — Gera folhas PDF (NOVO layout OMR) orientado por manifest.

Uso:
  python tools/pre_exame.py --exame EXA-D01-2026-10
  python tools/pre_exame.py --exame EXA-D01-2026-10 --csv data/alunos_exame.csv
  python tools/pre_exame.py --validar

NOVO LAYOUT (v5.5 — observações no rodapé, critérios em largura total):
- A4 PAISAGEM (297x210mm), até 3 alunos por folha (paginação automática).
- QR do exame (avaliador_id | dojo_id | exame_id) no canto superior direito,
  REDUZIDO para 14mm.
- QR dos ALUNOS no CABEÇALHO (3 QRs de 11mm). A POSIÇÃO do QR no cabeçalho
  define a linha: 1º QR (x=195) -> linha 1, 2º QR (x=214) -> linha 2,
  3º QR (x=233) -> linha 3.
- NOME do aluno no topo da linha + BALÃO CIRCULAR DE PRESENÇA AO LADO.
- 4 colunas de quesitos (Kihon, Kata, Bunkai, Kumite) em LARGURA TOTAL.
- CRUZES DE REFERÊNCIA DAS LINHAS: 2 cruzes por linha de aluno
  (x=5mm e x=292mm, na MARGEM, a 4mm do fundo). Calibração LOCAL da linha.
- CRUZES DE REFERÊNCIA DAS OBSERVAÇÕES: 2 cruzes GLOBAIS na MARGEM, na
  altura do rodapé (x=5mm e x=292mm, y=202mm, bloco 0).
- v5.5: cruzes desenhadas como RETÂNGULOS PREENCHIDOS sobrepostos (região
  sólida contínua no centro) — a impressora imprime o "+" maciço, nunca
  traços separados. Braço 2.0mm, espessura 1.2mm.
- OBSERVAÇÕES NO RODAPÉ (40mm): 3 blocos (um por aluno), BOM! / A MELHORAR.
- Exporta as coordenadas de cada balão E de cada cruz (mm) em JSON por folha.

Fluxo (manifest-driven):
1. lê data/exames.json e localiza o exame pelo ID;
2. valida o manifest;
3. (opcional) lê o CSV e faz merge idempotente no cadastro;
4. seleciona os elegíveis do DOJO do exame;
5. para cada AVALIADOR do manifest, gera um PDF com as folhas (3 alunos/página);
6. grava as coordenadas dos balões e cruzes em JSON por folha.

Dependências: qrcode[pil], reportlab.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import argparse
import csv
import json
import tempfile
import unicodedata
from datetime import date
import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from core.cadastro import alunos_para_exame
from core.config import (
    FAIXAS_SUPORTADAS,
    QUESITOS as QUESITOS_ORDEM,
    carregar_json,
)

RAIZ = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# NOVO LAYOUT — A4 PAISAGEM (v5.5)
# ---------------------------------------------------------------------------
A4_W_MM, A4_H_MM = 297.0, 210.0
ALUNOS_POR_FOLHA = 3
BALOES_POR_CRITERIO = 5

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]
NOME_QUESITO = {"kihon": "Kihon", "kata": "Kata", "bunkai": "Bunkai", "kumite": "Kumite"}

# Critérios padrão — TEXTO POR EXTENSO (sem abreviações)
CRITERIOS = {
    "kihon": ["Base Incorreta", "Execucao Tecnica Incorreta", "Movimento sem Carga",
              "Falta de Foco", "Perda de Equilibrio", "Ausencia de Kiai"],
    "kata": ["Embusen Incorreto", "Base Incorreta", "Falta de Ritmo", "Ausencia de Kiai",
             "Execucao Tecnica Incorreta", "Movimento sem Carga", "Falta de Foco",
             "Perda de Equilibrio"],
    "bunkai": ["Base Incorreta", "Ausencia de Kiai", "Execucao Tecnica Incorreta",
               "Movimento sem Carga", "Falta de Foco", "Perda de Equilibrio",
               "Distancia Inadequada", "Falta de Controle"],
    "kumite": ["Movimento sem Carga", "Falta de Foco", "Perda de Equilibrio",
               "Ausencia de Kiai", "Distancia Inadequada", "Falta de Combatividade",
               "Falta de Controle"],
}

# Observações estruturadas (6+6) — textos finais validados
OBS_P = ["Boa execucao dos Kihons", "Bom dominio do Kata", "Boa aplicacao do Bunkai",
         "Boa Conducao no Kumite", "Bom Dominio Tecnico", "Otimo Desempenho"]
OBS_M = ["Dificuldade nos Kihon", "Dificuldade no Kata", "Dificuldade no Bunkai",
         "Dificuldade nos Kumites", "Erros Tecnicos Constantes", "Nervosismo Constante"]

# Geometria em mm (fonte única)
MARGEM = 10.0
HEADER_H = 28.0                       # cabeçalho (compacto)
FOOTER_H = 40.0                       # rodapé de observações (ampliado)
LINHA_Y0 = HEADER_H
LINHA_H = (A4_H_MM - HEADER_H - FOOTER_H) / ALUNOS_POR_FOLHA  # (210-28-40)/3 = 47.33mm
FOOTER_Y0 = LINHA_Y0 + 3 * LINHA_H    # início do rodapé (170mm)

# QR do exame (canto superior direito) — REDUZIDO para 14mm
QR_CAB_X = A4_W_MM - MARGEM - 14.0    # 273mm
QR_CAB_Y = 8.0
QR_CAB_TAM = 14.0

# QR dos ALUNOS no CABEÇALHO — posição define a linha (1º=linha1, 2º=linha2, 3º=linha3)
QR_ALUNO_CAB_X = [195.0, 214.0, 233.0]
QR_ALUNO_CAB_Y = 8.0
QR_ALUNO_CAB_TAM = 11.0

# Linha do aluno — NOME + BALÃO CIRCULAR DE PRESENÇA AO LADO
NOME_X = 10.0
NOME_Y = 2.0                          # topo da linha
NOME_LARG = 150.0                     # limite do nome (balão logo após)
PRES_RAIO = 1.8                       # balão circular de presença (raio 1.8mm)

# CRUZES DE REFERÊNCIA (v5.5) — SÓLIDAS, retângulos preenchidos
CRUZ_BRACO = 2.0                      # braço da cruz (mm) — total 4mm
CRUZ_ESPESSURA = 1.2                  # espessura (mm) — área maciça

# CRUZES DAS LINHAS — na MARGEM da folha, fora do conteúdo
CRUZ_X_ESQ = 5.0                      # cruz esquerda (mm) — na margem
CRUZ_X_DIR = 292.0                    # cruz direita (mm) — na margem
CRUZ_Y_FIM = 4.0                      # distância da cruz ao fundo da linha (mm)

# CRUZES DAS OBSERVAÇÕES — GLOBAIS na margem, na altura do rodapé (bloco 0)
CRUZ_OBS_X_ESQ = 5.0                  # margem esquerda (mesma das linhas)
CRUZ_OBS_X_DIR = 292.0                # margem direita (mesma das linhas)
CRUZ_OBS_Y = 202.0                    # altura do rodapé, abaixo dos itens (170+8+20+4)

# Blocos de quesito (4 colunas) — LARGURA TOTAL (69mm cada)
QUESITO_X0 = 10.0
QUESITO_LARG = 69.0                   # 10 a 286mm (4 × 69 = 276mm)
QUESITO_TITLE_Y0 = 5.0                # topo da faixa cinza (abaixo do nome)
QUESITO_TITLE_H = 3.0                 # altura da faixa cinza
QUESITO_TITLE_CY = 6.5                # centro do texto na faixa
CRIT_Y0 = 9.5                         # primeira linha de critério
CRIT_ESPACO = 4.6                     # espaçamento (preenche a linha)
TEXTO_CRIT_X = 1.0
BALAO_X0 = 40.0                       # área de texto ~39mm (textos por extenso)
BALAO_ESPACO = 5.0
BALAO_RAIO = 1.8                      # balão de critério
BALAO_Y_OFFSET = 1.2                  # alinhamento do balão com o centro visual do texto

# Observações — RODAPÉ (v4.9)
OBS_BLOCK_Y = 3.0                     # rótulo do aluno (abaixado, longe da borda)
OBS_COL_TITLE_Y = 5.5                 # título "BOM!" / "A MELHORAR"
OBS_BLOCK_GAP = 2.0                   # vão entre blocos
OBS_ITEM_Y0 = 8.0                     # primeiro item
OBS_ITEM_ESPACO = 4.0                 # espaçamento (folga entre círculos)
OBS_RAIO = 1.5                        # círculo de observação
OBS_CHK_X_OFFSET = 3.5                # círculo a 3,5mm da borda do bloco
OBS_TEXTO_GAP = 3.0                   # texto após o círculo

# Tipografia
FONTE_TITULO = 13
FONTE_SUBTITULO = 9
FONTE_INSTRUCAO = 6.5
FONTE_QUESITO = 6.5
FONTE_CRITERIO = 7.0
FONTE_CRITERIO_MIN = 6.0
FONTE_OBS = 6.0
FONTE_OBS_TITULO = 5.5
FONTE_NOME = 6.5
FONTE_PRESENCA = 6

# Campos de ciclo de vida — preservados no merge
CAMPOS_CICLO_VIDA = ("ativo", "ultima_promocao", "historico_promocoes")
CAMPOS_CSV = ("nome", "faixa_atual", "faixa_pretendida", "dojo_id")


# ---------------------------------------------------------------------------
# CARGA DOS ARQUIVOS JSON
# ---------------------------------------------------------------------------
def carregar_dojos(config_dir: Path) -> dict:
    """config/dojos.json (lista de objetos) -> {id: nome}."""
    caminho = config_dir / "dojos.json"
    if not caminho.exists():
        return {}
    try:
        dados = carregar_json(caminho)
    except (json.JSONDecodeError, OSError):
        print(f"[AVISO] dojos.json inválido, ignorado: {caminho}")
        return {}
    if isinstance(dados, dict) and isinstance(dados.get("dojos"), list):
        return {d["id"]: d["nome"] for d in dados["dojos"]
                if isinstance(d, dict) and "id" in d}
    if isinstance(dados, dict):
        return dados  # formato antigo {id: nome}
    return {}


def carregar_avaliadores(config_dir: Path) -> dict:
    """config/avaliadores.json (lista de objetos) -> {id: nome}."""
    caminho = config_dir / "avaliadores.json"
    if not caminho.exists():
        return {}
    try:
        dados = carregar_json(caminho)
    except (json.JSONDecodeError, OSError):
        print(f"[AVISO] avaliadores.json inválido, ignorado: {caminho}")
        return {}
    if isinstance(dados, dict) and isinstance(dados.get("avaliadores"), list):
        return {a["id"]: a["nome"] for a in dados["avaliadores"]
                if isinstance(a, dict) and "id" in a}
    if isinstance(dados, dict):
        return dados  # formato antigo {id: nome}
    return {}


def carregar_manifest() -> list[dict]:
    """Lê data/exames.json e devolve a lista de exames."""
    caminho = RAIZ / "data" / "exames.json"
    if not caminho.exists():
        raise FileNotFoundError(
            f"Manifest não encontrado: {caminho}\n"
            f"Crie data/exames.json com a agenda de exames.")
    dados = carregar_json(caminho)
    exames = dados.get("exames") if isinstance(dados, dict) else None
    if not isinstance(exames, list):
        raise ValueError(f"{caminho}: esperado nó 'exames' com uma lista.")
    return exames


def gerar_id_exame(dojo_id: str, data_exame: date) -> str:
    """ID do exame: dojo + ano + mês da DATA DO EXAME (não da geração)."""
    return f"EXA-{dojo_id}-{data_exame.year:04d}-{data_exame.month:02d}"


def validar_manifest(exames: list[dict], dojos: dict,
                     avaliadores: dict) -> list[str]:
    """Valida o manifest e devolve a lista de erros (vazia = tudo ok)."""
    erros: list[str] = []
    vistos: set[tuple[str, str]] = set()  # (dojo_id, ano-mes)
    for exame in exames:
        eid = exame.get("id", "?")
        dojo_id = exame.get("dojo_id")
        if dojo_id not in dojos:
            erros.append(f"{eid}: dojo_id '{dojo_id}' não existe em dojos.json")
        for av in exame.get("avaliadores", []):
            if av not in avaliadores:
                erros.append(f"{eid}: avaliador '{av}' não existe em avaliadores.json")
        try:
            data = date.fromisoformat(exame["data_exame"])
            esperado = gerar_id_exame(dojo_id, data)
            if eid != esperado:
                erros.append(
                    f"{eid}: ID inconsistente — esperado '{esperado}' "
                    f"para dojo {dojo_id} em {exame['data_exame']}")
            chave = (dojo_id, f"{data.year:04d}-{data.month:02d}")
            if chave in vistos:
                erros.append(f"{eid}: já existe outro exame do mesmo dojo no mesmo mês")
            vistos.add(chave)
        except (ValueError, TypeError):
            erros.append(f"{eid}: data_exame inválida '{exame.get('data_exame')}'")
    return erros


def carregar_criterios(config_dir: Path, faixa_base: str = "branca") -> dict:
    """Carrega os critérios de config/faixas/<faixa>.json (fonte única)."""
    caminho = config_dir / "faixas" / f"{faixa_base}.json"
    if caminho.exists():
        try:
            dados = carregar_json(caminho)
            quesitos = dados.get("quesitos", {})
            criterios = {}
            for q in QUESITOS:
                bloco = quesitos.get(q, {})
                lista = bloco.get("criterios", []) if isinstance(bloco, dict) else []
                criterios[q] = [c["nome"] if isinstance(c, dict) else str(c)
                                for c in lista]
            if all(criterios.get(q) for q in QUESITOS):
                return criterios
        except Exception as exc:
            print(f"[AVISO] falha ao ler {caminho} ({exc}); usando criterios padrao.")
    return CRITERIOS


def _rotulo(identificador: str, nomes: dict) -> str:
    """'S01' -> 'Sensei Paulo (S01)'; sem nome cadastrado, só o ID."""
    nome = nomes.get(identificador)
    return f"{nome} ({identificador})" if nome else identificador


def normalizar_faixa(faixa: str) -> str:
    """Remove acentos e normaliza para uppercase (payload QR sem acentos)."""
    sem_acentos = unicodedata.normalize("NFKD", faixa)
    ascii_only = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return ascii_only.upper().strip()


def atualizar_cadastro(csv_path: Path, cadastro_path: Path) -> list[dict]:
    """Merge idempotente do CSV no alunos.json (ciclo de vida preservado)."""
    cadastro = (json.loads(cadastro_path.read_text(encoding="utf-8"))
                if cadastro_path.exists() else {"alunos": []})
    por_id = {a["id"]: a for a in cadastro["alunos"]}
    novos = []
    with open(csv_path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            aluno_id = row["id"]
            if aluno_id not in por_id:
                aluno = {"id": aluno_id,
                         **{campo: row.get(campo, "") for campo in CAMPOS_CSV},
                         "novo": True,
                         "ativo": True,
                         "ultima_promocao": None,
                         "historico_promocoes": []}
                cadastro["alunos"].append(aluno)
                por_id[aluno_id] = aluno
                novos.append(aluno)
            else:
                existente = por_id[aluno_id]
                for campo in CAMPOS_CSV:
                    if row.get(campo):
                        existente[campo] = row[campo]
                existente.setdefault("ativo", True)
                existente.setdefault("ultima_promocao", None)
                existente.setdefault("historico_promocoes", [])
    cadastro_path.parent.mkdir(parents=True, exist_ok=True)
    cadastro_path.write_text(
        json.dumps(cadastro, ensure_ascii=False, indent=2), encoding="utf-8")
    return novos


# ---------------------------------------------------------------------------
# FUNÇÕES DE DESENHO (reportlab — coordenadas em mm, y medido do TOPO)
# ---------------------------------------------------------------------------
def quebrar_linhas(texto: str, fonte: str, tamanho: float,
                   largura_max: float) -> list[str]:
    """Divide o texto em linhas que cabem em largura_max."""
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if stringWidth(teste, fonte, tamanho) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas


def desenhar_balao(pdf: canvas.Canvas, cx_mm: float, cy_topo_mm: float,
                   raio_mm: float) -> None:
    """Balão oval centrado em (cx, cy_topo), raio em mm."""
    cy = (A4_H_MM - cy_topo_mm) * mm
    x1 = (cx_mm - raio_mm) * mm
    y1 = cy - raio_mm * mm
    x2 = (cx_mm + raio_mm) * mm
    y2 = cy + raio_mm * mm
    pdf.ellipse(x1, y1, x2, y2)


def desenhar_cruz(pdf: canvas.Canvas, cx_mm: float, cy_topo_mm: float,
                  braco_mm: float, espessura_mm: float) -> None:
    """Cruz '+' SÓLIDA (retângulos preenchidos que se sobrepõem).

    v5.5: em vez de duas linhas independentes (que a impressora rasteriza
    como traços separados, sem junção), desenhamos DOIS RETÂNGULOS
    PREENCHIDOS que se cruzam no centro. A interseção vira uma região
    preenchida contínua — qualquer impressora imprime um '+' maciço.
    """
    cy = (A4_H_MM - cy_topo_mm) * mm
    pdf.setFillColorRGB(0, 0, 0)
    # Braço horizontal: retângulo de (cx-braco) a (cx+braco), altura = espessura
    pdf.rect((cx_mm - braco_mm) * mm,
             (cy - espessura_mm / 2) * mm,
             (2 * braco_mm) * mm,
             espessura_mm * mm,
             stroke=0, fill=1)
    # Braço vertical: retângulo de (cy-braco) a (cy+braco), largura = espessura
    pdf.rect((cx_mm - espessura_mm / 2) * mm,
             (cy - braco_mm) * mm,
             espessura_mm * mm,
             (2 * braco_mm) * mm,
             stroke=0, fill=1)


def desenhar_texto_centralizado(pdf: canvas.Canvas, texto: str, x_mm: float,
                                cy_topo_mm: float, tamanho: float,
                                fonte: str = "Helvetica") -> None:
    """Texto com o CENTRO VERTICAL alinhado a cy_topo (baseline -0.35*tam)."""
    pdf.setFont(fonte, tamanho)
    cy = (A4_H_MM - cy_topo_mm) * mm
    pdf.drawString(x_mm * mm, cy - tamanho * 0.35, texto)


def desenhar_qr(pdf: canvas.Canvas, dados: str, x_mm: float, y_topo_mm: float,
                lado_mm: float, tmp_dir: Path, nome_arquivo: str) -> None:
    """Gera o QR e o desenha no PDF (canto superior direito, nada cobre)."""
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(dados)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    caminho = tmp_dir / nome_arquivo
    img.save(caminho)
    pdf.drawImage(str(caminho), x_mm * mm,
                  (A4_H_MM - y_topo_mm - lado_mm) * mm,
                  lado_mm * mm, lado_mm * mm)


def desenhar_criterio(pdf: canvas.Canvas, x_mm: float, cy_topo_mm: float,
                      texto: str, largura_max_mm: float) -> None:
    """Texto do critério POR EXTENSO (até 2 linhas) centralizado no balão."""
    largura_max = largura_max_mm * mm
    tamanho = FONTE_CRITERIO
    linhas = quebrar_linhas(texto, "Helvetica", tamanho, largura_max)
    while len(linhas) > 2 and tamanho > FONTE_CRITERIO_MIN:
        tamanho -= 0.5
        linhas = quebrar_linhas(texto, "Helvetica", tamanho, largura_max)
    linhas = linhas[:2]
    leading = tamanho * 1.15
    n = len(linhas)
    cy = (A4_H_MM - cy_topo_mm) * mm
    pdf.setFont("Helvetica", tamanho)
    for i, linha in enumerate(linhas):
        baseline = cy + (n - 1) * leading / 2 - i * leading
        pdf.drawString(x_mm * mm, baseline, linha)


def desenhar_nome_com_presenca(pdf: canvas.Canvas, texto: str, x_mm: float,
                               cy_topo_mm: float, largura_max_mm: float,
                               coords_out: list[dict], aluno_idx: int) -> None:
    """Nome do aluno no topo da linha + BALÃO CIRCULAR DE PRESENÇA AO LADO."""
    largura_max = largura_max_mm * mm
    tamanho = FONTE_NOME
    while stringWidth(texto, "Helvetica-Bold", tamanho) > largura_max and tamanho > 5.0:
        tamanho -= 0.5
    cy = (A4_H_MM - cy_topo_mm) * mm
    pdf.setFont("Helvetica-Bold", tamanho)
    pdf.drawString(x_mm * mm, cy - tamanho * 0.35, texto)
    largura_nome = stringWidth(texto, "Helvetica-Bold", tamanho) / mm
    chk_cx = x_mm + largura_nome + 3.0
    desenhar_balao(pdf, chk_cx, cy_topo_mm, PRES_RAIO)
    pdf.setFont("Helvetica", FONTE_PRESENCA)
    pdf.drawString((chk_cx + PRES_RAIO + 1.5) * mm, cy - FONTE_PRESENCA * 0.35,
                   "PRESENTE")
    coords_out.append({
        "aluno": aluno_idx, "tipo": "presenca",
        "x_mm": round(chk_cx, 2),
        "y_mm": round(cy_topo_mm, 2),
        "r_mm": PRES_RAIO,
    })


def desenhar_observacoes_rodape(pdf: canvas.Canvas, alunos: list[dict],
                                coords_out: list[dict]) -> None:
    """Observações no RODAPÉ: 3 blocos, um por aluno (BOM! / A MELHORAR).

    As CRUZES DE REFERÊNCIA do rodapé são GLOBAIS (2 cruzes na margem,
    x=5 e x=292, y=202, bloco 0) — desenhadas DEPOIS do loop de blocos,
    longe dos círculos e das linhas divisórias.
    """
    n_blocos = len(alunos)
    largura_total = A4_W_MM - 2 * MARGEM
    bloco_larg = (largura_total - (n_blocos - 1) * OBS_BLOCK_GAP) / n_blocos
    col_larg = bloco_larg / 2
    y_top = A4_H_MM - (FOOTER_Y0 + OBS_ITEM_Y0)
    y_bot = A4_H_MM - (FOOTER_Y0 + OBS_ITEM_Y0 + 5 * OBS_ITEM_ESPACO)
    for i, aluno in enumerate(alunos):
        bx = MARGEM + i * (bloco_larg + OBS_BLOCK_GAP)
        pdf.setFont("Helvetica-Bold", FONTE_OBS_TITULO)
        pdf.drawString(bx * mm, (A4_H_MM - (FOOTER_Y0 + OBS_BLOCK_Y)) * mm,
                       f"{aluno['id']} - {aluno['nome']} "
                       f"({aluno['faixa_atual'].capitalize()})")
        if i < n_blocos - 1:
            dx2 = bx + bloco_larg
            pdf.line(dx2 * mm, y_top * mm, dx2 * mm, y_bot * mm)
        for col, (titulo, itens, tipo) in enumerate([
                ("BOM!", OBS_P, "obs_p"), ("A MELHORAR", OBS_M, "obs_m")]):
            ox = bx + col * col_larg
            pdf.setFont("Helvetica-Bold", FONTE_OBS_TITULO)
            pdf.drawString(ox * mm, (A4_H_MM - (FOOTER_Y0 + OBS_COL_TITLE_Y)) * mm,
                           titulo)
            for oi, rotulo in enumerate(itens):
                oy = FOOTER_Y0 + OBS_ITEM_Y0 + oi * OBS_ITEM_ESPACO
                cx = ox + OBS_CHK_X_OFFSET
                desenhar_balao(pdf, cx, oy, OBS_RAIO)
                desenhar_texto_centralizado(pdf, rotulo,
                                            cx + OBS_TEXTO_GAP, oy, FONTE_OBS)
                coords_out.append({
                    "aluno": i + 1, "tipo": tipo, "indice": oi + 1,
                    "bloco": i + 1,
                    "x_mm": round(cx, 2),
                    "y_mm": round(oy, 2),
                    "r_mm": OBS_RAIO,
                })

    # CRUZES DE REFERÊNCIA DO RODAPÉ — 2 cruzes GLOBAIS na margem,
    # na altura do rodapé. Longe dos círculos e das linhas divisórias.
    desenhar_cruz(pdf, CRUZ_OBS_X_ESQ, CRUZ_OBS_Y, CRUZ_BRACO, CRUZ_ESPESSURA)
    coords_out.append({
        "tipo": "marcador_obs", "bloco": 0, "lado": "esq",
        "x_mm": round(CRUZ_OBS_X_ESQ, 2),
        "y_mm": round(CRUZ_OBS_Y, 2),
        "r_mm": CRUZ_BRACO,
    })
    desenhar_cruz(pdf, CRUZ_OBS_X_DIR, CRUZ_OBS_Y, CRUZ_BRACO, CRUZ_ESPESSURA)
    coords_out.append({
        "tipo": "marcador_obs", "bloco": 0, "lado": "dir",
        "x_mm": round(CRUZ_OBS_X_DIR, 2),
        "y_mm": round(CRUZ_OBS_Y, 2),
        "r_mm": CRUZ_BRACO,
    })


def desenhar_folha(pdf: canvas.Canvas, alunos: list[dict], avaliador_id: str,
                   dojo_id: str, exame_id: str, criterios: dict,
                   dojo_nome: str, avaliador_nome: str,
                   tmp_dir: Path, coords_out: list[dict]) -> None:
    """Desenha UMA página (folha) com até 3 alunos, no novo layout v5.5."""
    # --- Cabeçalho ---
    pdf.setFont("Helvetica-Bold", FONTE_TITULO)
    pdf.drawString(MARGEM * mm, (A4_H_MM - 14) * mm, "GABARITO DE AVALIACAO")
    pdf.setFont("Helvetica", FONTE_SUBTITULO)
    pdf.drawString(MARGEM * mm, (A4_H_MM - 22) * mm,
                   f"{dojo_nome} | Avaliador: {avaliador_nome} | Exame: {exame_id}")
    pdf.setFont("Helvetica-Oblique", FONTE_INSTRUCAO)
    pdf.drawString(MARGEM * mm, (A4_H_MM - 25) * mm,
                   "Instrução: preencha o círculo com caneta. "
                   "Observações: marque as opções que se aplicam.")

    # QR do exame (avaliador_id | dojo_id | exame_id) — canto superior direito
    desenhar_qr(pdf, f"KA|AVALIADOR={avaliador_id}|DOJO={dojo_id}|EXAME={exame_id}",
                QR_CAB_X, QR_CAB_Y, QR_CAB_TAM, tmp_dir,
                f"qr_cab_{avaliador_id}.png")

    # QR dos ALUNOS no CABEÇALHO — posição define a linha (1º=linha1, ...)
    for i, aluno in enumerate(alunos):
        if i >= len(QR_ALUNO_CAB_X):
            break
        desenhar_qr(pdf,
                    f"KA|ALUNO={aluno['id']}|FAIXA={normalizar_faixa(aluno['faixa_atual'])}",
                    QR_ALUNO_CAB_X[i], QR_ALUNO_CAB_Y, QR_ALUNO_CAB_TAM, tmp_dir,
                    f"qr_{aluno['id']}_{avaliador_id}.png")
        coords_out.append({
            "aluno": i + 1, "tipo": "qr_aluno",
            "x_mm": round(QR_ALUNO_CAB_X[i], 2),
            "y_mm": round(QR_ALUNO_CAB_Y + QR_ALUNO_CAB_TAM / 2, 2),
            "r_mm": QR_ALUNO_CAB_TAM / 2,
        })

    for i, aluno in enumerate(alunos):
        y0 = LINHA_Y0 + i * LINHA_H
        y1 = y0 + LINHA_H

        # Borda da linha do aluno
        pdf.rect(MARGEM * mm, (A4_H_MM - y1) * mm,
                 (A4_W_MM - 2 * MARGEM) * mm, LINHA_H * mm)

        # NOME + BALÃO CIRCULAR DE PRESENÇA AO LADO
        desenhar_nome_com_presenca(
            pdf,
            f"{aluno['id']} - {aluno['nome']} ({aluno['faixa_atual'].capitalize()})",
            NOME_X, y0 + NOME_Y, NOME_LARG, coords_out, i + 1)

        # CRUZES DE REFERÊNCIA DA LINHA — na margem, fora do conteúdo
        cruz_cy = y1 - CRUZ_Y_FIM
        desenhar_cruz(pdf, CRUZ_X_ESQ, cruz_cy, CRUZ_BRACO, CRUZ_ESPESSURA)
        coords_out.append({
            "aluno": i + 1, "tipo": "marcador", "lado": "esq",
            "x_mm": round(CRUZ_X_ESQ, 2), "y_mm": round(cruz_cy, 2),
            "r_mm": CRUZ_BRACO,
        })
        desenhar_cruz(pdf, CRUZ_X_DIR, cruz_cy, CRUZ_BRACO, CRUZ_ESPESSURA)
        coords_out.append({
            "aluno": i + 1, "tipo": "marcador", "lado": "dir",
            "x_mm": round(CRUZ_X_DIR, 2), "y_mm": round(cruz_cy, 2),
            "r_mm": CRUZ_BRACO,
        })

        # Blocos de quesito (4 colunas) — LARGURA TOTAL, textos por extenso
        for qi, quesito in enumerate(QUESITOS):
            bx = QUESITO_X0 + qi * QUESITO_LARG
            # Título do quesito: faixa cinza abaixo do nome, texto centralizado
            pdf.setFillColorRGB(0.82, 0.82, 0.82)
            pdf.rect(bx * mm, (A4_H_MM - (y0 + QUESITO_TITLE_Y0 + QUESITO_TITLE_H)) * mm,
                     QUESITO_LARG * mm, QUESITO_TITLE_H * mm, stroke=0, fill=1)
            pdf.setFillColorRGB(0, 0, 0)
            desenhar_texto_centralizado(pdf, NOME_QUESITO[quesito].upper(),
                                        bx + 2.0, y0 + QUESITO_TITLE_CY,
                                        FONTE_QUESITO, "Helvetica-Bold")
            for ci, nome_crit in enumerate(criterios[quesito]):
                cy = y0 + CRIT_Y0 + ci * CRIT_ESPACO
                desenhar_criterio(pdf, bx + TEXTO_CRIT_X, cy + 2.0,
                                  f"{ci + 1}. {nome_crit}",
                                  BALAO_X0 - TEXTO_CRIT_X - 1.0)
                for bi in range(BALOES_POR_CRITERIO):
                    cx = bx + BALAO_X0 + bi * BALAO_ESPACO
                    desenhar_balao(pdf, cx, cy + BALAO_Y_OFFSET, BALAO_RAIO)
                    coords_out.append({
                        "aluno": i + 1, "tipo": "criterio",
                        "quesito": quesito, "criterio": ci + 1, "balao": bi + 1,
                        "x_mm": round(cx, 2),
                        "y_mm": round(cy + BALAO_Y_OFFSET, 2),
                        "r_mm": BALAO_RAIO,
                    })

        # Linhas divisórias verticais (1px, nos vãos — fora dos balões)
        for qi in range(1, 4):
            dx = QUESITO_X0 + qi * QUESITO_LARG
            pdf.line(dx * mm, (A4_H_MM - y1 + 2) * mm,
                     dx * mm, (A4_H_MM - y0 - 2) * mm)

    # Observações no RODAPÉ (com cruzes globais na margem)
    desenhar_observacoes_rodape(pdf, alunos, coords_out)

    pdf.showPage()


# ---------------------------------------------------------------------------
# ORQUESTRAÇÃO
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pré-exame Karate-Ashi v5.5 (novo layout OMR, manifest-driven)")
    ap.add_argument("--exame", help="ID do exame no manifest (ex.: EXA-D01-2026-10)")
    ap.add_argument("--csv", type=Path, default=None,
                    help="CSV opcional com alunos novos do exame")
    ap.add_argument("--cadastro", type=Path,
                    default=Path("data/cadastro/alunos.json"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/pre_exame"))
    ap.add_argument("--dry-run", action="store_true",
                    help="apenas lista o plano, sem gravar cadastro nem PDFs")
    ap.add_argument("--validar", action="store_true",
                    help="valida o manifest sem gerar folhas")
    args = ap.parse_args()

    dojos = carregar_dojos(args.config)
    avaliadores = carregar_avaliadores(args.config)
    try:
        exames = carregar_manifest()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERRO] {exc}")
        return 2

    erros = validar_manifest(exames, dojos, avaliadores)
    if erros:
        print("[ERRO] Manifest inválido:")
        for e in erros:
            print(f"  - {e}")
        return 2

    if args.validar:
        print("[OK] Manifest válido: todos os exames, dojos e avaliadores conferem.")
        return 0

    if not args.exame:
        ap.error("Informe --exame (ou use --validar)")

    exame = next((e for e in exames if e["id"] == args.exame), None)
    if exame is None:
        print(f"[ERRO] Exame '{args.exame}' não encontrado no manifest.")
        return 2

    dojo_id = exame["dojo_id"]
    senseis = exame["avaliadores"]
    dojo_nome = _rotulo(dojo_id, dojos)

    if args.dry_run:
        print("=== DRY RUN — nenhum arquivo será gravado ===")
        print(f"Exame: {exame['id']} | Dojo: {dojo_nome} | Data: {exame['data_exame']}")
        print(f"Avaliadores: {', '.join(_rotulo(s, avaliadores) for s in senseis)}")
        if args.cadastro.exists():
            cadastro = json.loads(args.cadastro.read_text(encoding="utf-8"))
            do_dojo = [a for a in cadastro["alunos"] if a.get("dojo_id") == dojo_id]
            elegiveis = alunos_para_exame(do_dojo)
            print(f"Cadastro do dojo: {len(do_dojo)} alunos | "
                  f"elegíveis: {len(elegiveis)} -> "
                  f"{', '.join(a['id'] for a in elegiveis) or '-'}")
            for sensei in senseis:
                folhas = (len(elegiveis) + ALUNOS_POR_FOLHA - 1) // ALUNOS_POR_FOLHA
                print(f"PDF folhas_{sensei}.pdf: {folhas} folha(s) "
                      f"({len(elegiveis)} alunos)")
        return 0

    novos = []
    if args.csv:
        novos = atualizar_cadastro(args.csv, args.cadastro)
    todos = json.loads(args.cadastro.read_text(encoding="utf-8"))["alunos"]
    do_dojo = [a for a in todos if a.get("dojo_id") == dojo_id]
    elegiveis_ids = {a["id"] for a in alunos_para_exame(do_dojo)}
    alunos = [a for a in do_dojo if a["id"] in elegiveis_ids]
    pulados = [a["id"] for a in do_dojo if a["id"] not in elegiveis_ids]
    if pulados:
        print(f"[INFO] pulados (inativo ou sem faixa_pretendida): "
              f"{', '.join(pulados)}")
    if not alunos:
        print(f"[ERRO] nenhum aluno elegível no dojo {dojo_id} para o exame "
              f"{exame['id']}. Cadastre alunos em data/cadastro/alunos.json "
              f"com dojo_id={dojo_id} e faixa_pretendida preenchida.")
        return 2

    faixa_base = alunos[0]["faixa_atual"].lower()
    criterios = carregar_criterios(args.config, faixa_base)

    args.out.mkdir(parents=True, exist_ok=True)
    gerados = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for sensei in senseis:
            avaliador_nome = _rotulo(sensei, avaliadores)
            pdf = canvas.Canvas(str(args.out / f"folhas_{sensei}.pdf"),
                                pagesize=landscape(A4))
            for n, inicio in enumerate(range(0, len(alunos), ALUNOS_POR_FOLHA),
                                       start=1):
                grupo = alunos[inicio:inicio + ALUNOS_POR_FOLHA]
                coords: list[dict] = []
                desenhar_folha(pdf, grupo, sensei, dojo_id, exame["id"],
                               criterios, dojo_nome, avaliador_nome,
                               tmp_dir, coords)
                coord_path = args.out / f"{exame['id']}_{sensei}_folha{n}_coordenadas.json"
                coord_path.write_text(
                    json.dumps(coords, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                gerados += 1
            pdf.save()
            print(f"  [OK] folhas_{sensei}.pdf "
                  f"({(len(alunos) + ALUNOS_POR_FOLHA - 1) // ALUNOS_POR_FOLHA} folha(s))")

    print(f"Pré-exame {exame['id']} | Dojo {dojo_nome} | "
          f"{len(senseis)} avaliadores | {len(alunos)} alunos | "
          f"{gerados} folhas geradas em {args.out} | novos cadastrados: {len(novos)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())