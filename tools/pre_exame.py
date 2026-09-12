"""tools/pre_exame.py — Gera folhas PDF com QR Code (multi-faixa).

Uso:
    python tools/pre_exame.py --csv data/alunos_exame.csv \
        --dojo D01 --exame EXA-D01-2026-02 --senseis S01,S02,S03 \
        --cadastro data/cadastro/alunos.json --out output/pre_exame/

Fluxo:
1. lê o CSV (alunos com faixa atual e pretendida);
2. merge idempotente no cadastro (novos com "novo": true);
3. para cada avaliador x aluno, desenha a folha usando o layout da faixa;
4. gera o QR Code com o payload padrão e salva o PDF;
5. GRAVA config/coordenadas/<faixa>.json com a posição real de cada linha
   de checkboxes e de cada checkbox de observação estruturada (em mm),
   para o OMR (Fase 03) ler a MESMA geometria que a folha usa.

Layout: folha A4 em DUAS COLUNAS, distribuída pela página inteira.
Esquerda: Kihon + Kata | Direita: Bunkai + Kumite
Cada quesito mantém seus critérios com 7 checkboxes.

Observações estruturadas (v2col-2.8):
- A observação do avaliador nasce na FOLHA como checkboxes, uniformes para
  todas as faixas: coluna 'Ótimo!' (obs_p1..p8) e coluna 'A Melhorar'
  (obs_m1..m8). SEM limite de marcações: o avaliador marca as opções que
  se aplicam; o OMR lê cada checkbox de forma independente e o relatório
  concatena tudo.
- SEM campo 'Outro': a observação é 100% estruturada — nenhuma transcrição
  manual entra no fluxo.
- Substitui as caixas de escrita livre por quesito e o CSV digitado ao
  final: o OMR lê as marcações na mesma passada dos códigos de erro.
- ICR (manuscrito) descartado por acurácia.
- Alinhamento: o baseline do texto é deslocado -0.35*tamanho (pt), de modo
  que o centro visual do texto (baseline + 0.35*tamanho) coincide com o
  centro do checkbox — texto e quadrado na MESMA linha de centro.
- Espaçamento: respiro de 10mm entre o título da seção e os cabeçalhos
  'Ótimo!'/'A Melhorar', e 6mm entre o cabeçalho e a primeira opção.

v2col-2.4 (mantido):
- QR desenhado POR ÚLTIMO no canto superior direito (nada cobre);
- sem estampa de versão na folha;
- entrelinha 8,5mm, quesito 12pt, critério 9pt — os blocos de quesitos
  terminam ~93mm acima da base; a seção de observações estruturadas
  ocupa o rodapé.

IMPORTANTE: a geometria de desenho é FIXA no código (constantes abaixo).
O config/coordenadas/<faixa>.json é apenas SAÍDA (registra o que foi
desenhado) — nunca é lido como configuração de desenho.

Nota: os CSVs de entrada são lidos com encoding="utf-8-sig", que aceita
arquivos com ou sem BOM (Excel/PowerShell 5.1 gravam com BOM).

Dependências: qrcode[pil], reportlab.
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
import unicodedata
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOME_QUESITO = {"kihon": "Kihon", "kata": "Kata",
                "bunkai": "Bunkai", "kumite": "Kumite"}

# Dimensões A4 em mm — base do sistema de coordenadas gravado para o OMR.
LARGURA_A4_MM = 210.0
ALTURA_A4_MM = 297.0

# Layout de duas colunas (x em mm a partir da borda esquerda).
COLUNAS = [
    ("esquerda", 15.0, ["kihon", "kata"]),
    ("direita", 107.0, ["bunkai", "kumite"]),
]
COL_LARGURA_MM = 88.0

# Geometria dos checkboxes (dentro da coluna) — FIXA.
CHECKBOX_X_OFFSET_MM = 46.0   # do início da coluna até o 1º checkbox
CHECKBOX_PASSO_MM = 5.5
CHECKBOX_LADO_MM = 4.0
CHECKBOX_QTD = 7

# Observações estruturadas — UNIFORMES para todas as faixas (v2col-2.8).
# Substituem as caixas de escrita livre por quesito: o avaliador marca
# opções e o OMR lê as marcações na mesma passada dos códigos de erro.
# SEM campo 'Outro' — a observação é 100% estruturada.
OBS_POSITIVAS = [
    "Boa execução técnica",
    "Ótima base / postura",
    "Chutes firmes",
    "Boa concentração / foco",
    "Bom controle e defesa",
    "Combate técnico / ágil",
    "Ótima Execução do Kata",
    "Ótima execução de Kihons",
]
OBS_MELHORAR = [
    "Melhorar bases / postura",
    "Dificuldade nas Transiçoes de Bases",
    "Falta kiai (usar mais o kiai)",
    "Falta foco / olhar nas técnicas",
    "Mais carga nos golpes",
    "Erros Técnicos Constantes",
    "Execução Incorreta do Kata",
    "Dificuldade na execução de Kihons",
]
OBS_COL_X_MM = [15.0, 107.0]   # x das colunas da seção (mm)
OBS_CHK_LADO_MM = 4.5          # checkbox da seção (um pouco maior p/ OMR)
OBS_LINHA_MM = 6.5             # altura de linha da seção
OBS_TEXTO_X_OFFSET_MM = 7.0    # texto após o checkbox

# QR Code — canto superior direito (desenhado por último, nada cobre).
QR_LADO_MM = 22.0
QR_MARGEM_MM = 10.0

# Tipografia
FONTE_TITULO = 13
FONTE_QUESITO = 12
FONTE_CRITERIO = 9
FONTE_CRITERIO_MIN = 7   # limite inferior do ajuste automático
FONTE_OBS = 9            # texto das opções de observação
FONTE_DADO = 10
FONTE_RODAPE = 9
LINHA_MM = 8.5           # entrelinha dos critérios (distribui pela página)
MAX_CRITERIOS_BLOCO = 8  # reserva fixa por bloco — alinha as colunas
ESPACO_TITULO_MM = 7.0   # espaço após o título do quesito
GAP_TEXTO_CHECKBOX_MM = 2.0  # folga mínima entre texto e checkboxes
GAP_APOS_BLOCO_MM = 8.0  # respiro após o bloco do quesito

RODAPE_TEXTO = ("Como marcar: preencha TOTALMENTE o quadrado (caneta preta "
                "ou lápis 2B), da esquerda para a direita, sem pular "
                "caixas. Deixe em branco para zero falhas.")
RODAPE_MARGEM_MM = 15.0
RODAPE_BASE_MM = 10.0

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def normalizar_faixa(faixa: str) -> str:
    """Remove acentos e normaliza para uppercase (payload QR sem acentos)."""
    sem_acentos = unicodedata.normalize("NFKD", faixa)
    ascii_only = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return ascii_only.upper().strip()

def montar_payload(dojo: str, exame: str, aluno_id: str,
                   sensei_id: str, faixa: str) -> str:
    """KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA — sem acentos, com pipes."""
    return "|".join(["KA", dojo, exame, aluno_id, sensei_id, normalizar_faixa(faixa)])

def atualizar_cadastro(csv_path: Path, cadastro_path: Path) -> list[dict]:
    """Merge idempotente do CSV no alunos.json."""
    cadastro = (json.loads(cadastro_path.read_text(encoding="utf-8"))
                if cadastro_path.exists() else {"alunos": []})
    por_id = {a["id"]: a for a in cadastro["alunos"]}
    novos = []
    with open(csv_path, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            aluno_id = row["id"]
            if aluno_id not in por_id:
                aluno = {**row, "novo": True}
                cadastro["alunos"].append(aluno)
                por_id[aluno_id] = aluno
                novos.append(aluno)
            else:
                for campo in ("faixa_atual", "faixa_pretendida", "dojo_id"):
                    if row.get(campo):
                        por_id[aluno_id][campo] = row[campo]
    cadastro_path.parent.mkdir(parents=True, exist_ok=True)
    cadastro_path.write_text(json.dumps(cadastro, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return novos

def carregar_coordenadas(config_dir: Path, faixa: str) -> dict:
    """Carrega config/coordenadas/<faixa>.json se existir (apenas para
    compatibilidade da assinatura; a geometria de desenho é fixa no código)."""
    caminho = config_dir / "coordenadas" / f"{faixa}.json"
    if caminho.exists():
        return carregar_json(caminho)
    return {}

def salvar_coordenadas(config_dir: Path, faixa: str, coords: dict) -> Path:
    """Grava config/coordenadas/<faixa>.json com a geometria REAL da folha.

    Valores em mm, origem no canto superior esquerdo da página A4.
    O leitor converte para pixels usando o tamanho real da imagem alinhada,
    então a coordenada vale para qualquer resolução de foto ou scanner.
    """
    destino = config_dir / "coordenadas" / f"{faixa}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "versao_template": f"{faixa}_v1",
        "faixa": faixa,
        "pagina": "A4",
        "unidade": "mm",
        "origem_y": "topo da página (imagem alinhada pós-perspectiva)",
        "observacoes": ("Gerado automaticamente por tools/pre_exame.py. "
                        "Valores x,y,w,h em mm relativos à folha A4; o OMR "
                        "converte para px pelo tamanho real da imagem "
                        "alinhada. Não editar à mão."),
    }
    for quesito in QUESITOS_ORDEM:
        payload[quesito] = coords.get(quesito, {})
    # Seção de observações estruturadas (obs_p1..p8, obs_m1..m8) — lida
    # pelo OMR na mesma passada dos códigos de erro.
    obs_section = {chave: coords[chave] for chave in sorted(coords)
                   if chave.startswith("obs_")}
    if obs_section:
        payload["observacoes"] = obs_section
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return destino

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

def desenhar_paragrafo(pdf: canvas.Canvas, texto: str, x: float, y: float,
                       largura_max: float, fonte: str = "Helvetica",
                       tamanho: float = FONTE_RODAPE) -> float:
    """Desenha texto com quebra de linha, sem cortar na margem."""
    leading = tamanho * 1.25
    linhas = quebrar_linhas(texto, fonte, tamanho, largura_max)
    for i, linha in enumerate(linhas):
        pdf.setFont(fonte, tamanho)
        pdf.drawString(x, y - i * leading, linha)
    return y - (len(linhas) - 1) * leading

def desenhar_checkbox_rotulado(pdf: canvas.Canvas, x: float, centro_y: float,
                               texto: str, tamanho: float,
                               lado_mm: float, texto_offset_mm: float,
                               coords_out: dict | None = None,
                               chave_coord: str | None = None) -> None:
    """Checkbox com texto à direita, alinhados na MESMA linha de centro.

    O baseline do texto é deslocado -0.35*tamanho (pt): o centro visual do
    texto (baseline + 0.35*tamanho) coincide com o centro do checkbox.
    """
    lado = lado_mm * mm
    yb = centro_y - lado / 2
    pdf.setFont("Helvetica", tamanho)
    pdf.rect(x, yb, lado, lado)
    pdf.drawString(x + texto_offset_mm * mm, centro_y - tamanho * 0.35, texto)
    if coords_out is not None and chave_coord:
        coords_out[chave_coord] = {
            "x": round(x / mm, 2),
            "y": round(ALTURA_A4_MM - (yb + lado) / mm, 2),
            "w": round(lado / mm, 2),
            "h": round(lado / mm, 2),
        }

def desenhar_observacoes_estruturadas(pdf: canvas.Canvas, y_base: float,
                                      coords_out: dict | None = None) -> float:
    """Seção única de observações estruturadas — uniforme para todas as faixas.

    Duas colunas: 'Ótimo!' (positivas, obs_p1..p8) e 'A Melhorar'
    (correções, obs_m1..m8). SEM limite de marcações e SEM campo 'Outro' —
    a observação é 100% estruturada.

    Espaçamento (v2col-2.8): 10mm entre o título da seção e os cabeçalhos,
    e 6mm entre o cabeçalho e a primeira opção.

    y_base = linha de base do título da seção. Retorna o y da base.
    """
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(15 * mm, y_base,
                   "OBSERVAÇÕES DO AVALIADOR — marque as opções que se aplicam")
    y = y_base - 10 * mm         # respiro entre título e cabeçalhos
    colunas = [("Ótimo!", OBS_POSITIVAS, "p"),
               ("A Melhorar", OBS_MELHORAR, "m")]
    for idx, (titulo, opcoes, prefixo) in enumerate(colunas):
        x = OBS_COL_X_MM[idx] * mm
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x, y, titulo)
        y_linha = y - 6 * mm     # respiro entre cabeçalho e 1ª opção
        for i, opcao in enumerate(opcoes, start=1):
            desenhar_checkbox_rotulado(
                pdf, x, y_linha, opcao, FONTE_OBS,
                OBS_CHK_LADO_MM, OBS_TEXTO_X_OFFSET_MM,
                coords_out, f"obs_{prefixo}{i}")
            y_linha -= OBS_LINHA_MM * mm
    return y_linha - OBS_LINHA_MM * mm

def desenhar_marcadores_fiduciais(pdf: canvas.Canvas, largura: float,
                                  altura: float) -> None:
    """Marcadores de registro em 3 cantos. O QR no canto superior direito
    funciona como 4ª referência de alinhamento para o OMR (Fase 03)."""
    margem = 8 * mm
    tam = 6 * mm
    cantos = ((margem, margem), (largura - margem, margem),
              (margem, altura - margem))
    for cx, cy in cantos:
        pdf.setLineWidth(0.8)
        pdf.line(cx - tam, cy, cx + tam, cy)
        pdf.line(cx, cy - tam, cx, cy + tam)
        pdf.setLineWidth(0.4)
        pdf.rect(cx - tam / 2, cy - tam / 2, tam, tam)

def desenhar_folha(pdf: canvas.Canvas, aluno: dict, sensei_id: str,
                   dojo: str, exame: str, faixa_cfg: dict,
                   coordenadas: dict, tmp_dir: Path,
                   coords_out: dict | None = None) -> None:
    """Desenha uma folha A4 do aluno, usando o layout da faixa.

    Duas colunas: esquerda (Kihon + Kata) e direita (Bunkai + Kumite).
    Cada quesito tem seus critérios com 7 checkboxes. Cada bloco reserva
    MAX_CRITERIOS_BLOCO linhas para as colunas terminarem na MESMA altura.
    A seção de observações estruturadas (uniforme) ocupa o rodapé.

    v2col-2.8: 16 opções estruturadas (8 + 8), sem campo 'Outro'.
    QR desenhado por último.
    """
    largura, altura = A4
    faixa_label = aluno["faixa_atual"].capitalize()

    # Cabeçalho
    pdf.setFont("Helvetica-Bold", FONTE_TITULO)
    pdf.drawString(15 * mm, altura - 15 * mm,
                   f"Folha de Avaliação Individual — Faixa {faixa_label}")
    pdf.setFont("Helvetica", FONTE_DADO)
    pdf.drawString(15 * mm, altura - 22 * mm,
                   f"Aluno: {aluno['nome']} ({aluno['id']})")
    pdf.drawString(15 * mm, altura - 28 * mm,
                   f"Dojo: {dojo} | Exame: {exame} | Avaliador: {sensei_id}")

    # Desenha cada coluna de forma independente, mas com o MESMO ritmo
    # vertical (blocos reservados em MAX_CRITERIOS_BLOCO linhas).
    for _, col_x_mm, quesitos in COLUNAS:
        col_x = col_x_mm * mm
        chk_x0 = (col_x_mm + CHECKBOX_X_OFFSET_MM) * mm
        y_atual = altura - 38 * mm
        for quesito in quesitos:
            criterios = faixa_cfg[quesito]["criterios"]
            pdf.setFont("Helvetica-Bold", FONTE_QUESITO)
            pdf.drawString(col_x, y_atual, NOME_QUESITO[quesito])
            y_atual -= ESPACO_TITULO_MM * mm
            for cri in criterios:
                nome = cri["nome"]
                x_texto = col_x + 2 * mm
                # Ajuste automático: reduz a fonte até o nome caber antes
                # dos checkboxes (nunca invade a coluna dos quadrados).
                largura_disponivel = (chk_x0 - x_texto
                                      - GAP_TEXTO_CHECKBOX_MM * mm)
                tamanho = FONTE_CRITERIO
                while (tamanho > FONTE_CRITERIO_MIN
                       and stringWidth(nome, "Helvetica", tamanho)
                       > largura_disponivel):
                    tamanho -= 0.5
                pdf.setFont("Helvetica", tamanho)
                pdf.drawString(x_texto, y_atual, nome)
                # Checkbox centralizado no centro visual do texto
                # (baseline + 0.35*tamanho) — mesmo alinhamento da seção
                # de observações.
                centro = y_atual + tamanho * 0.35
                yb = centro - CHECKBOX_LADO_MM / 2 * mm
                for i in range(CHECKBOX_QTD):
                    x0 = chk_x0 + i * CHECKBOX_PASSO_MM * mm
                    pdf.rect(x0, yb, CHECKBOX_LADO_MM * mm,
                             CHECKBOX_LADO_MM * mm)
                if coords_out is not None:
                    coords_out.setdefault(quesito, {})[cri["chave"]] = {
                        "x": round(chk_x0 / mm, 2),
                        "y": round(ALTURA_A4_MM
                                   - (yb + CHECKBOX_LADO_MM) / mm, 2),
                        "w": round(CHECKBOX_QTD * CHECKBOX_PASSO_MM, 2),
                        "h": round(CHECKBOX_LADO_MM, 2),
                    }
                y_atual -= LINHA_MM * mm
            # Reserva as linhas restantes do bloco (máx. 8) para que as
            # colunas terminem na MESMA altura.
            reserva = MAX_CRITERIOS_BLOCO - len(criterios)
            if reserva < 0:
                print(f"[AVISO] quesito {NOME_QUESITO[quesito]} excede "
                      f"{MAX_CRITERIOS_BLOCO} critérios — sem reserva de "
                      f"alinhamento")
            else:
                y_atual -= reserva * LINHA_MM * mm
            # Respiro após o bloco — o quesito seguinte começa com folga.
            y_atual -= GAP_APOS_BLOCO_MM * mm
            if y_atual < 20 * mm:
                print(f"[AVISO] layout apertado na faixa {faixa_label} "
                      f"(quesito {NOME_QUESITO[quesito]}) — revise "
                      f"config/faixas/{aluno['faixa_atual'].lower()}.json")

    # Seção de observações estruturadas (substitui as caixas de escrita
    # livre por quesito) — uniforme para todas as faixas.
    desenhar_observacoes_estruturadas(pdf, y_atual, coords_out)

    # QR Code (canto superior direito) — desenhado POR ÚLTIMO, depois das
    # colunas, para que nenhum elemento fique por cima.
    payload = montar_payload(dojo, exame, aluno["id"], sensei_id,
                             aluno["faixa_atual"])
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = tmp_dir / f"qr_temp_{aluno['id']}_{sensei_id}.png"
    img.save(qr_path)
    pdf.drawImage(str(qr_path),
                  largura - (QR_MARGEM_MM + QR_LADO_MM) * mm,
                  altura - (QR_MARGEM_MM + QR_LADO_MM) * mm,
                  QR_LADO_MM * mm, QR_LADO_MM * mm)

    # Rodapé
    largura_util = largura - 2 * RODAPE_MARGEM_MM * mm
    linhas_rodape = quebrar_linhas(RODAPE_TEXTO, "Helvetica-Oblique",
                                   FONTE_RODAPE, largura_util)
    y_rodape = (RODAPE_BASE_MM * mm
                + (len(linhas_rodape) - 1) * FONTE_RODAPE * 1.25)
    desenhar_paragrafo(pdf, RODAPE_TEXTO, RODAPE_MARGEM_MM * mm, y_rodape,
                       largura_util, fonte="Helvetica-Oblique",
                       tamanho=FONTE_RODAPE)
    desenhar_marcadores_fiduciais(pdf, largura, altura)
    pdf.showPage()

def executar_dry_run(args: argparse.Namespace, faixas_cfg: dict) -> int:
    """Modo --dry-run: mostra o plano sem gravar cadastro nem PDFs."""
    print("=== DRY RUN — nenhum arquivo será gravado ===")
    with open(args.csv, encoding="utf-8-sig") as fh:
        alunos = list(csv.DictReader(fh))
    existentes = set()
    if args.cadastro.exists():
        cadastro = json.loads(args.cadastro.read_text(encoding="utf-8"))
        existentes = {a["id"] for a in cadastro["alunos"]}
    novos = [a for a in alunos if a["id"] not in existentes]
    atualizados = [a for a in alunos if a["id"] in existentes]
    com_folha = [a for a in alunos if a["faixa_atual"].lower() in faixas_cfg]
    sem_folha = [a for a in alunos if a["faixa_atual"].lower() not in faixas_cfg]
    print(f"CSV: {args.csv} ({len(alunos)} alunos)")
    print(f"Dojo: {args.dojo} | Exame: {args.exame} | Senseis: {args.senseis}")
    print(f"Cadastro: {args.cadastro}")
    print(f"Novos (novo: true): {len(novos)} -> "
          f"{', '.join(a['id'] for a in novos) or '-'}")
    print(f"Existentes (faixa atualizada): {len(atualizados)} -> "
          f"{', '.join(a['id'] for a in atualizados) or '-'}")
    for sensei in [s.strip() for s in args.senseis.split(",")]:
        print(f"PDF folhas_{sensei}.pdf: {len(com_folha)} folha(s) "
              f"({', '.join(a['id'] for a in com_folha)})")
    if sem_folha:
        print(f"[AVISO] sem folha (faixa não suportada): "
              f"{', '.join(a['id'] for a in sem_folha)}")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pré-exame Karate-Ashi v2.0 (multi-faixa)")
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--dojo", required=True)
    ap.add_argument("--exame", required=True)
    ap.add_argument("--senseis", required=True,
                    help="IDs dos avaliadores separados por vírgula")
    ap.add_argument("--cadastro", type=Path,
                    default=Path("data/cadastro/alunos.json"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/pre_exame"))
    ap.add_argument("--dry-run", action="store_true",
                    help="apenas lista o plano, sem gravar cadastro nem PDFs")
    args = ap.parse_args()

    faixas_cfg = {}
    for faixa in FAIXAS_SUPORTADAS:
        caminho = args.config / "faixas" / f"{faixa}.json"
        if not caminho.exists():
            print(f"[ERRO] critérios não encontrados: {caminho}")
            return 2
        faixas_cfg[faixa] = carregar_json(caminho)["quesitos"]
    coordenadas_por_faixa = {
        faixa: carregar_coordenadas(args.config, faixa)
        for faixa in FAIXAS_SUPORTADAS
    }

    if args.dry_run:
        return executar_dry_run(args, faixas_cfg)

    novos = atualizar_cadastro(args.csv, args.cadastro)
    todos = json.loads(args.cadastro.read_text(encoding="utf-8"))["alunos"]
    args.out.mkdir(parents=True, exist_ok=True)
    gerados = 0
    sem_folha = []
    coords_geradas: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for sensei in [s.strip() for s in args.senseis.split(",")]:
            pdf = canvas.Canvas(str(args.out / f"folhas_{sensei}.pdf"),
                                pagesize=A4)
            for aluno in todos:
                if aluno["dojo_id"] != args.dojo:
                    continue
                faixa = aluno["faixa_atual"].lower()
                if faixa not in faixas_cfg:
                    print(f"[AVISO] faixa '{faixa}' não suportada — aluno "
                          f"{aluno['id']} sem folha nesta versão")
                    sem_folha.append(aluno["id"])
                    continue
                coords_out = coords_geradas.setdefault(faixa, {})
                desenhar_folha(pdf, aluno, sensei, args.dojo, args.exame,
                               faixas_cfg[faixa], coordenadas_por_faixa[faixa],
                               tmp_dir, coords_out)
                gerados += 1
            pdf.save()
    for faixa, coords in coords_geradas.items():
        if coords:
            caminho = salvar_coordenadas(args.config, faixa, coords)
            print(f"[OK] coordenadas gravadas: {caminho}")
    print(f"Pré-exame gerado em {args.out} | folhas: {gerados} | "
          f"novos cadastrados: {len(novos)}")
    if sem_folha:
        print(f"[AVISO] alunos sem folha (faixa não suportada): "
              f"{', '.join(sem_folha)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())