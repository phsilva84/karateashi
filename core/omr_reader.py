"""core/omr_reader.py — Leitura OMR por busca local (Karate-Ashi v3.27.6).
Semântica do domínio (definida pelo usuário):
- O avaliador marca TODOS os balões que observou (1..5 por critério);
  cada balão preenchido = 1 ocorrência do erro. 5/5 é legítimo.
- Frequência do critério = CONTAGEM de balões marcados (0..5), lidos
  INDEPENDENTEMENTE pelo interior do balão.
Padrão rbaron/omr + OMRChecker (skill "Leitura OMR por Busca Local"):
- PROIBIDO fiduciais/cruzes. Desalinhamento por BUSCA LOCAL por balão
  (janela ±3mm; presença ±5mm). QR via zxing-cpp (primário) + pyzbar.
- Scan A4 -> resize direto 3508x2480; warp só se não for A4.

Calibração:
- v3.23/v3.24: (1) seed por QR (dx); (2) alinhamento vertical por
  DESLOCAMENTO GLOBAL; (3) v3.24: dy da PÁGINA por VOTO MAJORITÁRIO.
- v3.27 (scan img20261004_00471691): seed do QR dava dy ~+3mm ESPÚRIO;
  a grade dava ~-0,4mm (verdade visual). FIX: grade vence quando
  |dy_grade| <= meio pitch (2,45mm); seed do QR vale APENAS para dx.
  PRESENÇA: removida a varredura cega (gerava falso PRESENTE na W06).
- v3.27.1: (a) FREQUÊNCIA mede o interior padrão (RECUO_FREQ 0.20,
  raio 0.80r); PRESENÇA estrita (RECUO 0.65) p/ não regredir W06;
  (b) version stamp (omr_reader_version); (c) incidente
  'ausencia_com_marcas:N' em AUSENTE com balões marcados.
- v3.27.2: quando a grade é inconclusiva/ausente, dy via OFFSET POR LINHA
  em vez de zero cego (resgatou W09 de 11162992). GREEN: golden 14/14.
- v3.27.3 (NÃO COMMITAR — regressão): candidatos linha->grade->seed->zero
  REGREDIU (seed marcava disco em folha em branco; 72 células alteradas).
- v3.27.4 (diag_presenca): presença-oráculo linha<->grade SEM gate, seed só
  no dx. GREEN 14/14. Ficou POR ALUNO -> mesma folha podia usar dy
  diferentes (W07/W08 grade -2,60 vs W09 linha +1,25) -> Eloah caiu 1 linha.
- v3.27.5 (divergência conferida à mão): OFFSET ÚNICO POR FOLHA por VOTO DE
  PRESENÇA na página inteira. GREEN 14/14; Eloah Kihon corrigido 6/6.
  Evidência diag_rotacao: 11162992 é PLANA (slope ~-0,001, drift -0,2mm) —
  o "pulo de linha" restante em Kata/Bunkai/Kumite da Eloah era do v3.27.4.
  22032837 é ROTACIONADA (slope -0,0048, drift -1,0mm no Kumite) e um dy só
  não corrige: colunas à direita medem com erro ~1mm -> falsos positivos
  (Kumite Kiai 1/2/1, Bunkai Base 5 vs 3 — tinta real não existe).
- v3.27.6 (diag_rotacao/diag_bloco): FIX de ROTAÇÃO com GATE — mede o dy da
  grade por coluna (kihon/kata/bunkai/kumite x=44/113/182/252), ajusta reta
  por mínimos quadrados e ativa dy(x) linear SÓ se 0.003 <= |slope| <= 0.006.
  Páginas planas (golden 22490841, 11162992) seguem com o dy votado do
  v3.27.5. + BAND SNAPPING na frequência: anel achado em banda vizinha
  (> 0.37*pitch de resíduo) é deslocado para a banda correta (período 4.9mm)
  — proteção universal contra aliasing de pitch. Presença segue pelo voto
  por página; seed nunca vota no dy; W06 AUSENTE preservada.
  CORREÇÃO PÓS-APLICAÇÃO: a coleta de ys POR COLUNA agregava só os 5 balões
  de UM critério (mesma linha -> ys com 1 valor -> len<2 -> coluna nunca
  medida -> rot_on sempre False). FIX: col_ys[q] agora acumula o y_mm de
  TODOS os critérios do quesito (todos os alunos), igual ao diag_rotacao —
  só assim a grade de cada coluna é medida e a rotação ativa de verdade.
Regras: presença não marcada -> AUSENTE; módulo <= ~400 linhas.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from core import observacoes
from core.config import QUESITOS, carregar_json

OMR_READER_VERSION = "v3.27.6"
A4_W_PX, A4_H_PX = 3508, 2480
A4_W_MM, A4_H_MM = 297.0, 210.0
RAZAO_MIN, RAZAO_MAX = 1.30, 1.55
JANELA_MM = 3.0          # janela da busca local (mm)
JANELA_PRESENCA_MM = 5.0 # janela ampliada p/ presenca
RECUO = 0.65             # PRESENCA: disco central estrito (raio 0.35r)
RECUO_FREQ = 0.20        # FREQUENCIA: interior padrão (raio 0.80r)
LIM_MARCADO = (0.30, 0.25)
LIM_VAZIO = (0.15, 0.08)
LIM_DISCO = (0.40, 0.32)
FREQ_BALOES = 5
_OFFSET_MAX_MM = 5.0
POS_QRS_ALUNO_MM = [(200.5, 14.8), (219.5, 14.8), (238.5, 14.8)]
LIMIAR_SEED_QR_MM = 1.0
PITCH_MM = 4.9
SLOPE_MIN_ROT = 0.003       # v3.27.6: gate mínimo de rotação (mm/mm)
SLOPE_MAX_ROT = 0.006       # v3.27.6: teto anti-louco (grade aliased)
BANDA_MAX_MM = PITCH_MM * 0.37  # v3.27.6: banda vizinha > 1.81mm é snap
_QR_EXAME = re.compile(r"KA\|AVALIADOR=([^|]+)\|DOJO=([^|]+)\|EXAME=([^|]+)")
_QR_ALUNO = re.compile(r"KA\|ALUNO=([^|]+)\|FAIXA=([^|]+)")

# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------
def carregar_imagem(caminho: Path) -> np.ndarray:
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pagina = pdfium.PdfDocument(str(caminho))[0]
        bmp = pagina.render(scale=300 / 72)
        arr = np.frombuffer(bmp.to_bits(), dtype=np.uint8).reshape(
            bmp.height, bmp.width, bmp.n_channels)
        return arr[..., :3][:, :, ::-1]
    img = cv2.imread(str(caminho), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"nao foi possivel ler a imagem: {caminho}")
    return img

def _cinza(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def _ordenar_pontos(pts: np.ndarray) -> np.ndarray:
    soma = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    return np.float32([pts[np.argmin(soma)], pts[np.argmin(diff)],
                       pts[np.argmax(soma)], pts[np.argmax(diff)]])

def normalizar_a4(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    razao = (w / h) if h else 0.0
    if RAZAO_MIN <= razao <= RAZAO_MAX:
        return cv2.resize(img, (A4_W_PX, A4_H_PX),
                          interpolation=cv2.INTER_AREA)
    cinza = _cinza(img)
    _, binaria = cv2.threshold(cinza, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return cv2.resize(img, (A4_W_PX, A4_H_PX))
    maior = max(contornos, key=cv2.contourArea)
    per = cv2.arcLength(maior, True)
    aprox = cv2.approxPolyDP(maior, 0.02 * per, True)
    if len(aprox) != 4:
        return cv2.resize(img, (A4_W_PX, A4_H_PX))
    origem = _ordenar_pontos(aprox.reshape(4, 2))
    destino = np.float32([[0, 0], [A4_W_PX, 0],
                          [A4_W_PX, A4_H_PX], [0, A4_H_PX]])
    M = cv2.getPerspectiveTransform(origem, destino)
    return cv2.warpPerspective(img, M, (A4_W_PX, A4_H_PX))

# ---------------------------------------------------------------------------
# QR
# ---------------------------------------------------------------------------
def _ler_qrs(imagem: np.ndarray) -> list[tuple[str, tuple[int, int, int, int]]]:
    cinza = _cinza(imagem)
    h, w = cinza.shape[:2]
    saida: list[tuple[str, tuple[int, int, int, int]]] = []

    def _append(texto: str, box: tuple[int, int, int, int]) -> None:
        if not any(t == texto for t, _ in saida):
            saida.append((texto, box))

    try:
        from zxingcpp import read_barcodes
        for fator in (1, 2, 3):
            base = cinza if fator == 1 else cv2.resize(
                cinza, (w * fator, h * fator),
                interpolation=cv2.INTER_CUBIC)
            try:
                for bar in read_barcodes(base):
                    if bar.format.name != "QRCode":
                        continue
                    pts = [bar.position.top_left, bar.position.top_right,
                           bar.position.bottom_left, bar.position.bottom_right]
                    xs = [int(p.x) for p in pts]
                    ys = [int(p.y) for p in pts]
                    x0, x1 = min(xs), max(xs)
                    y0, y1 = min(ys), max(ys)
                    _append(bar.text, (int(x0 / fator), int(y0 / fator),
                                       int((x1 - x0) / fator),
                                       int((y1 - y0) / fator)))
            except Exception:  # noqa: BLE001
                continue
        if saida:
            return saida
    except ImportError:
        pass
    try:
        from pyzbar import pyzbar
    except ImportError:
        det = cv2.QRCodeDetector()
        texto, pts, _ = det.detectAndDecode(imagem)
        if texto and pts is not None:
            box = pts[0].astype(int).reshape(-1, 2)
            x0, y0 = box.min(axis=0)
            x1, y1 = box.max(axis=0)
            _append(texto, (int(x0), int(y0),
                            int(x1 - x0), int(y1 - y0)))
        return saida
    _, otsu = cv2.threshold(cinza, 0, 255,
                            cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adapt51 = cv2.adaptiveThreshold(cinza, 255,
                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 51, 15)
    adapt101 = cv2.adaptiveThreshold(cinza, 255,
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 101, 10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cinza)
    variantes: list[tuple[str, np.ndarray, float]] = [
        ("orig", cinza, 1.0),
        ("2x", cv2.resize(cinza, (w * 2, h * 2),
                          interpolation=cv2.INTER_CUBIC), 2.0),
        ("3x", cv2.resize(cinza, (w * 3, h * 3),
                          interpolation=cv2.INTER_CUBIC), 3.0),
        ("otsu", otsu, 1.0),
        ("adapt51", adapt51, 1.0),
        ("adapt101", adapt101, 1.0),
        ("clahe", clahe, 1.0),
    ]
    for nome, img_v, fator in variantes:  # noqa: B007
        for qr in pyzbar.decode(img_v):
            texto = qr.data.decode("utf-8", "replace")
            x, y, wq, hq = qr.rect
            _append(texto, (int(x / fator), int(y / fator),
                            int(wq / fator), int(hq / fator)))
        if saida:
            break
    return saida

def _payload_por_prefixo(imagem: np.ndarray, prefixo: str) -> str | None:
    for texto, _ in _ler_qrs(imagem):
        if texto.startswith(f"KA|{prefixo}"):
            return texto
    return None

def _ler_alunos_do_qr(a4: np.ndarray) -> list[tuple[str, str]]:
    alunos = []
    for texto, (x, _, _, _) in _ler_qrs(a4):
        m = _QR_ALUNO.search(texto)
        if m:
            alunos.append((x, m.group(1), m.group(2)))
    alunos.sort(key=lambda t: t[0])
    return [(a, f) for _, a, f in alunos]

# ---------------------------------------------------------------------------
# Busca local + medicao
# ---------------------------------------------------------------------------
def _achar_anel(cinza: np.ndarray, cx: float, cy: float, r: float,
                janela_px: float) -> tuple[float, float, float] | None:
    x0, y0 = max(0, int(cx - janela_px)), max(0, int(cy - janela_px))
    x1 = min(cinza.shape[1], int(cx + janela_px + 1))
    y1 = min(cinza.shape[0], int(cy + janela_px + 1))
    recorte = cinza[y0:y1, x0:x1]
    if recorte.size == 0:
        return None
    _, binaria = cv2.threshold(recorte, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    raio_min, raio_max = r * 0.6, r * 1.4
    contornos, _ = cv2.findContours(binaria, cv2.RETR_LIST,
                                    cv2.CHAIN_APPROX_SIMPLE)
    melhor: tuple[float, float, float] | None = None
    melhor_dist = float("inf")
    for c in contornos:
        if len(c) < 8:
            continue
        per = cv2.arcLength(c, True)
        area = cv2.contourArea(c)
        if area <= 0 or per <= 0:
            continue
        circularidade = 4 * np.pi * area / (per * per)
        if circularidade < 0.40:
            continue
        (mx, my), mr = cv2.minEnclosingCircle(c)
        if mr < raio_min or mr > raio_max:
            continue
        dist = abs(mx + x0 - cx) + abs(my + y0 - cy)
        if dist < melhor_dist:
            melhor_dist = dist
            melhor = (mx + x0, my + y0, mr)
    if melhor is not None:
        return melhor
    n, _, stats, _ = cv2.connectedComponentsWithStats(binaria)
    candidatos = [(i, stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)]
    if not candidatos:
        return None
    i = max(candidatos, key=lambda t: t[1])[0]
    w = stats[i, cv2.CC_STAT_WIDTH]
    h = stats[i, cv2.CC_STAT_HEIGHT]
    if max(w, h) > 2.5 * min(w, h):
        return None
    centro = (x0 + stats[i, cv2.CC_STAT_LEFT] + w / 2.0,
              y0 + stats[i, cv2.CC_STAT_TOP] + h / 2.0)
    raio = max(w, h) / 2.0
    if raio < raio_min or raio > raio_max:
        return None
    if abs(centro[0] - cx) + abs(centro[1] - cy) > janela_px + r * 0.6:
        return None
    return (centro[0], centro[1], raio)

def _medir(cinza: np.ndarray, cx: float, cy: float, r: float,
           recuo: float = RECUO) -> tuple[float, float]:
    ri = r * (1.0 - recuo)
    x0, y0 = max(0, int(cx - ri)), max(0, int(cy - ri))
    x1 = min(cinza.shape[1], int(cx + ri + 1))
    y1 = min(cinza.shape[0], int(cy + ri + 1))
    recorte = cinza[y0:y1, x0:x1]
    if recorte.size == 0:
        return 0.0, 0.0
    _, binaria = cv2.threshold(recorte, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mascara = np.zeros(recorte.shape[:2], np.uint8)
    cv2.circle(mascara, (int(ri), int(ri)), int(ri), 255, -1)
    dentro = int(np.count_nonzero(mascara))
    if dentro == 0:
        return 0.0, 0.0
    escuros = cv2.bitwise_and(binaria, mascara)
    taxa = float(np.count_nonzero(escuros)) / dentro
    n, rotulos = cv2.connectedComponents(escuros)
    if n <= 1:
        blob = 0.0
    else:
        areas = np.bincount(rotulos.ravel())
        blob = float(areas[1:].max()) / dentro
    return taxa, blob

def classificar_checkbox(taxa: float, blob: float) -> str:
    if taxa >= LIM_MARCADO[0] and blob >= LIM_MARCADO[1]:
        return "marcado"
    if taxa < LIM_VAZIO[0] and blob < LIM_VAZIO[1]:
        return "vazio"
    return "suspeito"

def _calibrar_offset(cinza: np.ndarray, baloes: list[dict], escala: float,
                     janela_px: float) -> tuple[float, float]:
    passo = max(1, len(baloes) // 30)
    amostra = baloes[::passo][:36]
    desvios: list[tuple[float, float]] = []
    for balao in amostra:
        anel = _achar_anel(cinza, balao["x_mm"] * escala,
                           balao["y_mm"] * escala,
                           balao["r_mm"] * escala, janela_px)
        if anel is None:
            continue
        desvios.append(((anel[0] - balao["x_mm"] * escala) / escala,
                        (anel[1] - balao["y_mm"] * escala) / escala))
    if len(desvios) < 8:
        return 0.0, 0.0
    dx = float(np.median([d[0] for d in desvios]))
    dy = float(np.median([d[1] for d in desvios]))
    if abs(dx) > _OFFSET_MAX_MM or abs(dy) > _OFFSET_MAX_MM:
        return 0.0, 0.0
    return dx, dy

def _calibrar_offset_por_qr(a4: np.ndarray, escala: float) -> tuple[float, float]:
    dxs, dys = [], []
    for texto, (x, y, w, h) in _ler_qrs(a4):
        if _QR_ALUNO.search(texto) is None:
            continue
        cx, cy = (x + w / 2.0) / escala, (y + h / 2.0) / escala
        ex, ey = min(POS_QRS_ALUNO_MM, key=lambda p: abs(p[0] - cx))
        dxs.append(cx - ex)
        dys.append(cy - ey)
    if len(dxs) < 2:
        return 0.0, 0.0
    dx, dy = float(np.median(dxs)), float(np.median(dys))
    if abs(dx) > _OFFSET_MAX_MM or abs(dy) > _OFFSET_MAX_MM:
        return 0.0, 0.0
    return dx, dy

def _offset_por_linha(cinza: np.ndarray, baloes_linha: list[dict],
                      escala: float, janela_px: float,
                      dx0: float, dy0: float) -> tuple[float, float]:
    desvios: list[tuple[float, float]] = []
    for b in baloes_linha:
        anel = _achar_anel(cinza, (b["x_mm"] + dx0) * escala,
                           (b["y_mm"] + dy0) * escala,
                           b["r_mm"] * escala, janela_px)
        if anel is None:
            continue
        desvios.append(((anel[0] - (b["x_mm"] + dx0) * escala) / escala,
                        (anel[1] - (b["y_mm"] + dy0) * escala) / escala))
    if len(desvios) < 5:
        return dx0, dy0
    dx = float(np.median([d[0] for d in desvios]))
    dy = float(np.median([d[1] for d in desvios]))
    if abs(dx) > _OFFSET_MAX_MM or abs(dy) > _OFFSET_MAX_MM:
        return dx0, dy0
    return dx0 + dx, dy0 + dy

# ---------------------------------------------------------------------------
# DETECÇÃO DO GRID REAL DE LINHAS
# ---------------------------------------------------------------------------
def _detectar_linhas(cinza: np.ndarray, x_mm: float, escala: float,
                     y_min: float, y_max: float) -> list[float]:
    cx = int(x_mm * escala)
    faixa = cinza[max(0, int(y_min * escala)):int(y_max * escala),
                  max(0, cx - 30):cx + 30]
    if faixa.size == 0:
        return []
    _, bin_ = cv2.threshold(faixa, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    n, _, stats, cent = cv2.connectedComponentsWithStats(bin_, 8)
    ys: list[float] = []
    for i in range(1, n):
        w = int(stats[i, cv2.CC_STAT_WIDTH])
        h = int(stats[i, cv2.CC_STAT_HEIGHT])
        if not (12 <= h <= 70 and 12 <= w <= 70):
            continue
        ys.append((float(cent[i, 1]) + int(y_min * escala)) / escala)
    ys.sort()
    grupos: list[list[float]] = []
    for y in ys:
        if grupos and abs(y - grupos[-1][-1]) < 2.0:
            grupos[-1].append(y)
        else:
            grupos.append([y])
    return [float(np.mean(g)) for g in grupos]

def _offset_vertical_por_grade(cinza: np.ndarray, x_mm: float,
                               y_esperadas: list[float],
                               escala: float) -> float | None:
    tol = 0.8  # mm
    y0 = min(y_esperadas) - 5.0
    y1 = max(y_esperadas) + 5.0
    det = _detectar_linhas(cinza, x_mm, escala, y0, y1)
    if len(det) < 2:
        return None
    melhor_n = -1
    melhor_dy: float | None = None
    passo = 0.1
    dy_c = -_OFFSET_MAX_MM
    while dy_c <= _OFFSET_MAX_MM + 1e-9:
        n = 0
        for y_exp in y_esperadas:
            for d in det:
                if abs(d - (y_exp + dy_c)) <= tol:
                    n += 1
                    break
        if (n > melhor_n or (n == melhor_n and melhor_dy is not None
                             and abs(dy_c) < abs(melhor_dy))):
            melhor_n = n
            melhor_dy = float(dy_c)
        dy_c += passo
    if melhor_dy is None or melhor_n < max(2, int(len(y_esperadas) * 0.5)):
        return None
    if abs(melhor_dy) > _OFFSET_MAX_MM:
        return None
    return melhor_dy

def _densidade_balao(cinza: np.ndarray, balao: dict, escala: float,
                     janela_px: float, dx_mm: float = 0.0,
                     dy_mm: float = 0.0) -> tuple[float, float]:
    cx = (balao["x_mm"] + dx_mm) * escala
    cy = (balao["y_mm"] + dy_mm) * escala
    r = balao["r_mm"] * escala
    anel = _achar_anel(cinza, cx, cy, r, janela_px)
    if anel is not None:
        # v3.27.6: BAND SNAPPING — se o anel caiu em banda vizinha (resíduo
        # > 0.37*pitch), desloca o centro de medição para a banda correta.
        d = anel[1] / escala - (balao["y_mm"] + dy_mm)
        k = int(round(d / PITCH_MM))
        if k != 0 and abs(d) > BANDA_MAX_MM:
            cy_med = anel[1] - k * PITCH_MM * escala
            taxa, blob = _medir(cinza, anel[0], cy_med, anel[2],
                                recuo=RECUO_FREQ)
            if taxa >= LIM_MARCADO[0] or taxa >= LIM_VAZIO[0]:
                return taxa, blob
        return _medir(cinza, anel[0], anel[1], anel[2], recuo=RECUO_FREQ)
    return _medir(cinza, cx, cy, r, recuo=RECUO_FREQ)

# ---------------------------------------------------------------------------
# Presença / observações (v3.27 — SEM varredura cega)
# ---------------------------------------------------------------------------
def _estado_disco(cinza: np.ndarray, balao: dict, escala: float,
                  janela_px: float, dx_mm: float = 0.0, dy_mm: float = 0.0,
                  janela_mm: float = JANELA_MM) -> tuple[str, list[str]]:
    """Disco sólido no CENTRO (recuo exclui o anel; limiar ALTO).
    v3.27 — SEM varredura cega: mede apenas o disco central na posição
    pedida (offset aplicado) ou no anel encontrado. Centro limpo -> vazio
    -> AUSENTE.
    """
    cx = (balao["x_mm"] + dx_mm) * escala
    cy = (balao["y_mm"] + dy_mm) * escala
    r = balao["r_mm"] * escala
    jpx = janela_mm * escala
    anel = _achar_anel(cinza, cx, cy, r, jpx)
    if anel is not None:
        taxa, blob = _medir(cinza, anel[0], anel[1], anel[2])
        if taxa >= LIM_DISCO[0] and blob >= LIM_DISCO[1]:
            return "marcado", (["disco_sem_anel"] if taxa >= 0.75 else [])
        if taxa < LIM_VAZIO[0] and blob < LIM_VAZIO[1]:
            return "vazio", []
    taxa, blob = _medir(cinza, cx, cy, r)
    if taxa >= LIM_DISCO[0] and blob >= LIM_DISCO[1]:
        return "marcado", (["disco_sem_anel"] if taxa >= 0.75 else [])
    if taxa < LIM_VAZIO[0] and blob < LIM_VAZIO[1]:
        return "vazio", []
    return "suspeito", ["anel_nao_encontrado"]

def _frequencia(densidades: list[tuple[float, float]]) -> tuple[int, list[str]]:
    marcados = 0
    avisos: list[str] = []
    for taxa, blob in densidades:
        est = classificar_checkbox(taxa, blob)
        if est == "marcado":
            marcados += 1
        elif est == "suspeito":
            avisos.append("suspeito")
    return marcados, avisos

def _anular_contradicoes(marcadas: set[str], incidentes: list[str]) -> None:
    for i in range(1, 7):
        p, m = f"obs_p{i}", f"obs_m{i}"
        if p in marcadas and m in marcadas:
            marcadas.discard(p)
            marcadas.discard(m)
            incidentes.append(f"contradicao:{p}/{m}")

# ---------------------------------------------------------------------------
# Coordenadas
# ---------------------------------------------------------------------------
def _carregar_coordenadas(pasta: Path, exame: str,
                          avaliador: str) -> dict | None:
    candidatos = sorted(pasta.glob(f"{exame}_{avaliador}_coordenadas.json"))
    if not candidatos:
        candidatos = sorted(pasta.glob(f"{exame}_{avaliador}_*_coordenadas.json"))
    if not candidatos:
        return None
    return carregar_json(candidatos[0])

# ---------------------------------------------------------------------------
# Fluxo completo
# ---------------------------------------------------------------------------
def processar_imagem(caminho_imagem: Path, base_cfg: Path | None = None,
                     faixa: str | None = None,
                     origem: str | None = None,
                     pagina_por_ordem: int | None = None,
                     aplicar_offset: bool = False) -> list[dict]:
    imagem = carregar_imagem(caminho_imagem)
    m = _QR_EXAME.search(_payload_por_prefixo(imagem, "AVALIADOR") or "")
    if not m:
        raise ValueError("QR do exame nao encontrado "
                         "(KA|AVALIADOR=..|DOJO=..|EXAME=..)")
    avaliador, dojo, exame = m.group(1), m.group(2), m.group(3)
    a4 = normalizar_a4(imagem)
    cinza = _cinza(a4)
    escala = A4_W_PX / A4_W_MM
    janela_px = JANELA_MM * escala
    raiz = (base_cfg.parent if base_cfg and base_cfg.name == "config"
            else Path("."))
    coords = _carregar_coordenadas(raiz / "output" / "pre_exame",
                                   exame, avaliador)
    if coords is None:
        raise ValueError(
            f"JSON de coordenadas nao encontrado em output/pre_exame/ "
            f"({exame}_{avaliador}_*_coordenadas.json). Gere a folha com "
            f"tools/pre_exame.py e digitalize o PDF gerado.")
    por_pag: dict[int, set] = {}
    for a in coords["alunos"]:
        por_pag.setdefault(a.get("pagina", 1), set()).add(a["id"])
    paginas_json = sorted(por_pag)
    ids_lidos = {aid for aid, _ in _ler_alunos_do_qr(a4)}
    pagina_por_qr = None
    if ids_lidos:
        candidatas = [p for p, ids in por_pag.items()
                      if ids_lidos <= ids]
        if len(candidatas) == 1:
            pagina_por_qr = candidatas[0]
    alunos = coords["alunos"]
    ids_pagina: list[str] = []
    uso_ordem = False
    if pagina_por_qr is not None:
        alunos = [a for a in alunos if a.get("pagina", 1) == pagina_por_qr]
        ids_pagina = sorted(por_pag[pagina_por_qr])
    elif pagina_por_ordem is not None:
        alunos = [a for a in alunos
                  if a.get("pagina", 1) == pagina_por_ordem]
        if not alunos:
            raise ValueError(
                f"pagina {pagina_por_ordem} nao existe no JSON de "
                f"coordenadas (paginas: {','.join(map(str, paginas_json))}).")
        uso_ordem = True
    elif len(paginas_json) == 1:
        pass
    else:
        raise ValueError(
            "QRs de aluno nao lidos e o JSON tem multiplas paginas "
            f"({','.join(map(str, paginas_json))}).")
    amostra: list[dict] = []
    for aluno in alunos:
        amostra.append(aluno["presenca"])
        for baloes in aluno.get("frequencias", {}).values():
            amostra.extend(baloes)
    dx_mm, dy_mm = _calibrar_offset_por_qr(a4, escala)
    fonte_off = "_qr"
    if dx_mm == 0.0 and dy_mm == 0.0:
        dx_mm, dy_mm = _calibrar_offset(cinza, amostra, escala, janela_px)
        fonte_off = ""
    # --- v3.27.6: dy da grade POR COLUNA (kihon/kata/bunkai/kumite) ---------
    # CORREÇÃO: col_ys[q] acumula o y_mm de TODOS os critérios do quesito
    # (todos os alunos), igual ao diag_rotacao — antes só pegava os 5 balões
    # de um critério (mesma linha -> ys com 1 valor -> len<2 -> coluna nunca
    # medida -> rot_on sempre False).
    col_xs: dict[str, float] = {}
    col_ys: dict[str, set] = {}
    for ap in alunos:
        for ch, baloes in ap.get("frequencias", {}).items():
            q = ch.split("_", 1)[0]
            col_xs.setdefault(q, min(b["x_mm"] for b in baloes))
            col_ys.setdefault(q, set()).update(
                b["y_mm"] for b in baloes
                if isinstance(b, dict) and "y_mm" in b)
    col_dys: dict[str, float] = {}
    for q in col_xs:
        ys = sorted(col_ys[q])
        if len(ys) < 2:          # precisa de >=2 linhas p/ medir a grade
            continue
        dy_g = _offset_vertical_por_grade(cinza, col_xs[q], ys, escala)
        if dy_g is not None:
            col_dys[q] = dy_g
    rot_slope = 0.0
    rot_on = False
    if len(col_dys) >= 3:
        xs = [col_xs[q] for q in col_dys]
        dys = [col_dys[q] for q in col_dys]
        mx = sum(xs) / len(xs)
        my = sum(dys) / len(dys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 1e-9:
            rot_slope = sum((x - mx) * (y - my)
                            for x, y in zip(xs, dys)) / den
            if SLOPE_MIN_ROT <= abs(rot_slope) <= SLOPE_MAX_ROT:
                rot_on = True
    # --- v3.24: dy da PÁGINA por VOTO MAJORITÁRIO entre os alunos ----------
    dy_votos: dict[float, int] = {}
    for ap in alunos:
        y_esp = sorted({pos["y_mm"]
                        for ch in ap.get("frequencias", {})
                        for pos in ap["frequencias"][ch]
                        if isinstance(pos, dict) and "y_mm" in pos})
        if len(y_esp) < 2 or not ap.get("frequencias"):
            continue
        x_g = min(ap["frequencias"][ch][0]["x_mm"]
                  for ch in ap["frequencias"]
                  if ap["frequencias"][ch])
        dy_g = _offset_vertical_por_grade(cinza, x_g, y_esp, escala)
        if dy_g is None:
            continue
        chave = round(dy_g, 1)
        dy_votos[chave] = dy_votos.get(chave, 0) + 1
    dy_grade: float | None = None
    if dy_votos:
        melhor_n = max(dy_votos.values())
        empatados = [dy for dy, n in dy_votos.items() if n == melhor_n]
        dy_grade = float(min(empatados, key=abs))

    # --- v3.27.5: OFFSET ÚNICO POR FOLHA por VOTO DE PRESENÇA --------------
    baloes_linha_folha: list[dict] = []
    for ap in alunos:
        baloes_linha_folha.append(ap["presenca"])
        for baloes in ap.get("frequencias", {}).values():
            baloes_linha_folha.extend(baloes)
        baloes_linha_folha.extend(ap.get("observacoes", {}).values())
    dx_linha, dy_linha = _offset_por_linha(cinza, baloes_linha_folha, escala,
                                           janela_px, dx_mm, 0.0)
    candidatos_folha: list[tuple[str, float, float]] = []
    if (dx_linha, dy_linha) != (dx_mm, 0.0):
        candidatos_folha.append(("linha", dx_linha, dy_linha))
    if dy_grade is not None:
        candidatos_folha.append(("grade", dx_mm, dy_grade))
    if not candidatos_folha:
        candidatos_folha.append(("zero", dx_mm, 0.0))

    def _conta_presenca(dx_c: float, dy_c: float) -> int:
        n = 0
        for ap in alunos:
            p, _ = _estado_disco(cinza, ap["presenca"], escala, janela_px,
                                 dx_c, dy_c, janela_mm=JANELA_PRESENCA_MM)
            if p == "marcado":
                n += 1
        return n

    melhor_c = candidatos_folha[0]
    melhor_n = -1
    for nome_c, dx_c, dy_c in candidatos_folha:
        n = _conta_presenca(dx_c, dy_c)
        if (n > melhor_n or (n == melhor_n
                             and abs(dy_c) < abs(melhor_c[2]))):
            melhor_n = n
            melhor_c = (nome_c, dx_c, dy_c)
    dx_folha, dy_folha, fonte_dy = melhor_c[1], melhor_c[2], melhor_c[0]
    if melhor_n <= 0:
        dx_folha, dy_folha, fonte_dy = dx_mm, 0.0, "sem_presenca"

    # --- v3.27.6: dy(x) — reta de rotação OU dy único ----------------------
    order = sorted(col_xs, key=lambda q: col_xs[q])

    def _dy_em(x_mm: float) -> float:
        if not rot_on or len(order) < 2:
            return dy_folha
        xs = [col_xs[q] for q in order]
        dys = [col_dys[q] for q in order]
        if x_mm <= xs[0]:
            return dys[0]
        if x_mm >= xs[-1]:
            return dys[-1]
        for i in range(len(xs) - 1):
            if xs[i] <= x_mm <= xs[i + 1]:
                t = (x_mm - xs[i]) / (xs[i + 1] - xs[i])
                return dys[i] + t * (dys[i + 1] - dys[i])
        return dy_folha

    resultados = []
    for aluno in alunos:
        aluno_id = aluno["id"]
        faixa_aluno = (faixa or aluno.get("faixa") or "branca").strip().lower()
        incidentes = ["origem:" + (origem or "desconhecida"),
                      f"omr_reader:{OMR_READER_VERSION}"]
        if pagina_por_qr is not None:
            incidentes.append(f"qrs_pagina:{','.join(ids_pagina)}")
        elif uso_ordem:
            incidentes.append(f"pagina_por_ordem:{pagina_por_ordem}")
        if dx_mm or dy_mm:
            incidentes.append(
                f"calibracao_offset{fonte_off}:dx={dx_mm:.2f},dy={dy_mm:.2f}")
        if (dx_folha, dy_folha) != (dx_mm, dy_mm):
            incidentes.append(
                f"calibracao_offset_linha:dx={dx_folha:.2f},dy={dy_folha:.2f} "
                f"(fonte={fonte_dy},votos={melhor_n})")
        if rot_on:
            drift_k = rot_slope * (col_xs.get("kumite", 251.8)
                                   - col_xs.get("kihon", 44.0))
            incidentes.append(
                f"rotacao_acumulada:slope={rot_slope:.5f},"
                f"drift_kumite_mm={drift_k:+.2f}")
        if aplicar_offset and (dx_folha or dy_folha):
            incidentes.append(
                f"offset_aplicado:dx={dx_folha:.2f},dy={dy_folha:.2f}")
        # presença: dy na posição x do disco de presença
        dx_p = dx_folha
        dy_p = _dy_em(aluno["presenca"]["x_mm"])
        pres, inc_p = _estado_disco(cinza, aluno["presenca"], escala,
                                    janela_px, dx_p, dy_p,
                                    janela_mm=JANELA_PRESENCA_MM)
        incidentes.extend(f"presenca:{i}" for i in inc_p)
        if pres != "marcado":
            n_marcas = sum(
                classificar_checkbox(*_densidade_balao(
                    cinza, b, escala, janela_px,
                    dx_folha, _dy_em(b["x_mm"]))) == "marcado"
                for baloes in aluno.get("frequencias", {}).values()
                for b in baloes)
            if n_marcas:
                incidentes.append(f"ausencia_com_marcas:{n_marcas}")
            resultados.append({
                "metadados": {"exame_id": exame, "avaliador_id": avaliador,
                              "dojo_id": dojo, "aluno_id": aluno_id,
                              "faixa": faixa_aluno, "pagina": aluno.get("pagina", 1)},
                "aluno": {"id": aluno_id, "faixa_atual": faixa_aluno.title()},
                "presenca": "AUSENTE",
                "avaliacoes": {q: {"frequencias": {}, "observacao": ""}
                               for q in QUESITOS},
                "observacoes_marcadas": [],
                "observacao_montada": "",
                "origem": origem,
                "incidentes_auditoria": incidentes,
                "omr_reader_version": OMR_READER_VERSION,
            })
            continue
        avaliacoes: dict[str, dict] = {q: {"frequencias": {},
                                           "observacao": ""}
                                       for q in QUESITOS}
        for chave, baloes in aluno.get("frequencias", {}).items():
            quesito, _, criterio = chave.partition("_")
            if quesito not in avaliacoes or len(baloes) != FREQ_BALOES:
                continue
            dens = [_densidade_balao(cinza, b, escala, janela_px,
                                     dx_folha, _dy_em(b["x_mm"]))
                    for b in baloes]
            freq, inc = _frequencia(dens)
            incidentes.extend(f"{chave}:{i}" for i in inc)
            if freq > 0:
                avaliacoes[quesito]["frequencias"][criterio] = freq
        obs_marcadas = set()
        for chave, balao in aluno.get("observacoes", {}).items():
            estado, inc = _estado_disco(cinza, balao, escala, janela_px,
                                        dx_folha, _dy_em(balao["x_mm"]),
                                        janela_mm=JANELA_MM)
            incidentes.extend(f"{chave}:{i}" for i in inc)
            if estado == "marcado":
                obs_marcadas.add(chave)
        _anular_contradicoes(obs_marcadas, incidentes)
        obs_lista = sorted(obs_marcadas)
        resultados.append({
            "metadados": {"exame_id": exame, "avaliador_id": avaliador,
                          "dojo_id": dojo, "aluno_id": aluno_id,
                          "faixa": faixa_aluno, "pagina": aluno.get("pagina", 1)},
            "aluno": {"id": aluno_id, "faixa_atual": faixa_aluno.title()},
            "presenca": "PRESENTE",
            "avaliacoes": avaliacoes,
            "observacoes_marcadas": obs_lista,
            "observacao_montada": observacoes.montar_observacao(obs_lista),
            "origem": origem,
            "incidentes_auditoria": incidentes,
            "omr_reader_version": OMR_READER_VERSION,
        })
    return resultados