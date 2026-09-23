"""diagnosticar_omr.py — Mede a geometria real dos checkboxes e calibra o limiar.

POR QUE ESTE SCRIPT EXISTE
--------------------------
Antes de alterar o omr_reader (Fase 01), precisamos de 3 números exatos:

  1. ONDE o checkbox fica dentro da ROI (offset em mm a partir do canto
     esquerdo). Hoje assumimos "primeiros 4 mm", mas o teste real mostrou
     que essa suposição está errada (medições de 0-23% mesmo em caixas
     que o OMR leu como marcadas).

  2. QUAL o tamanho real do checkbox (largura x altura em mm).

  3. QUAL o limiar ideal de escuridão para separar "marcado" de "vazio"
     neste scanner/caneta. O OMR usa 0.40 fixo; o teste real sugere que
     o valor correto é bem menor.

A sacada: usamos os JSONs que o OMR já gerou (output/teste_omr) como
"gabarito" — sabemos quais critérios ele leu como marcados. Então medimos
a escuridão em 3 regiões candidatas e vemos qual região + qual limiar
separa melhor marcado de vazio.

Uso:
  python tools/diagnosticar_omr.py
  python tools/diagnosticar_omr.py --pasta-scans output/scans

Saída:
  Relatório no terminal + output/diagnostico/geometria_checkboxes.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

A4_W_MM, A4_H_MM = 210.0, 297.0
EXT_IMAGEM = {".png", ".jpg", ".jpeg"}
PASTAS_SCANS = ["output/scans", "output/scans/processados"]
PASTA_JSON = Path("output/teste_omr")
SAIDA = Path("output/diagnostico")


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


def limiar_otsu(hist: np.ndarray) -> int:
    """Limiar de Otsu: o valor que melhor separa fundo de conteúdo."""
    total = hist.sum()
    if total == 0:
        return 128
    prob = hist / total
    cum = np.cumsum(prob)
    media_acum = np.cumsum(prob * np.arange(256))
    media_total = media_acum[-1]
    melhor_t, melhor_var = 0, 0.0
    for t in range(1, 256):
        w0 = cum[t]
        w1 = 1.0 - w0
        if w0 == 0 or w1 == 0:
            continue
        mu0 = media_acum[t] / w0
        mu1 = (media_total - media_acum[t]) / w1
        var = w0 * w1 * (mu0 - mu1) ** 2
        if var > melhor_var:
            melhor_var = var
            melhor_t = t
    return melhor_t


def encontrar_checkbox(regiao: np.ndarray, limiar: int) -> tuple[int, int, int, int] | None:
    """Estima a caixa do checkbox dentro da ROI.

    A caixa é quadrada e fica no início (esquerda) da ROI. Usamos a
    densidade de pixels escuros por coluna/linha para achar a borda
    esquerda (x0) e as bordas superior/inferior (y0, y1). A largura é
    estimada pela altura (caixa quadrada).

    Retorna (x, y, w, h) em pixels, ou None se não achar nada.
    """
    h, w = regiao.shape
    binaria = regiao < limiar
    dens_col = binaria.mean(axis=0)
    dens_lin = binaria.mean(axis=1)

    ativas_col = np.where(dens_col > 0.15)[0]
    ativas_lin = np.where(dens_lin > 0.15)[0]
    if len(ativas_col) == 0 or len(ativas_lin) == 0:
        return None

    x0 = ativas_col[0]
    y0 = ativas_lin[0]
    y1 = ativas_lin[-1]
    altura = y1 - y0 + 1
    return x0, y0, altura, altura


def taxa_escuros(regiao: np.ndarray, limiar: int) -> float:
    """Fração de pixels com valor < limiar na região (0.0 a 1.0)."""
    if regiao.size == 0:
        return 0.0
    return float((regiao < limiar).mean())


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico da geometria dos checkboxes")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--faixa", default="branca")
    ap.add_argument("--pasta-scans", type=Path, default=None,
                    help="pasta com as folhas (default: output/scans + processados)")
    args = ap.parse_args()

    coords = carregar_coordenadas(args.config, args.faixa)
    rois = coletar_rois(coords)
    print(f"Coordenadas carregadas: {len(rois)} ROIs de criterios em {args.faixa}.json")

    pastas = [args.pasta_scans] if args.pasta_scans else [Path(p) for p in PASTAS_SCANS]
    imagens, vistos = [], set()
    for pasta in pastas:
        if pasta.is_dir():
            for p in sorted(pasta.iterdir()):
                if p.suffix.casefold() in EXT_IMAGEM and p.name not in vistos:
                    vistos.add(p.name)
                    imagens.append(p)

    if not imagens:
        print("[ERRO] nenhuma imagem encontrada nas pastas de scan.")
        return 2

    SAIDA.mkdir(parents=True, exist_ok=True)
    relatorio = {"folhas": []}

    for img_path in imagens:
        json_path = PASTA_JSON / f"{img_path.stem}.json"
        if not json_path.exists():
            candidatos = sorted(PASTA_JSON.glob(f"{img_path.stem}_p*.json"))
            json_path = candidatos[0] if candidatos else None
        if json_path is None:
            print(f"\n=== {img_path.name} === [SEM JSON — pulando]")
            continue

        dados = json.loads(json_path.read_text(encoding="utf-8"))
        imagem = Image.open(img_path).convert("L")
        largura, altura = imagem.size
        dpi_x = largura / (A4_W_MM / 25.4)
        dpi_y = altura / (A4_H_MM / 25.4)

        arr = np.asarray(imagem, dtype=np.uint8)
        hist = np.bincount(arr.ravel(), minlength=256)
        otsu = limiar_otsu(hist)
        p_min, p_max = int(arr.min()), int(arr.max())
        media = float(arr.mean())

        print(f"\n=== {img_path.name} ({largura}x{altura}, ~{dpi_x:.0f} DPI) ===")
        print(f"    contraste: min={p_min} max={p_max} media={media:.0f} | Otsu={otsu}")

        folha = {
            "arquivo": img_path.name,
            "dpi": round(dpi_x),
            "contraste": {"min": p_min, "max": p_max, "media": round(media, 1), "otsu": otsu},
            "checkboxes": [],
        }

        stats = {"roi_inteira": [], "esquerda_4mm": [], "checkbox": []}
        geometrias = []

        for nome, box in rois:
            x = int(box["x"] * dpi_x / 25.4)
            y = int(box["y"] * dpi_y / 25.4)
            w = int(box["w"] * dpi_x / 25.4)
            h = int(box["h"] * dpi_y / 25.4)
            if w < 1 or h < 1:
                continue
            regiao = arr[y:y + h, x:x + w]

            d_roi = taxa_escuros(regiao, otsu)

            w4 = max(1, int(4.0 * dpi_x / 25.4))
            d_esq = taxa_escuros(regiao[:, :w4], otsu)

            cb = encontrar_checkbox(regiao, otsu)
            d_cb = None
            if cb is not None:
                cx, cy, cw, ch = cb
                recuo_x = max(1, int(cw * 0.2))
                recuo_y = max(1, int(ch * 0.2))
                interior = regiao[cy + recuo_y:cy + ch - recuo_y,
                                  cx + recuo_x:cx + cw - recuo_x]
                d_cb = taxa_escuros(interior, otsu)
                geometrias.append({
                    "criterio": nome,
                    "x_mm": round(cx / dpi_x * 25.4, 2),
                    "y_mm": round(cy / dpi_y * 25.4, 2),
                    "w_mm": round(cw / dpi_x * 25.4, 2),
                    "h_mm": round(ch / dpi_y * 25.4, 2),
                })

            quesito, criterio = nome.split(".", 1)
            freq = dados.get("avaliacoes", {}).get(quesito, {}).get("frequencias", {})
            marcado = int(freq.get(criterio, 0)) > 0

            stats["roi_inteira"].append((marcado, d_roi))
            stats["esquerda_4mm"].append((marcado, d_esq))
            if d_cb is not None:
                stats["checkbox"].append((marcado, d_cb))

            folha["checkboxes"].append({
                "criterio": nome,
                "omr_marcado": marcado,
                "escuro_roi": round(d_roi, 3),
                "escuro_esquerda4mm": round(d_esq, 3),
                "escuro_checkbox": round(d_cb, 3) if d_cb is not None else None,
            })

        print(f"    {'regiao':<16} {'marcado (media)':>16} {'vazio (media)':>14} {'separacao':>10}")
        for nome_regiao, valores in stats.items():
            if not valores:
                continue
            marcados = [v for m, v in valores if m]
            vazios = [v for m, v in valores if not m]
            med_m = sum(marcados) / len(marcados) if marcados else 0.0
            med_v = sum(vazios) / len(vazios) if vazios else 0.0
            print(f"    {nome_regiao:<16} {med_m:>16.3f} {med_v:>14.3f} {med_m - med_v:>10.3f}")

        if geometrias:
            med_x = sum(g["x_mm"] for g in geometrias) / len(geometrias)
            med_y = sum(g["y_mm"] for g in geometrias) / len(geometrias)
            med_w = sum(g["w_mm"] for g in geometrias) / len(geometrias)
            med_h = sum(g["h_mm"] for g in geometrias) / len(geometrias)
            print(f"    checkbox detectado em {len(geometrias)}/{len(rois)} ROIs")
            print(f"    geometria media: x={med_x:.2f}mm y={med_y:.2f}mm "
                  f"w={med_w:.2f}mm h={med_h:.2f}mm")
            folha["geometria_checkbox"] = {
                "x_mm": round(med_x, 2), "y_mm": round(med_y, 2),
                "w_mm": round(med_w, 2), "h_mm": round(med_h, 2),
                "detectados": len(geometrias), "total_rois": len(rois),
            }

        relatorio["folhas"].append(folha)

    (SAIDA / "geometria_checkboxes.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatorio salvo em: {SAIDA / 'geometria_checkboxes.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())