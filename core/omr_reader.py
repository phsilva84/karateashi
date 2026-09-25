"""core/omr_reader.py — Leitura OMR por busca local (Karate-Ashi v3.17).

Semântica do domínio (definida pelo usuário):
- O avaliador marca TODOS os balões que observou (1..5 por critério);
  cada balão preenchido = 1 ocorrência do erro. 5/5 é legítimo.
- Frequência do critério = CONTAGEM de balões marcados (0..5), lidos
  INDEPENDENTEMENTE pelo DISCO CENTRAL (recuo 0.65 -> raio 0.35r):
  marcado = centro escuro, vazio = centro limpo. Imune a rabiscos e ao
  anel impresso (que fica fora do disco). 'suspeito' não conta e gera
  aviso de auditoria visual. NÃO existe 'ambiguidade' por múltiplas
  marcações — várias marcações são válidas.

Padrão rbaron/omr + OMRChecker (skill "Leitura OMR por Busca Local"):
- PROIBIDO fiduciais/cruzes. Desalinhamento por BUSCA LOCAL por balão
  (janela ±3mm; presença ±5mm) — mede no centro real do anel.
- QR via pyzbar primeiro (fallback cv2.QRCodeDetector). Scan A4 -> resize
  direto 3508x2480; warp só se não for A4.
- Calibração de offset GLOBAL (mediana) + OFFSET POR LINHA.
- Presença não marcada -> AUSENTE (sem avaliar). Regra: módulo <= ~400 linhas.
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
JANELA_PRESENCA_MM = 5.0 # janela ampliada p/ presenca
RECUO = 0.65             # DISCO CENTRAL (raio 0.35r) — so tinta no centro conta
LIM_MARCADO = (0.30, 0.25)   # (taxa de escuros, maior blob)
LIM_VAZIO = (0.15, 0.08)
LIM_DISCO = (0.40, 0.32) # limiar alto p/ presenca/obs (disco solido)
FREQ_BALOES = 5
_OFFSET_MAX_MM = 5.0
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
    cinza = _cinza(imagem)
    h, w = cinza.shape[:2]
    saida: list[tuple[str, tuple[int, int, int, int]]] = []
    try:
        from pyzbar import pyzbar
        cinza_2x = cv2.resize(cinza, (w * 2, h * 2),
                              interpolation=cv2.INTER_CUBIC)
        _, otsu = cv2.threshold(cinza, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for variante, fator in ((cinza, 1.0), (cinza_2x, 2.0), (otsu, 1.0)):
            for qr in pyzbar.decode(variante):
                texto = qr.data.decode("utf-8", "replace")
                x, y, wq, hq = qr.rect
                saida.append((texto, (int(x / fator), int(y / fator),
                                      int(wq / fator), int(hq / fator))))
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
    """Acha o circulo/anel impresso real na janela (+-janela_px).

    Raio aceito: 0.6r..1.4r (plausivel, anel/disco do balao) — evita
    contornos de grade/texto. SEM fechamento morfologico (preencheria o
    anel de balao vazio -> falso positivo). Fallback: maior blob circular.
    """
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
    """Taxa de escuros + maior blob no DISCO CENTRAL (recuo exclui o anel)."""
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

def _densidade_balao(cinza: np.ndarray, balao: dict, escala: float,
                     janela_px: float, dx_mm: float = 0.0,
                     dy_mm: float = 0.0) -> tuple[float, float]:
    """Densidade do DISCO CENTRAL do balao, medindo no anel real se achado,
    senao no centro nominal (offset aplicado)."""
    cx = (balao["x_mm"] + dx_mm) * escala
    cy = (balao["y_mm"] + dy_mm) * escala
    r = balao["r_mm"] * escala
    anel = _achar_anel(cinza, cx, cy, r, janela_px)
    if anel is not None:
        return _medir(cinza, anel[0], anel[1], anel[2])
    return _medir(cinza, cx, cy, r)

def _estado_disco(cinza: np.ndarray, balao: dict, escala: float,
                  janela_px: float, dx_mm: float = 0.0, dy_mm: float = 0.0,
                  janela_mm: float = JANELA_MM) -> tuple[str, list[str]]:
    """Presenca/Obs: disco solido (recuo exclui o anel; limiar ALTO).

    Sempre tenta a varredura como fallback: se o anel achado der medida
    'suspeita', NAO retorna logo — varre a janela por disco solido real.
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
        # anel suspeito: nao confia -> cai na varredura (fallback)
    passo = max(int(1.5 * escala), 4)
    raio_l = int(jpx)
    melhor = (0.0, 0.0)
    for ox in range(-raio_l, raio_l + 1, passo):
        for oy in range(-raio_l, raio_l + 1, passo):
            taxa, blob = _medir(cinza, cx + ox, cy + oy, r)
            if taxa > melhor[0]:
                melhor = (taxa, blob)
            if taxa >= LIM_DISCO[0] and blob >= LIM_DISCO[1]:
                return "marcado", ["disco_sem_anel"]
    taxa, blob = _medir(cinza, cx, cy, r)
    if taxa < LIM_VAZIO[0] and blob < LIM_VAZIO[1]:
        return "vazio", []
    return "suspeito", ["anel_nao_encontrado"]

def _frequencia(densidades: list[tuple[float, float]]) -> tuple[int, list[str]]:
    """Frequencia do criterio = QUANTIDADE de baloes marcados (0..5).

    Logica do dominio (avaliacao livre por ocorrencia):
    - o avaliador marca TODOS os baloes que observou (1..5 por criterio);
      cada balao preenchido = 1 ocorrencia do erro. 5/5 e legitimo.
    - conta quantos baloes estao 'marcado' (disco central preenchido);
    - 'suspeito' (marcacao leve/parcial) nao conta e gera aviso p/ revisao;
    - 'vazio' nao conta. Nao ha 'ambiguidade': varias marcacoes sao validas.
    """
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
    _ler_alunos_do_qr(a4)
    amostra: list[dict] = []
    for aluno in coords["alunos"]:
        amostra.append(aluno["presenca"])
        for baloes in aluno.get("frequencias", {}).values():
            amostra.extend(baloes)
    dx_mm, dy_mm = _calibrar_offset(cinza, amostra, escala, janela_px)
    resultados = []
    for aluno in coords["alunos"]:
        aluno_id = aluno["id"]
        faixa_aluno = (faixa or aluno.get("faixa") or "branca").strip().lower()
        incidentes = ["origem:" + (origem or "desconhecida")]
        if dx_mm or dy_mm:
            incidentes.append(
                f"calibracao_offset:dx={dx_mm:.2f},dy={dy_mm:.2f}")
        baloes_linha = [aluno["presenca"]]
        for baloes in aluno.get("frequencias", {}).values():
            baloes_linha.extend(baloes)
        baloes_linha.extend(aluno.get("observacoes", {}).values())
        dx_l, dy_l = _offset_por_linha(cinza, baloes_linha, escala,
                                       janela_px, dx_mm, dy_mm)
        if (dx_l, dy_l) != (dx_mm, dy_mm):
            incidentes.append(
                f"calibracao_offset_linha:dx={dx_l:.2f},dy={dy_l:.2f}")
        pres, inc_p = _estado_disco(
            cinza, aluno["presenca"], escala, janela_px, dx_l, dy_l,
            janela_mm=JANELA_PRESENCA_MM)
        incidentes.extend(f"presenca:{i}" for i in inc_p)
        if pres != "marcado":
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
        avaliacoes: dict[str, dict] = {q: {"frequencias": {},
                                           "observacao": ""}
                                       for q in QUESITOS}
        for chave, baloes in aluno.get("frequencias", {}).items():
            quesito, _, criterio = chave.partition("_")
            if quesito not in avaliacoes or len(baloes) != FREQ_BALOES:
                continue
            dens = [_densidade_balao(cinza, b, escala, janela_px, dx_l, dy_l)
                    for b in baloes]
            freq, inc = _frequencia(dens)
            incidentes.extend(f"{chave}:{i}" for i in inc)
            if freq > 0:
                avaliacoes[quesito]["frequencias"][criterio] = freq
        obs_marcadas = set()
        for chave, balao in aluno.get("observacoes", {}).items():
            estado, inc = _estado_disco(cinza, balao, escala, janela_px,
                                        dx_l, dy_l, janela_mm=JANELA_MM)
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