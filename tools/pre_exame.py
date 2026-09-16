#!/usr/bin/env python3
"""tools/pre_exame.py — Gera folhas PDF com QR Code (multi-faixa).

Uso: python tools/pre_exame.py --csv data/alunos_exame.csv \
    --dojo D01 --exame EXA-D01-2026-02 --senseis S01,S02,S03 \
    --cadastro data/cadastro/alunos.json --out output/pre_exame/

Fluxo:
1. lê o CSV (alunos com faixa atual e pretendida);
2. merge idempotente no cadastro (novos com "novo": true; existentes têm
   nome, faixas e dojo atualizados) — os campos de CICLO DE VIDA (ativo,
   ultima_promocao, historico_promocoes) NUNCA são sobrescritos;
3. seleciona os elegíveis (v2col-4.0): ativo != false E com
   faixa_pretendida preenchida (regra em core/cadastro.py);
4. para cada avaliador x aluno, desenha a folha usando o layout da faixa;
5. gera o QR Code com o payload padrão e salva o PDF;
6. GRAVA config/coordenadas/<faixa>.json com a posição real de cada linha
   de checkboxes e de cada checkbox de observação estruturada (em mm),
   para o OMR (Fase 03) ler a MESMA geometria que a folha usa.

Layout: folha A4 em DUAS COLUNAS, distribuída pela página inteira.
Esquerda: Kihon + Kata | Direita: Bunkai + Kumite
Cada quesito mantém seus critérios com 7 checkboxes.

Observações estruturadas (v2col-2.8):
- A observação do avaliador nasce na FOLHA como checkboxes, uniformes para
  todas as faixas: coluna 'Ótimo!' (obs_p1..p8) e 'A Melhorar' (obs_m1..m8).
  SEM limite de marcações: o avaliador marca as opções que se aplicam; o OMR
  lê cada checkbox de forma independente e o relatório concatena tudo.
- SEM campo 'Outro': a observação é 100% estruturada — nenhuma transcrição
  manual entra no fluxo.
- O VOCABULÁRIO vive em core/observacoes.py (OBS_POSITIVAS/OBS_MELHORAR) e
  é IMPORTADO daqui — folha e relatório nunca divergem (princípio dos
  gêmeos). As chaves das ROIs gravadas são exatamente as chaves do
  vocabulário.
- ICR (manuscrito) descartado por acurácia.
- Alinhamento: o baseline do texto é deslocado -0.35*tamanho (pt), de modo
  que o centro visual do texto coincide com o centro do checkbox.
- Espaçamento: respiro de 10mm entre o título da seção e os cabeçalhos
  'Ótimo!'/'A Melhorar', e 6mm entre o cabeçalho e a primeira opção.

Ciclo de vida do aluno (v2col-4.0):
- A seleção usa core/cadastro.py::alunos_para_exame — a MESMA regra que o
  tools/promover_alunos.py usa para promover. Folha e promoção nunca divergem.
- Filtros: ativo (False não gera folha) e faixa_pretendida (vazia não gera
  folha — é o caso do aluno na faixa terminal/Sensei).
- Campo 'novo' marca a primeira avaliação; é o promover_alunos que o zera.

Nomes legíveis (opcional):
- config/dojos.json {"D01": "Dojo Central"}
- config/avaliadores.json {"S01": "Sensei Paulo"}
- O cabeçalho imprime "Dojo Central (D01)" / "Sensei Paulo (S01)".
- Arquivo ausente ou inválido não quebra a geração (cai para o ID puro).

v2col-2.4 (mantido):
- QR desenhado POR ÚLTIMO no canto superior direito (nada cobre);
- sem estampa de versão na folha;
- entrelinha 8,5mm, quesito 12pt, critério 9pt — os blocos de quesitos
  terminam ~93mm acima da base; a seção de observações estruturadas ocupa
  o rodapé.

IMPORTANTE: a geometria de desenho é FIXA no código (constantes abaixo).
O config/coordenadas/<faixa>.json é apenas SAÍDA (registra o que foi
desenhado) — nunca é lido como configuração de desenho.

Nota: os CSVs de entrada são lidos com encoding="utf-8-sig", que aceita
arquivos com ou sem BOM (Excel/PowerShell 5.1 gravam com BOM).

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

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from core.cadastro import alunos_para_exame
from core.config import (
    FAIXAS_SUPORTADAS,
    QUESITOS as QUESITOS_ORDEM,  # alias mantém os usos existentes (fonte única)
    carregar_json,
)
from core.observacoes import OBS_MELHORAR, OBS_POSITIVAS

NOME_QUESITO = {
    "kihon": "Kihon",
    "kata": "Kata",
    "bunkai": "Bunkai",
    "kumite": "Kumite",
}

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
CHECKBOX_X_OFFSET_MM = 46.0  # do início da coluna até o 1º checkbox
CHECKBOX_PASSO_MM = 5.5
CHECKBOX_LADO_MM = 4.0
CHECKBOX_QTD = 7

# Observações estruturadas — UNIFORMES para todas as faixas (v2col-2.8).
OBS_COL_X_MM = [15.0, 107.0]  # x das colunas da seção (mm)
OBS_CHK_LADO_MM = 4.5  # checkbox da seção (um pouco maior p/ OMR)
OBS_LINHA_MM = 6.5  # altura de linha da seção
OBS_TEXTO_X_OFFSET_MM = 7.0  # texto após o checkbox

# QR Code — canto superior direito (desenhado por último, nada cobre).
QR_LADO_MM = 22.0
QR_MARGEM_MM = 10.0

# Tipografia
FONTE_TITULO = 13
FONTE_QUESITO = 12
FONTE_CRITERIO = 9
FONTE_CRITERIO_MIN = 7
FONTE_OBS = 9
FONTE_DADO = 10
FONTE_RODAPE = 9
LINHA_MM = 8.5
MAX_CRITERIOS_BLOCO = 8
ESPACO_TITULO_MM = 7.0
GAP_TEXTO_CHECKBOX_MM = 2.0
GAP_APOS_BLOCO_MM = 8.0
RODAPE_TEXTO = ("Como marcar: preencha TOTALMENTE o quadrado (caneta preta "
                "ou lápis 2B), da esquerda para a direita, sem pular "
                "caixas. Deixe em branco para zero falhas.")
RODAPE_MARGEM_MM = 15.0
RODAPE_BASE_MM = 10.0

# Campos de ciclo de vida — preservados no merge e criados para aluno novo.
CAMPOS_CICLO_VIDA = ("ativo", "ultima_promocao", "historico_promocoes")
CAMPOS_CSV = ("nome", "faixa_atual", "faixa_pretendida", "dojo_id")

def carregar_nomes(caminho: Path) -> dict:
    """Carrega config/dojos.json ou config/avaliadores.json ({} se ausente)."""
    if not caminho.exists():
        return {}
    try:
        dados = carregar_json(caminho)
    except (json.JSONDecodeError, OSError):
        print(f"[AVISO] arquivo de nomes inválido, ignorado: {caminho}")
        return {}
    return dados if isinstance(dados, dict) else {}

def _rotulo(identificador: str, nomes: dict) -> str:
    """'S01' -> 'Sensei Paulo (S01)'; sem nome cadastrado, só o ID."""
    nome = nomes.get(identificador)
    return f"{nome} ({identificador})" if nome else identificador

def normalizar_faixa(faixa: str) -> str:
    """Remove acentos e normaliza para uppercase (payload QR sem acentos)."""
    sem_acentos = unicodedata.normalize("NFKD", faixa)
    ascii_only = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return ascii_only.upper().strip()

def montar_payload(dojo: str, exame: str, aluno_id: str, sensei_id: str,
                   faixa: str) -> str:
    """KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA — sem acentos, com pipes."""
    return "|".join(["KA", dojo, exame, aluno_id, sensei_id,
                     normalizar_faixa(faixa)])

def atualizar_cadastro(csv_path: Path, cadastro_path: Path) -> list[dict]:
    """Merge idempotente do CSV no alunos.json.

    Novos alunos entram com os campos do CSV + "novo": true e os campos de
    CICLO DE VIDA inicializados (ativo, ultima_promocao, historico_promocoes).
    Alunos existentes têm apenas nome/faixas/dojo atualizados — os campos de
    ciclo de vida são PRESERVADOS (o CSV não tem o que o promover_alunos
    escreveu; sobrescrevê-los apagaria o histórico).
    """
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
                # Garante os campos de ciclo de vida em cadastros antigos,
                # sem tocar no que já existe.
                existente.setdefault("ativo", True)
                existente.setdefault("ultima_promocao", None)
                existente.setdefault("historico_promocoes", [])
    cadastro_path.parent.mkdir(parents=True, exist_ok=True)
    cadastro_path.write_text(
        json.dumps(cadastro, ensure_ascii=False, indent=2), encoding="utf-8")
    return novos

def carregar_coordenadas(config_dir: Path, faixa: str) -> dict:
    """Compatibilidade de assinatura (a geometria de desenho é fixa no código)."""
    caminho = config_dir / "coordenadas" / f"{faixa}.json"
    if caminho.exists():
        return carregar_json(caminho)
    return {}

def salvar_coordenadas(config_dir: Path, faixa: str, coords: dict) -> Path:
    """Grava config/coordenadas/<faixa>.json com a geometria REAL da folha."""
    destino = config_dir / "coordenadas" / f"{faixa}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "versao_template": f"{faixa}_v1",
        "faixa": faixa,
        "pagina": "A4",
        "unidade": "mm",
        "origem_y": "topo da página (imagem alinhada pós-perspectiva)",
    }
    for quesito in QUESITOS_ORDEM:
        payload[quesito] = coords.get(quesito, {})
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
                       largura_max: float,
                       fonte: str = "Helvetica",
                       tamanho: float = FONTE_RODAPE) -> float:
    """Desenha texto com quebra de linha, sem cortar na margem."""
    leading = tamanho * 1.25
    linhas = quebrar_linhas(texto, fonte, tamanho, largura_max)
    for i, linha in enumerate(linhas):
        pdf.setFont(fonte, tamanho)
        pdf.drawString(x, y - i * leading, linha)
    return y - (len(linhas) - 1) * leading

def desenhar_checkbox_rotulado(pdf: canvas.Canvas, x: float, centro_y: float,
                               texto: str, tamanho: float, lado_mm: float,
                               texto_offset_mm: float,
                               coords_out: dict | None = None,
                               chave_coord: str | None = None) -> None:
    """Checkbox com texto à direita, alinhados na MESMA linha de centro."""
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

def desenhar_observacoes_estruturadas(
        pdf: canvas.Canvas, y_base: float,
        coords_out: dict | None = None) -> float:
    """Seção única de observações estruturadas — uniforme para todas as faixas."""
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(15 * mm, y_base,
                   "OBSERVAÇÕES DO AVALIADOR — marque as opções que se aplicam")
    y = y_base - 10 * mm
    colunas = [("Ótimo!", OBS_POSITIVAS), ("A Melhorar", OBS_MELHORAR)]
    for idx, (titulo, opcoes) in enumerate(colunas):
        x = OBS_COL_X_MM[idx] * mm
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(x, y, titulo)
        y_linha = y - 6 * mm
        for chave, opcao in opcoes.items():
            desenhar_checkbox_rotulado(
                pdf, x, y_linha, opcao, FONTE_OBS, OBS_CHK_LADO_MM,
                OBS_TEXTO_X_OFFSET_MM, coords_out, chave)
            y_linha -= OBS_LINHA_MM * mm
    return y_linha - OBS_LINHA_MM * mm

def desenhar_marcadores_fiduciais(pdf: canvas.Canvas, largura: float,
                                  altura: float) -> None:
    """Marcadores de registro em 3 cantos (o QR é a 4ª referência)."""
    margem = 8 * mm
    tam = 6 * mm
    cantos = ((margem, margem),
              (largura - margem, margem),
              (margem, altura - margem))
    for cx, cy in cantos:
        pdf.setLineWidth(0.8)
        pdf.line(cx - tam, cy, cx + tam, cy)
        pdf.line(cx, cy - tam, cx, cy + tam)
        pdf.setLineWidth(0.4)
        pdf.rect(cx - tam / 2, cy - tam / 2, tam, tam)

def desenhar_folha(pdf: canvas.Canvas, aluno: dict, sensei_id: str, dojo: str,
                   exame: str, faixa_cfg: dict, coordenadas: dict,
                   tmp_dir: Path, coords_out: dict | None = None,
                   dojos: dict | None = None,
                   avaliadores: dict | None = None) -> None:
    """Desenha uma folha A4 do aluno, usando o layout da faixa."""
    largura, altura = A4
    faixa_label = aluno["faixa_atual"].capitalize()
    dojos = dojos or {}
    avaliadores = avaliadores or {}

    pdf.setFont("Helvetica-Bold", FONTE_TITULO)
    pdf.drawString(15 * mm, altura - 15 * mm,
                   f"Folha de Avaliação Individual — Faixa {faixa_label}")
    pdf.setFont("Helvetica", FONTE_DADO)
    pdf.drawString(15 * mm, altura - 22 * mm,
                   f"Aluno: {aluno['nome']} ({aluno['id']})")
    pdf.drawString(15 * mm, altura - 28 * mm,
                   f"Dojo: {_rotulo(dojo, dojos)} | Exame: {exame} | "
                   f"Avaliador: {_rotulo(sensei_id, avaliadores)}")

    y_atual = altura - 38 * mm
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
                largura_disponivel = (
                    chk_x0 - x_texto - GAP_TEXTO_CHECKBOX_MM * mm)
                tamanho = FONTE_CRITERIO
                while (tamanho > FONTE_CRITERIO_MIN
                       and stringWidth(nome, "Helvetica", tamanho)
                       > largura_disponivel):
                    tamanho -= 0.5
                pdf.setFont("Helvetica", tamanho)
                pdf.drawString(x_texto, y_atual, nome)
                centro = y_atual + tamanho * 0.35
                yb = centro - CHECKBOX_LADO_MM / 2 * mm
                for i in range(CHECKBOX_QTD):
                    x0 = chk_x0 + i * CHECKBOX_PASSO_MM * mm
                    pdf.rect(x0, yb,
                             CHECKBOX_LADO_MM * mm, CHECKBOX_LADO_MM * mm)
                if coords_out is not None:
                    coords_out.setdefault(quesito, {})[cri["chave"]] = {
                        "x": round(chk_x0 / mm, 2),
                        "y": round(ALTURA_A4_MM - (yb + CHECKBOX_LADO_MM) / mm,
                                   2),
                        "w": round(CHECKBOX_QTD * CHECKBOX_PASSO_MM, 2),
                        "h": round(CHECKBOX_LADO_MM, 2),
                    }
                y_atual -= LINHA_MM * mm
            reserva = MAX_CRITERIOS_BLOCO - len(criterios)
            if reserva < 0:
                print(f"[AVISO] quesito {NOME_QUESITO[quesito]} excede "
                      f"{MAX_CRITERIOS_BLOCO} critérios — sem reserva de "
                      f"alinhamento")
            else:
                y_atual -= reserva * LINHA_MM * mm
            y_atual -= GAP_APOS_BLOCO_MM * mm
            if y_atual < 20 * mm:
                print(f"[AVISO] layout apertado na faixa {faixa_label} "
                      f"(quesito {NOME_QUESITO[quesito]}) — revise "
                      f"config/faixas/{aluno['faixa_atual'].lower()}.json")

    desenhar_observacoes_estruturadas(pdf, y_atual, coords_out)

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

    # Filtro de elegibilidade (v2col-4.0) — mesma regra do promover_alunos.
    elegiveis = alunos_para_exame(alunos)
    inelegiveis = [a for a in alunos if a not in elegiveis]
    com_folha = [a for a in elegiveis
                 if a["faixa_atual"].lower() in faixas_cfg]
    sem_folha = [a for a in elegiveis
                 if a["faixa_atual"].lower() not in faixas_cfg]

    print(f"CSV: {args.csv} ({len(alunos)} alunos)")
    print(f"Dojo: {args.dojo} | Exame: {args.exame} | "
          f"Senseis: {args.senseis}")
    print(f"Cadastro: {args.cadastro}")
    print(f"Novos (novo: true): {len(novos)} -> "
          f"{', '.join(a['id'] for a in novos) or '-'}")
    print(f"Existentes (faixa atualizada): {len(atualizados)} -> "
          f"{', '.join(a['id'] for a in atualizados) or '-'}")
    print(f"\nElegíveis (ativo + faixa_pretendida): {len(elegiveis)} -> "
          f"{', '.join(a['id'] for a in elegiveis) or '-'}")
    if inelegiveis:
        print(f"[PULADOS] sem faixa_pretendida/inativo: "
              f"{', '.join(a['id'] for a in inelegiveis)}")
    for sensei in [s.strip() for s in args.senseis.split(",")]:
        print(f"PDF folhas_{sensei}.pdf: {len(com_folha)} folha(s) "
              f"({', '.join(a['id'] for a in com_folha)})")
    if sem_folha:
        print(f"[AVISO] sem folha (faixa não suportada): "
              f"{', '.join(a['id'] for a in sem_folha)}")
    print(f" faixas suportadas hoje: {', '.join(FAIXAS_SUPORTADAS)}")
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
    dojos = carregar_nomes(args.config / "dojos.json")
    avaliadores = carregar_nomes(args.config / "avaliadores.json")

    if args.dry_run:
        return executar_dry_run(args, faixas_cfg)

    novos = atualizar_cadastro(args.csv, args.cadastro)
    todos = json.loads(args.cadastro.read_text(encoding="utf-8"))["alunos"]
    # Filtro de elegibilidade (v2col-4.0): ativo E com faixa_pretendida.
    do_dojo = [a for a in todos if a.get("dojo_id") == args.dojo]
    elegiveis_ids = {a["id"] for a in alunos_para_exame(do_dojo)}
    alunos = [a for a in do_dojo if a["id"] in elegiveis_ids]
    pulados = [a["id"] for a in do_dojo if a["id"] not in elegiveis_ids]
    if pulados:
        print(f"[INFO] pulados (inativo ou sem faixa_pretendida): "
              f"{', '.join(pulados)}")

    args.out.mkdir(parents=True, exist_ok=True)
    gerados = 0
    sem_folha = []
    coords_geradas: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for sensei in [s.strip() for s in args.senseis.split(",")]:
            pdf = canvas.Canvas(str(args.out / f"folhas_{sensei}.pdf"),
                                pagesize=A4)
            for aluno in alunos:
                faixa = aluno["faixa_atual"].lower()
                if faixa not in faixas_cfg:
                    print(f"[AVISO] faixa '{faixa}' não suportada — aluno "
                          f"{aluno['id']} sem folha nesta versão")
                    sem_folha.append(aluno["id"])
                    continue
                coords_out = coords_geradas.setdefault(faixa, {})
                desenhar_folha(pdf, aluno, sensei, args.dojo, args.exame,
                               faixas_cfg[faixa],
                               coordenadas_por_faixa[faixa], tmp_dir,
                               coords_out, dojos, avaliadores)
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