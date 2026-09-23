"""gerar_contato_rois.py — Recorta cada ROI da folha e monta um contato visual.

POR QUE ESTE SCRIPT EXISTE
--------------------------
O diagnóstico numérico (diagnosticar_omr.py) mostrou medições invertidas:
caixas "vazias" aparecem MAIS escuras que as "marcadas". Isso significa
que ainda não sabemos onde os checkboxes realmente ficam na folha.

Antes de calibrar o leitor, precisamos VER com os olhos:
  - onde o checkbox fica dentro da ROI (esquerda, centro ou direita);
  - onde estão as marcações reais (lápis/caneta);
  - qual o tamanho real do checkbox.

Este script recorta cada ROI da folha e monta uma grade (contato) com
rótulos, para você abrir e olhar.

Uso:
  python tools/gerar_contato_rois.py
  python tools/gerar_contato_rois.py --imagem output/scans/processados/s02.png

Saída:
  output/diagnostico/contato/<folha>_contato.png   (grade completa)
  output/diagnostico/contato/<folha>_rois/         (recortes individuais)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

A4_W_MM, A4_H_MM = 210.0, 297.0
SAIDA = Path("output/diagnostico/contato")


def carregar_coordenadas(config: Path, faixa: str) -> dict:
    caminho = config / "coordenadas" / f"{faixa}.json"
    return json.loads(caminho.read_text(encoding="utf-8"))


def coletar_rois(coords: dict) -> list[tuple[str, dict]]:
    """Extrai todas as ROIs de critérios: (nome, box) com x,y,w,h em mm."""
    rois = []
    for bloco_nome, bloco in coords.items():
        if not isinstance(bloco, dict):
            continue
        for nome, box in bloco.items():
            if isinstance(box, dict) and {"x", "y", "w", "h"} <= set(box):
                rois.append((f"{bloco_nome}.{nome}", box))
    return rois


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera contato visual das ROIs")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--faixa", default="branca")
    ap.add_argument("--imagem", type=Path, default=None,
                    help="folha a recortar (default: primeira em output/scans/processados)")
    args = ap.parse_args()

    coords = carregar_coordenadas(args.config, args.faixa)
    rois = coletar_rois(coords)
    print(f"Coordenadas carregadas: {len(rois)} ROIs")

    if args.imagem is None:
        pasta = Path("output/scans/processados")
        candidatos = sorted(p for p in pasta.glob("*.png") if p.is_file())
        if not candidatos:
            print("[ERRO] nenhuma imagem em output/scans/processados. Use --imagem.")
            return 2
        args.imagem = candidatos[0]

    imagem = Image.open(args.imagem).convert("RGB")
    largura, altura = imagem.size
    dpi_x = largura / (A4_W_MM / 25.4)
    dpi_y = altura / (A4_H_MM / 25.4)
    print(f"Folha: {args.imagem.name} ({largura}x{altura}, ~{dpi_x:.0f} DPI)")

    pasta_rois = SAIDA / f"{args.imagem.stem}_rois"
    pasta_rois.mkdir(parents=True, exist_ok=True)

    # 1. Recorta cada ROI (com margem de 1 mm para não cortar a borda)
    recortes = []
    for rotulo, box in rois:
        x = int(box["x"] * dpi_x / 25.4)
        y = int(box["y"] * dpi_y / 25.4)
        w = int(box["w"] * dpi_x / 25.4)
        h = int(box["h"] * dpi_y / 25.4)
        margem = max(2, int(1.0 * dpi_x / 25.4))
        x0, y0 = max(0, x - margem), max(0, y - margem)
        x1, y1 = min(largura, x + w + margem), min(altura, y + h + margem)
        recorte = imagem.crop((x0, y0, x1, y1))
        recorte.save(pasta_rois / f"{rotulo.replace('.', '_')}.png")
        recortes.append((rotulo, recorte))

    # 2. Escala todos para a mesma altura (para a grade ficar alinhada)
    ALT_CELULA = 120
    celulas = []
    for rotulo, recorte in recortes:
        escala = ALT_CELULA / recorte.height
        novo_w = max(1, int(recorte.width * escala))
        celulas.append((rotulo, recorte.resize((novo_w, ALT_CELULA))))

    # 3. Monta a grade com 4 colunas e rótulo embaixo de cada célula
    COLUNAS = 4
    ALT_ROTULO = 18
    larg_celula = max(c.width for _, c in celulas)
    larg_celula = max(larg_celula, max(len(r) for r, _ in celulas) * 7 + 10)
    linhas = (len(celulas) + COLUNAS - 1) // COLUNAS

    grade = Image.new(
        "RGB",
        (COLUNAS * larg_celula, linhas * (ALT_CELULA + ALT_ROTULO)),
        "white",
    )
    desenho = ImageDraw.Draw(grade)
    try:
        fonte = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        fonte = ImageFont.load_default()

    for i, (rotulo, celula) in enumerate(celulas):
        col = i % COLUNAS
        lin = i // COLUNAS
        x0 = col * larg_celula
        y0 = lin * (ALT_CELULA + ALT_ROTULO)
        grade.paste(celula, (x0, y0))
        desenho.text((x0 + 2, y0 + ALT_CELULA + 2), rotulo, fill="black", font=fonte)

    arquivo = SAIDA / f"{args.imagem.stem}_contato.png"
    grade.save(arquivo)
    print(f"Contato salvo: {arquivo}")
    print(f"Recortes individuais: {pasta_rois}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())