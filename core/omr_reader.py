"""core/omr_reader.py — Leitura OMR enxuta por busca local (Karate-Ashi v3.14).

Contrato (steering fase-03 / playbook OMR):
- PROIBIDO fiduciais/cruzes impressos. Desalinhamento resolvido por BUSCA
  LOCAL: para cada balão esperado (x_mm, y_mm, r_mm), achar o ANEL impresso
  real numa janela de +-3 mm e medir o preenchimento no centro real. Isso é
  auto-calibrante por balão (dispensa homografia e fiduciais).
- QR via pyzbar primeiro (fallback cv2.QRCodeDetector) na imagem ORIGINAL.
- Scan ja A4 -> redimensiona direto para 3508x2480; warp so se nao for A4.
- Medicao: recuo de 20% do raio, Otsu local, taxa de escuros + maior blob.
  marcado: taxa >= 0.30 E blob >= 0.25 | vazio: taxa < 0.15 E blob < 0.08.
- Sem anel na janela -> "suspeito" (auditoria visual, nunca assume marcado).
- Presenca nao marcada -> AUSENTE (sem frequencias).
- Regra de arquitetura: maximo ~400 linhas.
"""
from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

from core import observacoes
from core.config import QUESITOS, carregar_json

A4_W_PX, A4_H_PX = 3508, 2480
A4_W_MM, A4_H_MM = 297.0, 210.0
RAZAO_MIN, RAZAO_MAX = 1.30, 1.55
JANELA_MM = 3.0          # janela da busca local (mm)
RECUO = 0.20             # recuo do interior de medicao (% do raio)
LIM_MARCADO = (0.30, 0.25)   # (taxa de escuros, maior blob)
LIM_VAZIO = (0.15, 0.08)
FREQ_BALOES = 5          # baloes de frequencia 1..5 por criterio

_QR_EXAME = re.compile(r"KA\|AVALIADOR=([^|]+)\|DOJO=([^|]+)\|EXAME=([^|]+)")
_QR_ALUNO = re.compile(r"KA\|ALUNO=([^|]+)\|FAIXA=([^|]+)")


# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------
def carregar_imagem(caminho: Path) -> np.ndarray:
    """PDF (pypdfium2 a 300 dpi) ou PNG/JPG/BMP/TIFF -> BGR."""
    caminho = Path(caminho)
    if caminho.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pagina = pdfium.PdfDocument(str(caminho))[0]
        bmp = pagina.render(scale=300 / 72)
        arr = np.frombuffer(bmp.to_bits(), dtype=np.uint8).reshape(
            bmp.height, bmp.width, bmp.n_channels)
        return arr[..., :3][:, :, ::-1]  # BGRA -> BGR
    img = cv2.imread(str(caminho), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"nao foi possivel ler a imagem: {caminho}")
    return img


def _cinza(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _ordenar_pontos(pts: np.ndarray) -> np.ndarray:
    """4 cantos (contorno) na ordem TL, TR, BR, BL."""
    soma = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    return np.float32([pts[np.argmin(soma)], pts[np.argmin(diff)],
                       pts[np.argmax(soma)], pts[np.argmax(diff)]])


def normalizar_a4(img: np.ndarray) -> np.ndarray:
    """Scan flatbed (~A4) -> resize direto; foto -> warp de 4 pontos."""
    h, w = img.shape[:2]
    razao = (w / h) if h else 0.0
    if RAZAO_MIN <= razao <= RAZAO_MAX:
        return cv2.resize(img, (A4_W_PX, A4_H_PX), interpolation=cv2.INTER_AREA)
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
    """Decodifica QRs -> [(payload, rect (x, y, w, h))]. pyzbar primeiro.

    Variantes testadas: cinza nativo, CINZA 2X (QR pequeno em scan/render
    de 300dpi costuma falhar em tamanho nativo), e binarizacao Otsu.
    O rect e devolvido em coordenadas da imagem ORIGINAL.
    """
    cinza = _cinza(imagem)
    h, w = cinza.shape[:2]
    escala = 1.0
    saida: list[tuple[str, tuple[int, int, int, int]]] = []
    try:
        from pyzbar import pyzbar
        cinza_2x = cv2.resize(cinza, (w * 2, h * 2),
                              interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(cinza, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for variante, fator in ((cinza, 1.0), (cinza_2x, 2.0),
                                (otsu, 1.0)):
            for qr in pyzbar.decode(variante):
                texto = qr.data.decode("utf-8", "replace")
                x, y, wq, hq = qr.rect
                # converte o rect de volta para a escala original
                x = int(x / fator)
                y = int(y / fator)
                wq = int(wq / fator)
                hq = int(hq / fator)
                saida.append((texto, (x, y, wq, hq)))
            if saida:
                break
    except ImportError:
        det = cv2.QRCodeDetector()
        texto, pts, _ = det.detectAndDecode(imagem)
        if texto and pts is not None:
            box = pts[0].astype(int).reshape(-1, 2)
            x0, y0 = box.min(axis=0)
            x1, y1 = box.max(axis=0)
            saida.append((texto, (int(x0), int(y0),
                                  int(x1 - x0), int(y1 - y0))))
    return saida


def _payload_por_prefixo(imagem: np.ndarray, prefixo: str) -> str | None:
    for texto, _ in _ler_qrs(imagem):
        if texto.startswith(f"KA|{prefixo}"):
            return texto
    return None


def _ler_alunos_do_qr(a4: np.ndarray) -> list[tuple[str, str]]:
    """Qrs KA|ALUNO=..|FAIXA=.. ordenados por posicao x (linha 1..3)."""
    alunos = []
    for texto, (x, _, _, _) in _ler_qrs(a4):
        m = _QR_ALUNO.search(texto)
        if m:
            alunos.append((x, m.group(1), m.group(2)))
    alunos.sort(key=lambda t: t[0])
    return [(aluno_id, faixa) for _, aluno_id, faixa in alunos]


# ---------------------------------------------------------------------------
# Busca local + medicao
# ---------------------------------------------------------------------------
def _achar_anel(cinza: np.ndarray, cx: float, cy: float, r: float,
                janela_px: float) -> tuple[float, float, float] | None:
    """Busca local +-janela_px pelo anel circular impresso (auto-calibrante)."""
    x0, y0 = max(0, int(cx - janela_px)), max(0, int(cy - janela_px))
    x1 = min(cinza.shape[1], int(cx + janela_px + 1))
    y1 = min(cinza.shape[0], int(cy + janela_px + 1))
    recorte = cinza[y0:y1, x0:x1]
    if recorte.size == 0:
        return None
    _, binaria = cv2.threshold(recorte, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(binaria, cv2.RETR_LIST,
                                    cv2.CHAIN_APPROX_SIMPLE)
    melhor: tuple[float, float, float] | None = None
    melhor_dist = float("inf")
    for c in contornos:
        if len(c) < 10:
            continue
        per = cv2.arcLength(c, True)
        area = cv2.contourArea(c)
        if area <= 0 or per <= 0:
            continue
        circularidade = 4 * np.pi * area / (per * per)
        if circularidade < 0.6:          # nao e um circulo
            continue
        (mx, my), mr = cv2.minEnclosingCircle(c)
        if mr < r * 0.5 or mr > r * 2.0:  # raio plausivel
            continue
        dist = abs(mx + x0 - cx) + abs(my + y0 - cy)
        if dist < melhor_dist:
            melhor_dist = dist
            melhor = (mx + x0, my + y0, mr)
    return melhor


def _medir(cinza: np.ndarray, cx: float, cy: float, r: float
           ) -> tuple[float, float]:
    """Taxa de escuros + maior blob no interior (recuo de 20% do raio)."""
    ri = r * (1.0 - RECUO)
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
    """marcado / vazio / suspeito — limiares validados (steering fase-03)."""
    if taxa >= LIM_MARCADO[0] and blob >= LIM_MARCADO[1]:
        return "marcado"
    if taxa < LIM_VAZIO[0] and blob < LIM_VAZIO[1]:
        return "vazio"
    return "suspeito"


def _estado_do_balao(cinza: np.ndarray, balao: dict, escala: float,
                     janela_px: float) -> tuple[str, list[str]]:
    """Busca local pelo anel; sem anel -> 'suspeito' (ja, nunca marcado)."""
    cx = balao["x_mm"] * escala
    cy = balao["y_mm"] * escala
    r = balao["r_mm"] * escala
    anel = _achar_anel(cinza, cx, cy, r, janela_px)
    if anel is None:
        return "suspeito", ["anel_nao_encontrado"]
    taxa, blob = _medir(cinza, anel[0], anel[1], anel[2])
    return classificar_checkbox(taxa, blob), []


def _frequencia(estados: list[str]) -> tuple[int, list[str]]:
    """5 baloes (1..5): 1 marcado -> indice; 0 -> 0; >1 -> ambiguidade."""
    marcados = [i for i, e in enumerate(estados) if e == "marcado"]
    if len(marcados) == 1:
        return marcados[0] + 1, []
    if not marcados:
        return 0, []
    return 0, ["ambiguidade_frequencia"]


def _anular_contradicoes(marcadas: set[str], incidentes: list[str]) -> None:
    """Anula pares obs_pN <-> obs_mN quando ambos marcados (v2col-3.0)."""
    for i in range(1, 7):
        p, m = f"obs_p{i}", f"obs_m{i}"
        if p in marcadas and m in marcadas:
            marcadas.discard(p)
            marcadas.discard(m)
            incidentes.append(f"contradicao:{p}/{m}")


# ---------------------------------------------------------------------------
# Coordenadas (contrato com tools/pre_exame.py)
# ---------------------------------------------------------------------------
def _carregar_coordenadas(pasta: Path, exame: str,
                          avaliador: str) -> dict | None:
    """output/pre_exame/{exame}_{avaliador}_folha*_coordenadas.json."""
    candidatos = sorted(pasta.glob(f"{exame}_{avaliador}_*_coordenadas.json"))
    if not candidatos:
        return None
    return carregar_json(candidatos[0])


# ---------------------------------------------------------------------------
# Fluxo completo
# ---------------------------------------------------------------------------
def processar_imagem(caminho_imagem: Path, base_cfg: Path | None = None,
                     faixa: str | None = None,
                     origem: str | None = None) -> list[dict]:
    """Folha OMR -> lista de JSONs v2.0 (um por aluno).

    base_cfg: pasta config/ (entao output/pre_exame e a pasta irma).
    Os QRs sao lidos na imagem ORIGINAL; a medicao roda na A4 normalizada.
    """
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

    alunos_qr = _ler_alunos_do_qr(a4)
    resultados = []
    for aluno in coords["alunos"]:
        aluno_id = aluno["id"]
        faixa_aluno = (faixa or aluno.get("faixa") or "branca").strip().lower()
        incidentes = ["origem:" + (origem or "desconhecida")]

        # Presenca: so 'marcado' conta como PRESENTE
        estado_p, inc = _estado_do_balao(cinza, aluno["presenca"],
                                         escala, janela_px)
        incidentes.extend(f"presenca:{i}" for i in inc)
        if estado_p != "marcado":
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
            })
            continue

        # Frequencias por criterio (5 baloes 1..5)
        avaliacoes: dict[str, dict] = {q: {"frequencias": {},
                                           "observacao": ""}
                                       for q in QUESITOS}
        for chave, baloes in aluno.get("frequencias", {}).items():
            quesito, _, criterio = chave.partition("_")
            if quesito not in avaliacoes or len(baloes) != FREQ_BALOES:
                continue
            estados = []
            for balao in baloes:
                estado, inc = _estado_do_balao(cinza, balao, escala, janela_px)
                estados.append(estado)
                incidentes.extend(f"{chave}:{i}" for i in inc)
            freq, inc = _frequencia(estados)
            incidentes.extend(f"{chave}:{i}" for i in inc)
            if freq > 0:
                avaliacoes[quesito]["frequencias"][criterio] = freq

        # Observacoes do rodape (obs_p1..p6 / obs_m1..m6)
        obs_marcadas = set()
        for chave, balao in aluno.get("observacoes", {}).items():
            estado, inc = _estado_do_balao(cinza, balao, escala, janela_px)
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
        })
    return resultados