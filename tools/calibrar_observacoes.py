"""tools/calibrar_observacoes.py — v2 (deslocamento + escala).

Mede, na folha alinhada:
  1. o deslocamento (dy) das ROIs de observação vs as caixas impressas;
  2. o passo das caixas de observação vs o config (6,5 mm);
  3. o passo das LINHAS de critérios vs o config (8,5 mm) — referência de escala.

Separa três causas da leitura trocada:
  A) ESCALA DA PÁGINA: critérios E observações desviados -> homografia/warp;
  B) BLOCO DE OBSERVAÇÕES: só as observações desviadas -> config x folha;
  C) ALINHADO: nada desviado -> investigar o limiar de classificação.

v2 corrige o veredito da v1 (que calculava o passo sobre as duas colunas juntas
e obtinha 0) e valida que o contorno é um QUADRADO VAZADO (checkbox impresso),
não um glifo de texto.

Uso:
    python tools/calibrar_observacoes.py --foto output/fotos/IMG_9786.JPEG \
        --faixa branca --config config --out output/diagnostico
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from core import omr_reader  # noqa: E402

LARGURA_A4_MM = omr_reader.LARGURA_A4_MM
ALTURA_A4_MM = omr_reader.ALTURA_A4_MM

LADO_MIN_MM, LADO_MAX_MM = 2.8, 7.0
ASPECTO_MIN, ASPECTO_MAX = 0.60, 1.70

# (quesito, x0_mm, x1_mm) das colunas de critérios no layout
COLUNAS_CRITERIOS = (("kihon", 58.0, 102.0), ("kata", 58.0, 102.0),
                     ("bunkai", 150.0, 194.0), ("kumite", 150.0, 194.0))

def _quadrado_vazado(cinza, x, y, w, h):
    """True se é quadrado com borda escura e interior claro (checkbox)."""
    if w < 5 or h < 5:
        return False
    roi = cinza[y:y + h, x:x + w]
    borda = np.concatenate([roi[0, :], roi[-1, :], roi[:, 0], roi[:, -1]])
    interior = roi[h // 4:3 * h // 4, w // 4:3 * w // 4]
    if interior.size == 0:
        return False
    return float(borda.mean()) < 140.0 and float(interior.mean()) > 170.0

def _quadrados(alinhada, x0_mm, x1_mm, y0_mm, y1_mm):
    h, w = alinhada.shape[:2]
    pxx, pxy = w / LARGURA_A4_MM, h / ALTURA_A4_MM
    xa, xb = max(0, int(x0_mm * pxx)), min(w, int(x1_mm * pxx))
    ya, yb = max(0, int(y0_mm * pxy)), min(h, int(y1_mm * pxy))
    if xb - xa < 10 or yb - ya < 10:
        return []
    reg = alinhada[ya:yb, xa:xb]
    cinza = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(
        cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(
        binaria, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    achados = []
    for c in contornos:
        x, y, cw, ch = cv2.boundingRect(c)
        lx, ly = cw / pxx, ch / pxy
        if not (LADO_MIN_MM <= lx <= LADO_MAX_MM and
                LADO_MIN_MM <= ly <= LADO_MAX_MM):
            continue
        if not (ASPECTO_MIN <= cw / max(ch, 1) <= ASPECTO_MAX):
            continue
        if not _quadrado_vazado(cinza, x, y, cw, ch):
            continue
        achados.append({"cx": (xa + x + cw / 2) / pxx,
                        "cy": (ya + y + ch / 2) / pxy})
    return achados

def _barras(alinhada, x0_mm, x1_mm, y0_mm, y1_mm,
            wmin=28.0, wmax=48.0, hmin=2.5, hmax=7.0):
    """Detecta barras horizontais de critério (ROI de 38,5 mm x 4,0 mm)."""
    h, w = alinhada.shape[:2]
    pxx, pxy = w / LARGURA_A4_MM, h / ALTURA_A4_MM
    xa, xb = max(0, int(x0_mm * pxx)), min(w, int(x1_mm * pxx))
    ya, yb = max(0, int(y0_mm * pxy)), min(h, int(y1_mm * pxy))
    if xb - xa < 10 or yb - ya < 10:
        return []
    reg = alinhada[ya:yb, xa:xb]
    cinza = cv2.cvtColor(reg, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(
        cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(
        binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ys = []
    for c in contornos:
        _, y, cw, ch = cv2.boundingRect(c)
        lw, lh = cw / pxx, ch / pxy
        if wmin <= lw <= wmax and hmin <= lh <= hmax:
            ys.append((ya + y + ch / 2) / pxy)
    return ys

def _coluna_dominante(caixas, tol=3.0):
    """Mantém só o cluster de x com mais elementos (a coluna de checkboxes)."""
    if not caixas:
        return []
    melhor_x, melhor_n = caixas[0]["cx"], 0
    for c in caixas:
        n = sum(1 for o in caixas if abs(o["cx"] - c["cx"]) <= tol)
        if n > melhor_n:
            melhor_x, melhor_n = c["cx"], n
    return [c for c in caixas if abs(c["cx"] - melhor_x) <= tol]

def _pitch(valores):
    if len(valores) < 2:
        return None
    v = sorted(valores)
    return float(np.median([b - a for a, b in zip(v, v[1:])]))

def _regressao(y, dy):
    if len(y) < 3:
        return None, None
    a, b = np.polyfit(y, dy, 1)
    return float(a), float(b)

def _veredito(ratios_obs, ratio_ref):
    def _desvio(r):
        return r is not None and abs(r - 1.0) > 0.04

    if _desvio(ratio_ref):
        return ("ESCALA DA PÁGINA: as linhas de critérios também divergem "
                f"(razão {ratio_ref:.3f}). O warp/homografia está comprimindo a "
                "página — revisar a geometria do QR e o refino por fiduciais.")
    if any(_desvio(r) for r in ratios_obs if r is not None):
        return ("BLOCO DE OBSERVAÇÕES: só as observações divergem (critérios OK). "
                "A seção 'observacoes' do config não casa com a folha impressa — "
                "recalibrar o bloco ou regerar as folhas.")
    return ("ALINHADO: sem divergência de escala relevante. O erro de leitura não "
            "é geométrico — investigar o limiar de classificação das caixas.")

def main() -> int:
    ap = argparse.ArgumentParser(description="Calibra ROIs de observações v2")
    ap.add_argument("--foto", required=True, type=Path)
    ap.add_argument("--faixa", required=True)
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/diagnostico"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    coords = omr_reader.carregar_json(
        args.config / "coordenadas" / f"{args.faixa}.json")
    obs = coords.get("observacoes", {})
    if not obs:
        print("[ERRO] sem seção 'observacoes' no JSON da faixa")
        return 2

    imagem = cv2.imread(str(args.foto))
    if imagem is None:
        print(f"[ERRO] não abriu {args.foto}")
        return 2
    alinhada = omr_reader.detectar_e_corrigir(imagem)
    h, w = alinhada.shape[:2]
    pxx, pxy = w / LARGURA_A4_MM, h / ALTURA_A4_MM
    print(f"Folha: {args.foto.name} | faixa {args.faixa} | alinhada {w}x{h}px "
          f"({pxx:.2f} x {pxy:.2f} px/mm)\n")

    overlay = alinhada.copy()
    ratios_obs: list[float | None] = []

    for col in ("p", "m"):
        chaves = [k for k in obs if k.startswith(f"obs_{col}")]
        if not chaves:
            continue
        x_ref = float(np.median([obs[k]["x"] + obs[k]["w"] / 2 for k in chaves]))
        y_min = min(obs[k]["y"] for k in chaves)
        y_max = max(obs[k]["y"] + obs[k]["h"] for k in chaves)

        caixas = _coluna_dominante(
            _quadrados(alinhada, x_ref - 8, x_ref + 8, y_min - 10, y_max + 10))
        print(f"--- Coluna '{col}' — {len(caixas)} checkboxes detectados "
              f"(de {len(chaves)} esperados) ---")
        print(f"{'chave':8s} {'y_esp':>8s} {'y_med':>8s} {'dy':>7s}")

        esperados = sorted(
            ({"chave": k,
              "ey": obs[k]["y"] + obs[k]["h"] / 2,
              "ex": obs[k]["x"] + obs[k]["w"] / 2} for k in chaves),
            key=lambda e: e["ey"])
        y_ok, dy_ok = [], []
        for e in esperados:
            if caixas:
                c = min(caixas, key=lambda o: abs(o["cy"] - e["ey"]))
                dy = c["cy"] - e["ey"]
                y_ok.append(e["ey"]); dy_ok.append(dy)
                print(f"{e['chave']:8s} {e['ey']:8.2f} {c['cy']:8.2f} {dy:+7.2f}")
                cv2.circle(overlay, (int(c["cx"] * pxx), int(c["cy"] * pxy)),
                           6, (255, 128, 0), -1)
            else:
                print(f"{e['chave']:8s} {e['ey']:8.2f} {'--':>8s} {'--':>7s}")
            cv2.rectangle(overlay,
                          (int((e["ex"] - 2.25) * pxx), int((e["ey"] - 2.25) * pxy)),
                          (int((e["ex"] + 2.25) * pxx), int((e["ey"] + 2.25) * pxy)),
                          (0, 0, 255), 2)

        passo_esp = _pitch([e["ey"] for e in esperados])
        passo_med = _pitch([c["cy"] for c in caixas]) if caixas else None
        razao = passo_med / passo_esp if (passo_esp and passo_med) else None
        ratios_obs.append(razao)
        incl, _ = _regressao(y_ok, dy_ok)
        print(f"  passo esperado {passo_esp:.2f} mm | medido "
              f"{passo_med:.2f} mm | razão {razao:.3f}" if razao
              else "  passo: dados insuficientes")
        if incl is not None:
            print(f"  inclinação do dy: {incl:+.4f} mm/mm "
                  f"({incl * 100:+.1f}% de erro de escala ao longo do bloco)")
        print()

    # --- referência de escala: linhas de critérios (8,5 mm no config) ---
    print("--- Referência de escala (linhas de critérios) ---")
    ratios_ref = []
    for quesito, x0, x1 in COLUNAS_CRITERIOS:
        rows = sorted(coords.get(quesito, {}).values(), key=lambda r: r["y"])
        if len(rows) < 3:
            continue
        y0 = rows[0]["y"] - 6
        y1 = rows[-1]["y"] + rows[-1]["h"] + 6
        med = _barras(alinhada, x0, x1, y0, y1)
        if len(med) < 3:
            med = _rows_de_quadrados(alinhada, x0, x1, y0, y1)
        esp_esp = _pitch([r["y"] + r["h"] / 2 for r in rows])
        esp_med = _pitch(med)
        if esp_esp and esp_med:
            ratio = esp_med / esp_esp
            ratios_ref.append(ratio)
            print(f"  {quesito:7s} esperado {esp_esp:.2f} mm | medido "
                  f"{esp_med:.2f} mm | razão {ratio:.3f} "
                  f"({len(med)} linhas detectadas)")
        else:
            print(f"  {quesito:7s} não foi possível medir ({len(med)} linhas)")

    ratio_ref = float(np.median(ratios_ref)) if ratios_ref else None
    print()
    print("Veredito:")
    print(f"  {_veredito(ratios_obs, ratio_ref)}")

    saida = args.out / f"{args.foto.stem}_calibra.png"
    cv2.imwrite(str(saida), overlay)
    print(f"\nOverlay salvo: {saida} (vermelho = esperado, azul = medido)")
    return 0

def _rows_de_quadrados(alinhada, x0, x1, y0, y1, tol=2.5):
    """Fallback: agrupa quadrados em linhas e devolve os centros."""
    caixas = _quadrados(alinhada, x0, x1, y0, y1)
    ordenadas = sorted(caixas, key=lambda c: c["cy"])
    linhas, atual = [], []
    for c in ordenadas:
        if not atual or c["cy"] - atual[-1]["cy"] <= tol:
            atual.append(c)
        else:
            linhas.append(atual); atual = [c]
    if atual:
        linhas.append(atual)
    return [float(np.mean([c["cy"] for c in ln]))
            for ln in linhas if len(ln) >= 3]

if __name__ == "__main__":
    raise SystemExit(main())