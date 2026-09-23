"""diagnosticar_novo_layout.py — Diagnóstico e validação do NOVO layout de balões.

MUDANÇAS DA v18 (geometria sincronizada com o pre_exame v4.9):
- QR do exame REDUZIDO para 14mm (x=273, y=8).
- Cabeçalho 28mm, rodapé 40mm, LINHA_H = 47.33mm.
- Círculos de observação com espaçamento 4.0mm.
- Presença como balão circular (raio 1.8mm) ao lado do nome.
- QR dos alunos no cabeçalho (x=[195, 214, 233], y=8, 11mm).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# A4 PAISAGEM
A4_W_MM, A4_H_MM = 297.0, 210.0
SAIDA = Path("output/diagnostico_novo_layout")

# Identificação padrão (usada quando --exame não é informado)
EXAME_ID = "EXA-D01-2026-10"
DOJO_NOME = "Wolf"
AVALIADOR_ID = "S02"
AVALIADOR_NOME = "Sensei Fabio"

# Parâmetros do novo layout
N_ALUNOS = 3
BALOES_POR_CRITERIO = 5
QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

# Nomes dos critérios por quesito — TEXTO POR EXTENSO (sem abreviações)
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

# Alunos fictícios — FAIXA POR ALUNO (folha pode ser mista)
ALUNOS = [
    {"id": "T01", "nome": "Pedro Joao da Silva", "faixa": "Branca"},
    {"id": "T02", "nome": "Aline Roberta", "faixa": "Amarela"},
    {"id": "T03", "nome": "Jomiro da Silva", "faixa": "Laranja"},
]

# Observações — textos COMPLETOS na folha
OBS_P = ["Boa execucao dos Kihons", "Bom dominio do Kata", "Boa aplicacao do Bunkai",
         "Boa Conducao no Kumite", "Bom Dominio Tecnico", "Otimo Desempenho"]
OBS_M = ["Dificuldade nos Kihon", "Dificuldade no Kata", "Dificuldade no Bunkai",
         "Dificuldade nos Kumites", "Erros Tecnicos Constantes", "Nervosismo Constante"]

# Limiares de classificação (calibrados para caneta/lápis em 300 DPI)
LIMIAR_TAXA = 0.30    # fração de pixels escuros no interior do balão
LIMIAR_BLOB = 0.25    # fração do maior blob sobre o interior

# ---------------------------------------------------------------------------
# GEOMETRIA — SINCRONIZADA COM O pre_exame.py v4.9 (fonte única)
# ---------------------------------------------------------------------------
MARGEM = 10.0
HEADER_H = 28.0                       # cabeçalho (compacto)
FOOTER_H = 40.0                       # rodapé de observações (ampliado)
LINHA_Y0 = HEADER_H
LINHA_H = (A4_H_MM - HEADER_H - FOOTER_H) / N_ALUNOS  # (210-28-40)/3 = 47.33mm
FOOTER_Y0 = LINHA_Y0 + 3 * LINHA_H    # 170mm

# QR do exame (canto superior direito) — REDUZIDO para 14mm (v4.9)
QR_CAB_X = A4_W_MM - MARGEM - 14.0    # 273mm
QR_CAB_Y = 8.0
QR_CAB_TAM = 14.0

# QR dos ALUNOS no CABEÇALHO — posição define a linha (QR i -> linha i+1)
QR_ALUNO_CAB_X = [195.0, 214.0, 233.0]
QR_ALUNO_CAB_Y = 8.0
QR_ALUNO_CAB_TAM = 11.0

# Linha do aluno — NOME + BALÃO CIRCULAR DE PRESENÇA AO LADO
NOME_X = 10.0
NOME_Y = 2.0                          # topo da linha
NOME_LARG = 150.0                     # limite do nome (balão logo após)
PRES_RAIO = 1.8                       # balão circular de presença (raio 1.8mm)

# Blocos de quesito (4 colunas) — LARGURA TOTAL (69mm cada)
QUESITO_X0 = 10.0
QUESITO_LARG = 69.0                   # 10 a 286mm
QUESITO_TITLE_Y0 = 5.0                # topo da faixa cinza
QUESITO_TITLE_H = 3.0                 # altura da faixa cinza
QUESITO_TITLE_CY = 6.5                # centro do texto na faixa
CRIT_Y0 = 9.5                         # primeira linha de critério
CRIT_ESPACO = 4.6                     # espaçamento entre critérios
TEXTO_CRIT_X = 1.0
BALAO_X0 = 40.0                       # área de texto ~39mm
BALAO_ESPACO = 5.0
BALAO_RAIO = 1.8
BALAO_Y_OFFSET = 1.2                  # alinhamento do balão com o centro visual do texto

# Observações — RODAPÉ (v18): círculos com folga (espaçamento 4.0)
OBS_BLOCK_Y = 3.0                     # rótulo do aluno (abaixado, longe da borda)
OBS_COL_TITLE_Y = 5.5                 # título "BOM!" / "A MELHORAR"
OBS_BLOCK_GAP = 2.0                   # vão entre blocos
OBS_ITEM_Y0 = 8.0                     # primeiro item
OBS_ITEM_ESPACO = 4.0                 # espaçamento (folga entre círculos)
OBS_RAIO = 1.5                        # círculo de observação
OBS_CHK_X_OFFSET = 3.5                # círculo a 3,5mm da borda do bloco
OBS_TEXTO_GAP = 3.0                   # texto após o círculo


def mm_para_px(mm: float, dpi: float) -> int:
    return int(round(mm * dpi / 25.4))


def desenhar_texto_centralizado(img, texto, x, y_centro, escala,
                                cor=(0, 0, 0), espessura=1):
    """Desenha texto com o CENTRO VERTICAL alinhado a y_centro."""
    (_, alt), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, espessura)
    cv2.putText(img, texto, (x, y_centro + alt // 2),
                cv2.FONT_HERSHEY_SIMPLEX, escala, cor, espessura)


def desenhar_nome_com_presenca(img, texto, x, y_centro, escala, largura_max_mm,
                               dpi, pres_raio_px, coords_out, aluno_idx):
    """Nome no topo da linha + BALÃO CIRCULAR DE PRESENÇA AO LADO."""
    largura_max = mm_para_px(largura_max_mm, dpi)
    (larg, alt), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, 1)
    while larg > largura_max and escala > 0.35:
        escala -= 0.05
        (larg, alt), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, escala, 1)
    cv2.putText(img, texto, (x, y_centro + alt // 2),
                cv2.FONT_HERSHEY_SIMPLEX, escala, (0, 0, 0), 1)
    # Balão circular logo após o nome, na mesma linha
    chk_cx = x + larg + mm_para_px(3.0, dpi)
    desenhar_balao(img, chk_cx, y_centro, pres_raio_px)
    cv2.putText(img, "PRESENTE",
                (chk_cx + pres_raio_px + mm_para_px(1.5, dpi), y_centro + alt // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0, 0, 0), 1)
    cx_mm = chk_cx / dpi * 25.4
    cy_mm = y_centro / dpi * 25.4
    coords_out.append({
        "aluno": aluno_idx, "tipo": "presenca",
        "x_mm": round(cx_mm, 2),
        "y_mm": round(cy_mm, 2),
        "r_mm": PRES_RAIO,
    })


def gerar_qr(dados: str, tamanho_px: int) -> np.ndarray:
    """Gera um QR code como array numpy (placeholder se a lib não existir)."""
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=4, border=1)
        qr.add_data(dados)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("L")
        arr = np.array(img, dtype=np.uint8)
        return cv2.resize(arr, (tamanho_px, tamanho_px), interpolation=cv2.INTER_NEAREST)
    except ImportError:
        ph = np.full((tamanho_px, tamanho_px), 255, dtype=np.uint8)
        cv2.rectangle(ph, (0, 0), (tamanho_px - 1, tamanho_px - 1), 0, 2)
        cv2.putText(ph, "QR", (tamanho_px // 5, tamanho_px // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
        return ph


def desenhar_balao(img, cx, cy, raio, cor=(0, 0, 0), espessura=1):
    """Desenha um balão oval (elipse) centrado em (cx, cy)."""
    cv2.ellipse(img, (cx, cy), (raio, raio), 0, 0, 360, cor, espessura)


def renderizar_pdf(caminho_pdf: Path, dpi: int = 300) -> np.ndarray:
    """Renderiza a 1ª página do PDF em imagem (mesmo DPI das coordenadas)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("[ERRO] pypdfium2 nao instalado. Rode: pip install pypdfium2")
        raise
    pdf = pdfium.PdfDocument(str(caminho_pdf))
    pagina = pdf[0]
    escala = dpi / 72.0          # PDF usa 72 DPI como base
    bitmap = pagina.render(scale=escala)
    return np.array(bitmap.to_pil().convert("RGB"))


def carregar_contexto_exame(exame_id: str | None):
    """Carrega dojo/avaliador/alunos reais do manifest (se --exame informado)."""
    if not exame_id:
        return EXAME_ID, DOJO_NOME, AVALIADOR_ID, AVALIADOR_NOME, ALUNOS
    try:
        manifest = json.loads((RAIZ / "data" / "exames.json").read_text(encoding="utf-8"))
        dojos = json.loads((RAIZ / "config" / "dojos.json").read_text(encoding="utf-8"))
        avaliadores = json.loads((RAIZ / "config" / "avaliadores.json").read_text(encoding="utf-8"))
        exame = next(e for e in manifest["exames"] if e["id"] == exame_id)
        dojo = next(d for d in dojos["dojos"] if d["id"] == exame["dojo_id"])
        av_id = exame["avaliadores"][0]
        av = next(a for a in avaliadores["avaliadores"] if a["id"] == av_id)
        cadastro = json.loads((RAIZ / "data" / "cadastro" / "alunos.json").read_text(encoding="utf-8"))
        alunos = [{"id": a["id"], "nome": a["nome"],
                   "faixa": a.get("faixa_atual", "Branca")}
                  for a in cadastro["alunos"]
                  if a.get("dojo_id") == exame["dojo_id"]][:N_ALUNOS]
        if not alunos:
            alunos = ALUNOS  # fallback para os fictícios
        return exame_id, dojo["nome"], av_id, av["nome"], alunos
    except Exception as exc:
        print(f"[AVISO] nao foi possivel carregar o contexto do exame ({exc}); "
              f"usando padroes de teste.")
        return EXAME_ID, DOJO_NOME, AVALIADOR_ID, AVALIADOR_NOME, ALUNOS


def gerar_folha_teste(dpi: int = 300, exame_id: str | None = None) -> Path:
    """Gera a folha de teste do novo layout + coordenadas dos balões."""
    exame_id, dojo_nome, av_id, av_nome, alunos = carregar_contexto_exame(exame_id)

    largura = mm_para_px(A4_W_MM, dpi)
    altura = mm_para_px(A4_H_MM, dpi)
    folha = np.full((altura, largura), 255, dtype=np.uint8)
    margem = mm_para_px(MARGEM, dpi)

    # --- Cabeçalho ---
    cv2.putText(folha, "GABARITO DE AVALIACAO",
                (margem, mm_para_px(14, dpi)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    cv2.putText(folha, f"{dojo_nome} | Avaliador: {av_nome} | Exame: {exame_id}",
                (margem, mm_para_px(22, dpi)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 0, 1)
    cv2.putText(folha, "Instrucao: preencha o circulo com caneta. Observacoes: marque as opcoes que se aplicam.",
                (margem, mm_para_px(25, dpi)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1)

    # QR do exame (avaliador_id | dojo_id | exame_id)
    qr_tam = mm_para_px(QR_CAB_TAM, dpi)
    qr_x = mm_para_px(QR_CAB_X, dpi)
    qr_y = mm_para_px(QR_CAB_Y, dpi)
    folha[qr_y:qr_y + qr_tam, qr_x:qr_x + qr_tam] = gerar_qr(
        f"KA|AVALIADOR={av_id}|DOJO={exame_id.split('-')[1]}|EXAME={exame_id}", qr_tam)

    # QR dos ALUNOS no CABEÇALHO — posição define a linha (QR i -> linha i+1)
    qr_aluno_tam = mm_para_px(QR_ALUNO_CAB_TAM, dpi)
    for i, aluno in enumerate(alunos):
        if i >= len(QR_ALUNO_CAB_X):
            break
        qa_x = mm_para_px(QR_ALUNO_CAB_X[i], dpi)
        qa_y = mm_para_px(QR_ALUNO_CAB_Y, dpi)
        folha[qa_y:qa_y + qr_aluno_tam, qa_x:qa_x + qr_aluno_tam] = gerar_qr(
            f"KA|ALUNO={aluno['id']}|FAIXA={aluno['faixa'].upper()}", qr_aluno_tam)

    baloes = []
    linha_h = mm_para_px(LINHA_H, dpi)
    linha_y0 = mm_para_px(LINHA_Y0, dpi)

    for i, aluno in enumerate(alunos):
        y0 = linha_y0 + i * linha_h
        y1 = y0 + linha_h
        cv2.rectangle(folha, (margem, y0), (largura - margem, y1), 0, 1)

        # NOME + BALÃO CIRCULAR DE PRESENÇA AO LADO
        y_centro = y0 + mm_para_px(NOME_Y + PRES_RAIO, dpi)
        desenhar_nome_com_presenca(
            folha,
            f"{aluno['id']} - {aluno['nome']} ({aluno['faixa']})",
            mm_para_px(NOME_X, dpi), y_centro, 0.45, NOME_LARG, dpi,
            mm_para_px(PRES_RAIO, dpi), baloes, i + 1)

        # Blocos de quesito (4 colunas) — LARGURA TOTAL, textos por extenso
        bloco_x0 = mm_para_px(QUESITO_X0, dpi)
        bloco_larg = mm_para_px(QUESITO_LARG, dpi)
        for qi, quesito in enumerate(QUESITOS):
            bx = bloco_x0 + qi * bloco_larg
            # Título do quesito: fundo cinza + texto centralizado
            cv2.rectangle(folha, (bx, y0 + mm_para_px(QUESITO_TITLE_Y0, dpi)),
                          (bx + bloco_larg, y0 + mm_para_px(QUESITO_TITLE_Y0 + QUESITO_TITLE_H, dpi)), 210, -1)
            desenhar_texto_centralizado(folha, quesito.upper(),
                                        bx + mm_para_px(2, dpi),
                                        y0 + mm_para_px(QUESITO_TITLE_CY, dpi),
                                        0.38, espessura=2)
            for ci, nome_crit in enumerate(CRITERIOS[quesito]):
                cy = y0 + mm_para_px(CRIT_Y0, dpi) + ci * mm_para_px(CRIT_ESPACO, dpi)
                desenhar_texto_centralizado(folha, f"{ci + 1}. {nome_crit}",
                                            bx + mm_para_px(TEXTO_CRIT_X, dpi),
                                            cy + mm_para_px(2, dpi), 0.4)
                for bi in range(BALOES_POR_CRITERIO):
                    cx = bx + mm_para_px(BALAO_X0, dpi) + bi * mm_para_px(BALAO_ESPACO, dpi)
                    desenhar_balao(folha, cx, cy + mm_para_px(BALAO_Y_OFFSET, dpi),
                                   mm_para_px(BALAO_RAIO, dpi))
                    baloes.append({
                        "aluno": i + 1, "tipo": "criterio",
                        "quesito": quesito, "criterio": ci + 1, "balao": bi + 1,
                        "x_mm": round(QUESITO_X0 + qi * QUESITO_LARG
                                      + BALAO_X0 + bi * BALAO_ESPACO, 2),
                        "y_mm": round(LINHA_Y0 + i * LINHA_H
                                      + CRIT_Y0 + ci * CRIT_ESPACO + BALAO_Y_OFFSET, 2),
                        "r_mm": BALAO_RAIO,
                    })

        # Linhas divisórias verticais (1px, nos vãos — fora dos balões)
        for qi in range(1, 4):
            dx = bloco_x0 + qi * bloco_larg
            cv2.line(folha, (dx, y0 + mm_para_px(2, dpi)),
                     (dx, y1 - mm_para_px(2, dpi)), 0, 1)

    # Observações no RODAPÉ (v18) — 3 blocos, um por aluno
    n_blocos = len(alunos)
    largura_total = A4_W_MM - 2 * MARGEM
    bloco_larg = (largura_total - (n_blocos - 1) * OBS_BLOCK_GAP) / n_blocos
    col_larg = bloco_larg / 2
    footer_y0_px = mm_para_px(FOOTER_Y0, dpi)
    # Altura da divisória: do primeiro ao último item de observação
    y_top = footer_y0_px + mm_para_px(OBS_ITEM_Y0, dpi)
    y_bot = footer_y0_px + mm_para_px(OBS_ITEM_Y0 + 5 * OBS_ITEM_ESPACO, dpi)
    for i, aluno in enumerate(alunos):
        bx = MARGEM + i * (bloco_larg + OBS_BLOCK_GAP)
        # Rótulo do aluno no topo do bloco (abaixado, longe da borda)
        cv2.putText(folha, f"{aluno['id']} - {aluno['nome']} ({aluno['faixa']})",
                    (mm_para_px(bx, dpi),
                     footer_y0_px + mm_para_px(OBS_BLOCK_Y + 3, dpi)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, 0, 1)
        # Divisória entre alunos (borda direita do bloco, exceto o último)
        if i < n_blocos - 1:
            dx2 = mm_para_px(bx + bloco_larg, dpi)
            cv2.line(folha, (dx2, y_top), (dx2, y_bot), 0, 1)
        for col, (titulo, itens, tipo) in enumerate([
                ("BOM!", OBS_P, "obs_p"), ("A MELHORAR", OBS_M, "obs_m")]):
            ox = bx + col * col_larg
            cv2.putText(folha, titulo,
                        (mm_para_px(ox, dpi),
                         footer_y0_px + mm_para_px(OBS_COL_TITLE_Y + 3, dpi)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, 0, 1)
            for oi, rotulo in enumerate(itens):
                oy = FOOTER_Y0 + OBS_ITEM_Y0 + oi * OBS_ITEM_ESPACO
                cx = ox + OBS_CHK_X_OFFSET
                desenhar_balao(folha, mm_para_px(cx, dpi), mm_para_px(oy, dpi),
                               mm_para_px(OBS_RAIO, dpi))
                desenhar_texto_centralizado(folha, rotulo,
                                            mm_para_px(cx + OBS_TEXTO_GAP, dpi),
                                            mm_para_px(oy, dpi), 0.3)
                baloes.append({
                    "aluno": i + 1, "tipo": tipo, "indice": oi + 1,
                    "x_mm": round(cx, 2),
                    "y_mm": round(oy, 2),
                    "r_mm": OBS_RAIO,
                })

    SAIDA.mkdir(parents=True, exist_ok=True)
    caminho = SAIDA / "novo_layout_teste.png"
    cv2.imwrite(str(caminho), folha)
    coord_path = SAIDA / "novo_layout_coordenadas.json"
    coord_path.write_text(json.dumps(baloes, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"Folha de teste gerada: {caminho} ({largura}x{altura} px, {dpi} DPI)")
    print(f"Coordenadas dos baloes: {coord_path} ({len(baloes)} baloes)")
    print("Imprima em A4 paisagem, preencha os baloes a mao e digitalize.")
    return caminho


def ler_qr(imagem, box_mm, dpi_x, dpi_y):
    """Lê o QR code numa região definida em mm."""
    x = mm_para_px(box_mm["x"], dpi_x)
    y = mm_para_px(box_mm["y"], dpi_y)
    w = mm_para_px(box_mm["w"], dpi_x)
    h = mm_para_px(box_mm["h"], dpi_y)
    regiao = imagem[y:y + h, x:x + w]
    if regiao.size == 0:
        return None
    detector = cv2.QRCodeDetector()
    dados, _, _ = detector.detectAndDecode(regiao)
    return dados.strip() if dados else None


def nome_do_aluno(qr_dados, alunos):
    """Cruza o QR do aluno com a lista de alunos para exibir nome e faixa."""
    if not qr_dados:
        return None
    for aluno in alunos:
        if f"ALUNO={aluno['id']}" in qr_dados:
            return f"{aluno['nome']} ({aluno['faixa']})"
    return None


def medir_balao_por_coordenada(img, x_mm, y_mm, r_mm, dpi_x, dpi_y):
    """Mede escuridão adaptativa + conectividade do INTERIOR do balão.
    Usa recuo de 20% — a borda do balão (e linhas adjacentes) ficam FORA
    da área medida, evitando falsos positivos.
    """
    cx = int(x_mm * dpi_x / 25.4)
    cy = int(y_mm * dpi_y / 25.4)
    r = max(1, int(r_mm * dpi_x / 25.4))
    recuo = max(1, int(r * 0.2))
    x0, y0 = max(0, cx - r + recuo), max(0, cy - r + recuo)
    x1, y1 = cx + r - recuo, cy + r - recuo
    if x1 <= x0 or y1 <= y0:
        return {"taxa_escuros": 0.0, "fracao_blob": 0.0, "fora_da_imagem": True}
    interior = img[y0:y1, x0:x1]
    if interior.size == 0:
        return {"taxa_escuros": 0.0, "fracao_blob": 0.0, "fora_da_imagem": True}
    cinza = cv2.cvtColor(interior, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    escuros = binaria == 0
    taxa = float(escuros.mean())
    num, _, stats, _ = cv2.connectedComponentsWithStats(
        escuros.astype(np.uint8), connectivity=8)
    maior = 0
    if num > 1:
        maior = int(stats[1:, cv2.CC_STAT_AREA].max())
    fracao_blob = maior / escuros.size if escuros.size else 0.0
    return {"taxa_escuros": round(taxa, 3), "fracao_blob": round(fracao_blob, 3),
            "fora_da_imagem": False}


def classificar(medida):
    """Classifica o balão: marcado / vazio / suspeito / erro."""
    if medida is None or medida.get("fora_da_imagem"):
        return "erro"
    if medida["taxa_escuros"] >= LIMIAR_TAXA and medida["fracao_blob"] >= LIMIAR_BLOB:
        return "marcado"
    if medida["taxa_escuros"] < 0.15 and medida["fracao_blob"] < 0.08:
        return "vazio"
    return "suspeito"


def diagnosticar_folha(caminho_imagem: Path, coord_path: Path | None = None) -> int:
    """Processa a folha (PDF ou PNG) usando as coordenadas conhecidas."""
    if caminho_imagem.suffix.lower() == ".pdf":
        img = renderizar_pdf(caminho_imagem, dpi=300)
    else:
        img = cv2.imread(str(caminho_imagem))
    if img is None:
        print(f"[ERRO] nao conseguiu abrir {caminho_imagem}")
        return 2
    altura, largura = img.shape[:2]
    dpi_x = largura / (A4_W_MM / 25.4)
    dpi_y = altura / (A4_H_MM / 25.4)
    print(f"Folha: {caminho_imagem.name} ({largura}x{altura}, ~{dpi_x:.0f} DPI)")

    if coord_path is None:
        coord_path = SAIDA / "novo_layout_coordenadas.json"
    if not coord_path.exists():
        print(f"[ERRO] coordenadas nao encontradas: {coord_path}")
        print("Rode primeiro: python tools/diagnosticar_novo_layout.py gerar-teste")
        return 2
    baloes = json.loads(coord_path.read_text(encoding="utf-8"))
    _, _, _, _, alunos = carregar_contexto_exame(None)

    # 1. QR do exame (canto superior direito, em mm)
    cabecalho = {"x": QR_CAB_X - 2.0, "y": QR_CAB_Y - 3.0,
                 "w": QR_CAB_TAM + 10.0, "h": QR_CAB_TAM + 10.0}
    qr_cab = ler_qr(img, cabecalho, dpi_x, dpi_y)
    print(f"QR exame: {qr_cab or 'nao detectado'}")

    # 2. QR dos ALUNOS no CABEÇALHO — posição define a linha (QR i -> linha i+1)
    qr_alunos = []
    for j in range(N_ALUNOS):
        box = {"x": QR_ALUNO_CAB_X[j], "y": QR_ALUNO_CAB_Y,
               "w": QR_ALUNO_CAB_TAM, "h": QR_ALUNO_CAB_TAM}
        qr_alunos.append(ler_qr(img, box, dpi_x, dpi_y))

    vis = img.copy()
    relatorio = {"cabecalho_qr": qr_cab, "linhas": []}
    total = {"marcado": 0, "suspeito": 0, "vazio": 0, "erro": 0, "ausente": 0}

    for i in range(N_ALUNOS):
        qr_aluno = qr_alunos[i]
        nome = nome_do_aluno(qr_aluno, alunos)

        baloes_aluno = [b for b in baloes if b["aluno"] == i + 1]
        cont = {"marcado": 0, "suspeito": 0, "vazio": 0, "erro": 0}
        detalhes = []
        presenca = None

        for b in baloes_aluno:
            # QR do aluno no cabeçalho: não é balão a medir (lido via ler_qr)
            if b["tipo"] == "qr_aluno":
                continue

            medida = medir_balao_por_coordenada(
                img, b["x_mm"], b["y_mm"], b["r_mm"], dpi_x, dpi_y)
            status = classificar(medida)

            # Balão de presença: status próprio (marcado = presente)
            if b["tipo"] == "presenca":
                presenca = (status == "marcado")
                cor = (0, 200, 0) if presenca else (0, 0, 255)
                cx = int(b["x_mm"] * dpi_x / 25.4)
                cy = int(b["y_mm"] * dpi_y / 25.4)
                r = int(b["r_mm"] * dpi_x / 25.4)
                cv2.circle(vis, (cx, cy), r, cor, 2)
                detalhes.append({
                    "tipo": "presenca",
                    "x_mm": b["x_mm"], "y_mm": b["y_mm"],
                    "status": "presente" if presenca else "ausente",
                    **medida,
                })
                continue

            cont[status] += 1
            total[status] += 1
            cor = {"marcado": (0, 200, 0), "suspeito": (0, 0, 255),
                   "vazio": (255, 0, 0), "erro": (0, 255, 255)}[status]
            cx = int(b["x_mm"] * dpi_x / 25.4)
            cy = int(b["y_mm"] * dpi_y / 25.4)
            r = int(b["r_mm"] * dpi_x / 25.4)
            cv2.circle(vis, (cx, cy), r, cor, 2)
            detalhes.append({
                "tipo": b["tipo"],
                "quesito": b.get("quesito"),
                "criterio": b.get("criterio"),
                "balao": b.get("balao"),
                "indice": b.get("indice"),
                "x_mm": b["x_mm"], "y_mm": b["y_mm"],
                "status": status,
                **medida,
            })

        # Lógica de presença: ausente = não avaliado (sem nota)
        if presenca is False:
            total["ausente"] += 1
            situacao = "AUSENTE (nao avaliado)"
        elif presenca is True:
            situacao = "presente"
        else:
            situacao = "presenca nao detectada"

        print(f"Linha {i+1}: QR aluno={qr_aluno or 'nao detectado'} "
              f"({nome or '?'}) | presenca={situacao} | "
              f"{cont['marcado']} marcados | {cont['suspeito']} suspeitos | "
              f"{cont['vazio']} vazios | {cont['erro']} erros | "
              f"{len(baloes_aluno)} baloes")
        relatorio["linhas"].append({
            "aluno_qr": qr_aluno,
            "aluno_nome": nome,
            "presenca": situacao,
            "baloes": len(baloes_aluno),
            "marcados": cont["marcado"],
            "suspeitos": cont["suspeito"],
            "vazios": cont["vazio"],
            "erros": cont["erro"],
            "detalhes": detalhes,
        })

    SAIDA.mkdir(parents=True, exist_ok=True)
    vis_path = SAIDA / f"{caminho_imagem.stem}_diagnostico.png"
    cv2.imwrite(str(vis_path), vis)
    rel_path = SAIDA / f"{caminho_imagem.stem}_relatorio.json"
    rel_path.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"\nTOTAL: {total['marcado']} marcados | {total['suspeito']} suspeitos | "
          f"{total['vazio']} vazios | {total['erro']} erros | "
          f"{total['ausente']} ausentes")
    print(f"Diagnostico visual: {vis_path}")
    print(f"Relatorio: {rel_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnostico do novo layout de baloes")
    sub = ap.add_subparsers(dest="comando", required=True)

    p_gerar = sub.add_parser("gerar-teste", help="Gera a folha de teste do novo layout")
    p_gerar.add_argument("--dpi", type=int, default=300)
    p_gerar.add_argument("--exame", default=None,
                         help="ID do exame no manifest (carrega dados reais)")

    p_diag = sub.add_parser("diagnosticar", help="Diagnostica uma folha (PDF ou PNG)")
    p_diag.add_argument("--imagem", type=Path, required=True)
    p_diag.add_argument("--coordenadas", type=Path, default=None,
                        help="JSON de coordenadas exportado pelo pre_exame "
                             "(EXA-..._folhaN_coordenadas.json)")

    args = ap.parse_args()

    if args.comando == "gerar-teste":
        gerar_folha_teste(args.dpi, args.exame)
        return 0
    if args.comando == "diagnosticar":
        return diagnosticar_folha(args.imagem, args.coordenadas)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())