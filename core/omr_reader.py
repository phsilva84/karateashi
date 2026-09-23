"""core/omr_reader.py — Leitura OMR dos gabaritos Karate-Ashi v3.14 (novo layout).

Pipeline:
1. carregar imagem (PDF via pypdfium2 a 300 DPI, ou PNG/JPG);
2. decodificar o QR do cabeçalho na foto ORIGINAL;
3. NORMALIZAR a folha para A4 PAISAGEM EXATO (3508x2480 @ 300dpi);
4. CALIBRAR (v3.14):
   a. CRUZES DAS LINHAS: 2 cruzes por linha (margem x=5/x=292) -> conversor
      LOCAL da linha (critérios + presença).
   b. CRUZES DAS OBSERVAÇÕES: 2 cruzes GLOBAIS na margem, na altura do
      rodapé (x=5/x=292, y=202) -> conversor LOCAL do rodapé (círculos
      BOM!/A MELHORAR).
   c. FALLBACK: calibração global pelos QRs (folhas antigas sem cruzes).
5. LOCALIZAR AS COORDENADAS automaticamente pelo QR do cabeçalho;
6. ler os QR de cada aluno no CABEÇALHO (posição define a linha);
7. extrair os balões das coordenadas exportadas (JSON por folha);
8. medir cada balão (interior com recuo 20%, Otsu local + blob);
9. classificar: marcado / vazio / suspeito / erro;
10. determinar frequência (1-5) por critério + presença + observações;
11. anular contradições de observação (5 pares) e gerar JSON schema v2.0.

ASSINATURA CANÔNICA (v3.14):
    processar_imagem(caminho_imagem, base_cfg=None, faixa=None, origem=None)

CORREÇÕES v3.14:
- Validação tolerante a marcadores: 'aluno' é obrigatório apenas para balões
  de MEDIÇÃO. Marcadores (cruzes) são globais e não têm 'aluno'.
- Agrupamento por aluno ignora elementos sem 'aluno' (cruzes).
- Template da cruz SÓLIDA (retângulos preenchidos) — casa com o desenho do
  pre_exame v5.5, garantindo detecção confiável no template matching.

Dependências: opencv-python, numpy, pypdfium2 (para PDF), pyzbar (opcional).
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from core.config import QUESITOS, carregar_json  # fonte única (Fase 4)

RAIZ = Path(__file__).resolve().parent.parent

# A4 PAISAGEM — base da conversão mm -> px das coordenadas.
LARGURA_A4_MM = 297.0
ALTURA_A4_MM = 210.0
# Dimensões EXATAS do A4 paisagem a 300 DPI (warp de normalização).
A4_LANDSCAPE_PX = (3508, 2480)

# --- Detecção da folha (robustez p/ foto) ---------------------------------
_EPSILON_CANDIDATOS = (0.010, 0.015, 0.020, 0.025, 0.030)
_AREA_MINIMA = 0.05             # fração mínima da imagem
_RETANGULARIDADE_MINIMA = 0.80  # área do contorno / área do retângulo mínimo
_MARGEM_BORDA = 0.02            # fração do menor lado
_LADO_DETECCAO_PX = 1600        # downscale p/ detecção (velocidade)
_RAZAO_A4_MIN = 1.20            # A4 paisagem ≈ 1.414
_RAZAO_A4_MAX = 1.60
_LADO_MIN_PX = 50
_FRACAO_PRETA_MAX = 0.15        # guarda de folha cortada no warp

# --- QR do cabeçalho (canto superior direito) — REDUZIDO para 14mm (v4.9) --
_QR_CAB_X_MM = 273.0
_QR_CAB_Y_MM = 8.0
_QR_CAB_TAM_MM = 14.0

# --- QR dos ALUNOS no CABEÇALHO (v3.14) — posição define a linha -----------
_QR_ALUNO_CAB_X_MM = [195.0, 214.0, 233.0]
_QR_ALUNO_CAB_Y_MM = 8.0
_QR_ALUNO_CAB_TAM_MM = 11.0
_QR_ALUNO_PADDING_MM = 4.0      # zona de silêncio ao redor do QR

# --- CRUZES DE REFERÊNCIA (v3.14) — SÓLIDAS, retângulos preenchidos -------
CRUZ_BRACO_MM = 2.0             # braço da cruz (mm) — total 4mm
CRUZ_ESPESSURA_MM = 1.2         # espessura (mm) — área maciça
CRUZ_JANELA_MM = 8.0            # janela de busca ao redor da posição esperada
CRUZ_CONFIANCA_MIN = 0.45       # limiar de confiança do template matching

# --- Geometria das linhas (v3.14 — cabeçalho 28mm, rodapé 40mm) -----------
_LINHA_Y0_MM = 28.0
_LINHA_H_MM = 47.33               # (210 - 28 - 40) / 3

# --- Limiares de classificação de balões -----------------------------------
LIMIAR_TAXA = 0.30      # fração de pixels escuros no interior do balão
LIMIAR_BLOB = 0.25      # fração do maior blob sobre o interior
LIMIAR_VAZIO_TAXA = 0.15
LIMIAR_VAZIO_BLOB = 0.08

# --- Pares de contradição (5 pares — v3.0) ---------------------------------
PARES_CONTRADICAO = [
    ("obs_p1", "obs_m1"),
    ("obs_p2", "obs_m2"),
    ("obs_p3", "obs_m3"),
    ("obs_p4", "obs_m4"),
    ("obs_p5", "obs_m5"),
]

# ---------------------------------------------------------------------------
# QR Code
# ---------------------------------------------------------------------------
def variantes_qr(imagem: np.ndarray) -> list[np.ndarray]:
    """Variantes de pré-processamento para o leitor de QR."""
    variantes: list[np.ndarray] = [imagem]
    cinza = (cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
             if imagem.ndim == 3 else imagem)
    variantes.append(cinza)
    maior = max(cinza.shape[:2])
    if maior < 1400:
        for fator in (2.0, 3.0):
            if maior * fator <= 5000:
                variantes.append(cv2.resize(
                    cinza, None, fx=fator, fy=fator,
                    interpolation=cv2.INTER_CUBIC))
    else:
        fator = 1600.0 / maior
        variantes.append(cv2.resize(cinza, None, fx=fator, fy=fator,
                                    interpolation=cv2.INTER_AREA))
    nitido = cv2.addWeighted(cinza, 1.6,
                             cv2.GaussianBlur(cinza, (0, 0), 3.0), -0.6, 0)
    variantes.append(nitido)
    variantes.append(cv2.adaptiveThreshold(
        cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10))
    _, otsu = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variantes.append(otsu)
    return variantes


def decodificar_qr(imagem: np.ndarray) -> str | None:
    """Decodifica o primeiro QR encontrado; devolve o texto ou None."""
    try:
        detector = cv2.QRCodeDetector()
        dados, _, _ = detector.detectAndDecode(imagem)
        if dados:
            return dados
    except Exception:  # noqa: BLE001
        pass
    try:
        from pyzbar.pyzbar import decode  # import local
    except Exception:  # noqa: BLE001 — libzbar0 ausente
        return None
    for variante in variantes_qr(imagem):
        try:
            simbolos = decode(variante)
        except Exception:  # noqa: BLE001
            continue
        for obj in simbolos:
            texto = obj.data.decode("utf-8", errors="replace")
            if texto:
                return texto
    return None


def decodificar_qr_com_prefixo(imagem: np.ndarray, prefixo: str) -> str | None:
    """Decodifica o primeiro QR cujo payload contenha 'prefixo'."""
    for img in [imagem] + variantes_qr(imagem):
        try:
            detector = cv2.QRCodeDetector()
            dados, _, _ = detector.detectAndDecode(img)
            if dados and prefixo in dados:
                return dados
        except Exception:  # noqa: BLE001
            pass
    try:
        from pyzbar.pyzbar import decode
    except Exception:  # noqa: BLE001
        return None
    for img in [imagem] + variantes_qr(imagem):
        try:
            simbolos = decode(img)
        except Exception:  # noqa: BLE001
            continue
        for obj in simbolos:
            texto = obj.data.decode("utf-8", errors="replace")
            if texto and prefixo in texto:
                return texto
    return None


def parse_payload_qr(payload: str) -> dict:
    """KA|CHAVE=VALOR|CHAVE=VALOR -> dict de metadados."""
    partes = [p.strip() for p in payload.split("|")]
    if not partes or partes[0] != "KA":
        raise ValueError(f"payload QR inválido: {payload!r}")
    metadados: dict[str, str] = {}
    for parte in partes[1:]:
        if "=" in parte:
            chave, valor = parte.split("=", 1)
            metadados[chave.strip().lower()] = valor.strip()
    return metadados


# ---------------------------------------------------------------------------
# Detecção e correção de perspectiva
# ---------------------------------------------------------------------------
def binarizacoes(cinza: np.ndarray) -> list[np.ndarray]:
    """Três binarizações complementares (folha clara/escura/baixo contraste)."""
    blur = cv2.GaussianBlur(cinza, (5, 5), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, otsu_inv = cv2.threshold(blur, 0, 255,
                                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    canny = cv2.Canny(blur, 50, 150)
    canny = cv2.morphologyEx(
        canny, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    return [otsu, otsu_inv, canny]


def _quatro_cantos(contorno: np.ndarray) -> np.ndarray | None:
    """Aproxima o contorno a um quadrilátero convexo (varredura de epsilon)."""
    peri = cv2.arcLength(contorno, True)
    if peri <= 0:
        return None
    hull = cv2.convexHull(contorno)
    for eps in _EPSILON_CANDIDATOS:
        approx = cv2.approxPolyDP(hull, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype("float32")
    return None


def _toca_borda(pts: np.ndarray, largura: int, altura: int,
                margem: float) -> bool:
    """True se algum canto está colado na borda."""
    for x, y in pts:
        if (x <= margem or y <= margem or
                x >= largura - margem or y >= altura - margem):
            return True
    return False


def _retangularidade(quad: np.ndarray) -> float:
    """Quão retangular é o quadrilátero (1.0 = retângulo perfeito)."""
    area = cv2.contourArea(quad)
    _, (lado_a, lado_b), _ = cv2.minAreaRect(quad)
    area_rect = lado_a * lado_b
    return float(area / area_rect) if area_rect > 0 else 0.0


def _ordenar_cantos(pts: np.ndarray) -> np.ndarray:
    """Ordena: topo-esq, topo-dir, baixo-dir, baixo-esq."""
    soma = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(soma)], pts[np.argmin(diff)],
                     pts[np.argmax(soma)], pts[np.argmax(diff)]],
                    dtype="float32")


def _warp(imagem: np.ndarray, ordem: np.ndarray) -> np.ndarray:
    """Aplica a correção de perspectiva para o quadrilátero ordenado."""
    largura = max(int(np.linalg.norm(ordem[1] - ordem[0])),
                  int(np.linalg.norm(ordem[2] - ordem[3])))
    altura = max(int(np.linalg.norm(ordem[3] - ordem[0])),
                 int(np.linalg.norm(ordem[2] - ordem[1])))
    if largura < 2 or altura < 2:
        raise ValueError("folha detectada com dimensões inválidas")
    destino = np.array([[0, 0], [largura - 1, 0],
                        [largura - 1, altura - 1], [0, altura - 1]],
                       dtype="float32")
    matriz = cv2.getPerspectiveTransform(ordem, destino)
    return cv2.warpPerspective(imagem, matriz, (largura, altura))


def _warp_a4(imagem: np.ndarray, ordem: np.ndarray) -> np.ndarray:
    """Warp para A4 paisagem EXATO (3508x2480 @ 300dpi)."""
    largura, altura = A4_LANDSCAPE_PX
    destino = np.array([[0, 0], [largura - 1, 0],
                        [largura - 1, altura - 1], [0, altura - 1]],
                       dtype="float32")
    matriz = cv2.getPerspectiveTransform(ordem, destino)
    return cv2.warpPerspective(imagem, matriz, (largura, altura))


def _quad_folha_plausivel(cantos: np.ndarray) -> bool:
    """Valida se os 4 cantos formam uma página A4 PAISAGEM plausível."""
    ordem = _ordenar_cantos(cantos)
    largura = max(float(np.linalg.norm(ordem[1] - ordem[0])),
                  float(np.linalg.norm(ordem[2] - ordem[3])))
    altura = max(float(np.linalg.norm(ordem[3] - ordem[0])),
                 float(np.linalg.norm(ordem[2] - ordem[1])))
    if largura < _LADO_MIN_PX or altura < _LADO_MIN_PX:
        return False
    razao = largura / altura
    return _RAZAO_A4_MIN <= razao <= _RAZAO_A4_MAX


def _pontos_mm_qr_cabecalho() -> np.ndarray:
    """Cantos do QR do cabeçalho em mm (origem topo-esquerda)."""
    x0, y0, lado = _QR_CAB_X_MM, _QR_CAB_Y_MM, _QR_CAB_TAM_MM
    return np.array([
        [x0, y0], [x0 + lado, y0],
        [x0 + lado, y0 + lado], [x0, y0 + lado],
    ], dtype="float32")


def localizar_qr_opencv(imagem: np.ndarray) -> tuple[np.ndarray, str] | None:
    """Localiza o QR do cabeçalho usando o detector nativo do OpenCV."""
    try:
        detector = cv2.QRCodeDetector()
        dados, pontos, _ = detector.detectAndDecode(imagem)
        if dados and pontos is not None and len(pontos) == 4:
            return pontos.reshape(4, 2).astype("float32"), dados
        try:
            ok, dados_multi, pontos_multi, _ = detector.detectAndDecodeMulti(imagem)
            if ok and dados_multi is not None and pontos_multi is not None:
                for i, d in enumerate(dados_multi):
                    if d and "AVALIADOR" in d and i < len(pontos_multi):
                        return pontos_multi[i].reshape(4, 2).astype("float32"), d
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    return None


def localizar_qr_pyzbar(imagem: np.ndarray) -> tuple[np.ndarray, str] | None:
    """Localiza o QR do cabeçalho via pyzbar (método principal)."""
    try:
        from pyzbar.pyzbar import decode
    except Exception:  # noqa: BLE001
        return None
    candidatas: list[np.ndarray] = [imagem]
    if imagem.ndim == 3:
        candidatas.append(cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY))
    for img in candidatas:
        try:
            simbolos = decode(img)
        except Exception:  # noqa: BLE001
            continue
        for obj in simbolos:
            if obj.type != "QRCODE" or len(obj.polygon) < 4:
                continue
            dados = obj.data.decode("utf-8", errors="replace")
            if not dados:
                continue
            pontos = np.array([[p.x, p.y] for p in obj.polygon],
                              dtype="float32")
            if "AVALIADOR" in dados:
                return pontos, dados
    return None


def localizar_qr(imagem: np.ndarray) -> tuple[np.ndarray, str] | None:
    """Localiza o QR do cabeçalho (pyzbar, ordem nativa) — compatibilidade."""
    return localizar_qr_pyzbar(imagem)


def warp_pela_ancora(imagem: np.ndarray, pontos_qr_px: np.ndarray) -> np.ndarray:
    """Warp da folha usando o QR do cabeçalho como âncora (A4 paisagem)."""
    alvo_mm = _pontos_mm_qr_cabecalho()  # TL, TR, BR, BL em mm
    altura, largura = imagem.shape[:2]
    folga = 0.3 * max(altura, largura)
    melhor: tuple[np.ndarray, np.ndarray] | None = None
    melhor_erro = float("inf")
    for k in range(4):
        pts = np.roll(pontos_qr_px, k, axis=0)
        H, _ = cv2.findHomography(alvo_mm, pts)
        if H is None:
            continue
        pagina_mm = np.array([[0, 0], [LARGURA_A4_MM, 0],
                              [LARGURA_A4_MM, ALTURA_A4_MM], [0, ALTURA_A4_MM]],
                             dtype="float32")
        cantos = cv2.perspectiveTransform(
            pagina_mm.reshape(-1, 1, 2), H).reshape(-1, 2)
        if (cantos[:, 0].min() < -folga or cantos[:, 1].min() < -folga or
                cantos[:, 0].max() > largura + folga or
                cantos[:, 1].max() > altura + folga):
            continue
        ordem = _ordenar_cantos(cantos)
        w = max(float(np.linalg.norm(ordem[1] - ordem[0])),
                float(np.linalg.norm(ordem[2] - ordem[3])))
        h = max(float(np.linalg.norm(ordem[3] - ordem[0])),
                float(np.linalg.norm(ordem[2] - ordem[1])))
        if w <= 0 or h <= 0:
            continue
        razao = w / h
        erro = abs(razao - 1.414)
        if erro < melhor_erro:
            melhor_erro = erro
            melhor = (pts, ordem)
    if melhor is None:
        raise ValueError("não foi possível estimar a homografia do QR "
                         "(nenhuma rotação produziu página plausível)")
    _, ordem = melhor
    return _warp_a4(imagem, ordem)


def _fracao_preta(imagem: np.ndarray) -> float:
    """Fração de pixels quase pretos (área fora da foto no warp)."""
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cinza < 30))


def _detectar_quad(imagem: np.ndarray) -> np.ndarray | None:
    """Detecta o quadrilátero da folha (multi-binarização)."""
    escala = min(1.0, _LADO_DETECCAO_PX / max(imagem.shape[:2]))
    pequena = (cv2.resize(imagem, None, fx=escala, fy=escala,
                          interpolation=cv2.INTER_AREA)
               if escala < 1.0 else imagem)
    cinza = cv2.cvtColor(pequena, cv2.COLOR_BGR2GRAY)
    altura, largura = cinza.shape[:2]
    area_img = float(altura * largura)
    margem = _MARGEM_BORDA * min(altura, largura)
    melhor: np.ndarray | None = None
    melhor_score = 0.0
    for binaria in binarizacoes(cinza):
        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area < _AREA_MINIMA * area_img:
                continue
            quad = _quatro_cantos(contorno)
            if quad is None:
                continue
            if _toca_borda(quad, largura, altura, margem):
                continue
            retang = _retangularidade(quad)
            if retang < _RETANGULARIDADE_MINIMA:
                continue
            score = (area / area_img) * retang
            if score > melhor_score:
                melhor_score = score
                melhor = quad
    if melhor is None:
        return None
    if escala < 1.0:
        melhor = melhor / escala
    return melhor


def _rotacionar_para_paisagem(imagem: np.ndarray,
                              ordem: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    """Gira a imagem para deixar a folha em paisagem (fallback de contorno)."""
    local = localizar_qr_opencv(imagem) or localizar_qr_pyzbar(imagem)
    if local is not None:
        pontos_qr, dados = local
        if "AVALIADOR" in dados:
            centro = pontos_qr.mean(axis=0)
            dists = [float(np.linalg.norm(centro - c)) for c in ordem]
            idx = int(np.argmin(dists))
            rot = {
                0: cv2.ROTATE_90_CLOCKWISE,
                2: cv2.ROTATE_90_COUNTERCLOCKWISE,
                3: cv2.ROTATE_180,
            }.get(idx)
            if rot is not None:
                return cv2.rotate(imagem, rot), None
    for rot in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
        girada = cv2.rotate(imagem, rot)
        quad2 = _detectar_quad(girada)
        if quad2 is not None:
            ordem2 = _ordenar_cantos(quad2)
            w2 = max(float(np.linalg.norm(ordem2[1] - ordem2[0])),
                     float(np.linalg.norm(ordem2[2] - ordem2[3])))
            h2 = max(float(np.linalg.norm(ordem2[3] - ordem2[0])),
                     float(np.linalg.norm(ordem2[2] - ordem2[1])))
            if w2 >= h2:
                return girada, quad2
    return imagem, None


def detectar_e_corrigir(imagem: np.ndarray) -> np.ndarray:
    """Detecta a folha e normaliza para A4 paisagem EXATO (3508x2480)."""
    if imagem is None or imagem.size == 0:
        raise ValueError("imagem vazia")

    if _parece_a4_ja_alinhada(imagem):
        largura, altura = A4_LANDSCAPE_PX
        return cv2.resize(imagem, (largura, altura),
                          interpolation=cv2.INTER_AREA)

    local = localizar_qr_pyzbar(imagem)
    if local is not None:
        pontos_qr, dados = local
        if "AVALIADOR" in dados:
            try:
                return warp_pela_ancora(imagem, pontos_qr)
            except ValueError:
                pass

    local = localizar_qr_opencv(imagem)
    if local is not None:
        pontos_qr, dados = local
        if "AVALIADOR" in dados:
            try:
                return warp_pela_ancora(imagem, pontos_qr)
            except ValueError:
                pass

    quad = _detectar_quad(imagem)
    if quad is None:
        raise ValueError("nenhum contorno de folha encontrado — enquadre a "
                         "folha inteira, com as quatro bordas visíveis")

    ordem = _ordenar_cantos(quad)
    largura = max(float(np.linalg.norm(ordem[1] - ordem[0])),
                  float(np.linalg.norm(ordem[2] - ordem[3])))
    altura = max(float(np.linalg.norm(ordem[3] - ordem[0])),
                 float(np.linalg.norm(ordem[2] - ordem[1])))

    if altura > largura:
        imagem, quad = _rotacionar_para_paisagem(imagem, ordem)
        if quad is None:
            quad = _detectar_quad(imagem)
        if quad is None:
            raise ValueError("folha em pé e não foi possível girar — "
                             "refaça o scan em paisagem (horizontal)")
        ordem = _ordenar_cantos(quad)

    return _warp_a4(imagem, ordem)


def _parece_a4_ja_alinhada(imagem: np.ndarray) -> bool:
    """Heurística: a imagem já é uma folha A4 paisagem plana e alinhada?"""
    altura, largura = imagem.shape[:2]
    if altura <= 0:
        return False
    razao = largura / altura
    return _RAZAO_A4_MIN <= razao <= _RAZAO_A4_MAX


# ---------------------------------------------------------------------------
# Carga de imagem (PDF ou PNG)
# ---------------------------------------------------------------------------
def renderizar_pdf(caminho_pdf: Path, dpi: int = 300) -> np.ndarray:
    """Renderiza a 1ª página do PDF em imagem (mesmo DPI das coordenadas)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise ValueError("pypdfium2 não instalado. Rode: pip install pypdfium2")
    pdf = pdfium.PdfDocument(str(caminho_pdf))
    pagina = pdf[0]
    escala = dpi / 72.0          # PDF usa 72 DPI como base
    bitmap = pagina.render(scale=escala)
    return np.array(bitmap.to_pil().convert("RGB"))


def carregar_imagem(caminho: Path) -> np.ndarray:
    """Carrega PDF (renderizado a 300 DPI) ou PNG/JPG."""
    if caminho.suffix.lower() == ".pdf":
        return renderizar_pdf(caminho)
    img = cv2.imread(str(caminho))
    if img is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho}")
    return img


# ---------------------------------------------------------------------------
# Coordenadas dos balões (JSON exportado por pre_exame)
# ---------------------------------------------------------------------------
def carregar_coordenadas_baloes(coordenadas_path: Path) -> list[dict]:
    """Carrega a lista de balões do JSON exportado por pre_exame.

    v3.14: 'aluno' é obrigatório apenas para balões de MEDIÇÃO. Marcadores
    (cruzes) são globais e não têm 'aluno'.
    """
    if not coordenadas_path.exists():
        raise FileNotFoundError(
            f"Coordenadas não encontradas: {coordenadas_path}\n"
            f"Gere as folhas com tools/pre_exame.py (que exporta "
            f"{coordenadas_path.name}).")
    dados = carregar_json(coordenadas_path)
    if not isinstance(dados, list):
        raise ValueError(f"{coordenadas_path}: se esperava uma lista de balões")
    if not dados:
        raise ValueError(f"{coordenadas_path}: lista de balões vazia")
    for b in dados:
        # Campos obrigatórios para TODOS os elementos.
        if not all(k in b for k in ("tipo", "x_mm", "y_mm", "r_mm")):
            raise ValueError(f"balão sem campos obrigatórios: {b}")
        # 'aluno' é obrigatório apenas para balões de MEDIÇÃO.
        # Marcadores (cruzes) são globais e não pertencem a um aluno.
        if b.get("tipo") not in ("marcador", "marcador_obs") and "aluno" not in b:
            raise ValueError(f"balão sem campo 'aluno': {b}")
        if float(b["x_mm"]) == 0 and float(b["y_mm"]) == 0:
            raise ValueError(
                f"coordenadas não calibradas em {b} — "
                f"gere as folhas com tools/pre_exame.py")
    return dados


def _numero_folha(nome: str) -> int:
    """Extrai o número da folha do nome 'EXA-..._S02_folha1_coordenadas.json'."""
    m = re.search(r"folha(\d+)", nome)
    return int(m.group(1)) if m else 1


def _alunos_do_exame(dojo_id: str | None, exame_id: str | None) -> list[str]:
    """Lista ordenada de IDs dos alunos do exame (cadastro filtrado pelo dojo)."""
    if not dojo_id or not exame_id:
        return []
    try:
        cadastro = carregar_json(RAIZ / "data" / "cadastro" / "alunos.json")
        exames = carregar_json(RAIZ / "data" / "exames.json")
    except Exception:  # noqa: BLE001
        return []
    exame = next((e for e in exames.get("exames", [])
                  if e.get("id") == exame_id), None)
    if exame is None:
        return []
    dojo = exame.get("dojo_id")
    return [a["id"] for a in cadastro.get("alunos", [])
            if a.get("dojo_id") == dojo]


def _resolver_coordenadas(base_cfg, metadados_cab: dict,
                          alinhada: np.ndarray,
                          px_mm_x: float, px_mm_y: float) -> Path:
    """Localiza o JSON de coordenadas da folha processada."""
    if base_cfg is not None and Path(base_cfg).suffix.lower() == ".json":
        return Path(base_cfg)

    exame = metadados_cab.get("exame")
    avaliador = metadados_cab.get("avaliador")
    if not exame or not avaliador:
        raise ValueError(
            "QR do cabeçalho sem exame/avaliador — não é possível localizar "
            "as coordenadas. Informe o JSON de coordenadas diretamente.")

    raiz = RAIZ
    if base_cfg is not None:
        raiz = Path(base_cfg).resolve().parent
    candidatos: list[Path] = []
    for pasta in (raiz / "output" / "pre_exame",
                  RAIZ / "output" / "pre_exame"):
        if pasta.is_dir():
            candidatos.extend(sorted(pasta.glob(
                f"{exame}_{avaliador}_folha*_coordenadas.json")))
    vistos: set[Path] = set()
    unicos: list[Path] = []
    for c in candidatos:
        if c not in vistos:
            vistos.add(c)
            unicos.append(c)
    candidatos = unicos

    if not candidatos:
        raise FileNotFoundError(
            f"Coordenadas não encontradas para {exame}/{avaliador} em "
            f"output/pre_exame. Gere as folhas com tools/pre_exame.py.")

    if len(candidatos) == 1:
        return candidatos[0]

    ids_imagem: set[str] = set()
    for j in range(len(_QR_ALUNO_CAB_X_MM)):
        box = {"x": _QR_ALUNO_CAB_X_MM[j], "y": _QR_ALUNO_CAB_Y_MM,
               "w": _QR_ALUNO_CAB_TAM_MM, "h": _QR_ALUNO_CAB_TAM_MM}
        payload = _ler_qr_em_mm(alinhada, box, px_mm_x, px_mm_y)
        meta = parse_payload_qr(payload) if payload else {}
        if meta.get("aluno"):
            ids_imagem.add(meta["aluno"])

    ordem = _alunos_do_exame(metadados_cab.get("dojo"), exame)
    for candidato in candidatos:
        folha_num = _numero_folha(candidato.name)
        esperados = ordem[3 * (folha_num - 1): 3 * folha_num]
        if esperados and ids_imagem and set(esperados) == ids_imagem:
            return candidato

    print(f"[AVISO] múltiplas folhas para {exame}/{avaliador}; usando "
          f"{candidatos[0].name} (não foi possível desambiguar pelos QRs).")
    return candidatos[0]


# ---------------------------------------------------------------------------
# CALIBRAÇÃO GLOBAL PELOS QRs (v3.11 — fallback)
# ---------------------------------------------------------------------------
def _qrs_com_posicao(imagem: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Decodifica todos os QRs e devolve (payload, centro_px) de cada um."""
    try:
        from pyzbar.pyzbar import decode
    except Exception:  # noqa: BLE001
        return []
    candidatas: list[np.ndarray] = [imagem]
    if imagem.ndim == 3:
        candidatas.append(cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY))
    for img in candidatas:
        try:
            simbolos = decode(img)
        except Exception:  # noqa: BLE001
            continue
        resultados: list[tuple[str, np.ndarray]] = []
        for obj in simbolos:
            if obj.type != "QRCODE" or len(obj.polygon) < 4:
                continue
            dados = obj.data.decode("utf-8", errors="replace")
            if not dados:
                continue
            pts = np.array([[p.x, p.y] for p in obj.polygon], dtype="float32")
            resultados.append((dados, pts.mean(axis=0)))
        if resultados:
            return resultados
    return []


def _calibrar_conversor(alinhada: np.ndarray, px_mm_x: float, px_mm_y: float):
    """Calcula a conversão REAL mm→px usando os QRs detectados na imagem.

    Com 4+ QRs: homografia. Com 3: afim. Com 2: escala + translação.
    Sem QRs suficientes: conversão linear simples.
    """
    refs_mm: list[list[float]] = []
    refs_px: list[np.ndarray] = []

    for dados, centro in _qrs_com_posicao(alinhada):
        if "AVALIADOR" in dados:
            refs_mm.append([_QR_CAB_X_MM + _QR_CAB_TAM_MM / 2,
                            _QR_CAB_Y_MM + _QR_CAB_TAM_MM / 2])
            refs_px.append(centro)
        elif "ALUNO=" in dados:
            meta = parse_payload_qr(dados)
            if not meta.get("aluno"):
                continue
            cx_mm = float(centro[0]) / px_mm_x
            melhor_j, melhor_dist = None, float("inf")
            for j, x_esp in enumerate(_QR_ALUNO_CAB_X_MM):
                dist = abs(cx_mm - (x_esp + _QR_ALUNO_CAB_TAM_MM / 2))
                if dist < melhor_dist:
                    melhor_dist = dist
                    melhor_j = j
            if melhor_j is not None and melhor_dist < 20.0:
                pos_mm = [_QR_ALUNO_CAB_X_MM[melhor_j] + _QR_ALUNO_CAB_TAM_MM / 2,
                          _QR_ALUNO_CAB_Y_MM + _QR_ALUNO_CAB_TAM_MM / 2]
                if pos_mm not in refs_mm:
                    refs_mm.append(pos_mm)
                    refs_px.append(centro)

    n = len(refs_mm)

    if n >= 4:
        H, _ = cv2.findHomography(np.array(refs_mm, dtype="float32"),
                                  np.array(refs_px, dtype="float32"))
        if H is not None:
            def converter(x_mm: float, y_mm: float) -> tuple[float, float]:
                p = np.array([x_mm, y_mm, 1.0])
                q = H @ p
                return float(q[0] / q[2]), float(q[1] / q[2])
            return converter

    if n == 3:
        try:
            M = cv2.getAffineTransform(np.array(refs_mm, dtype="float32"),
                                       np.array(refs_px, dtype="float32"))
            if M is not None:
                def converter(x_mm: float, y_mm: float) -> tuple[float, float]:
                    p = np.array([x_mm, y_mm, 1.0])
                    q = M @ p
                    return float(q[0]), float(q[1])
                return converter
        except cv2.error:
            pass

    if n == 2:
        mm_arr = np.array(refs_mm, dtype="float64")
        px_arr = np.array(refs_px, dtype="float64")
        d_mm = float(np.linalg.norm(mm_arr[1] - mm_arr[0]))
        d_px = float(np.linalg.norm(px_arr[1] - px_arr[0]))
        escala = d_px / d_mm if d_mm > 0 else px_mm_x
        transl = px_arr.mean(axis=0) - escala * mm_arr.mean(axis=0)

        def converter(x_mm: float, y_mm: float) -> tuple[float, float]:
            return (escala * x_mm + transl[0], escala * y_mm + transl[1])
        return converter

    def converter(x_mm: float, y_mm: float) -> tuple[float, float]:
        return x_mm * px_mm_x, y_mm * px_mm_y
    return converter


# ---------------------------------------------------------------------------
# CALIBRAÇÃO LOCAL — CRUZES DE REFERÊNCIA (v3.12/v3.13/v3.14)
# ---------------------------------------------------------------------------
def _gerar_template_cruz(tamanho_px: int, braco_px: int,
                         espessura_px: int) -> np.ndarray:
    """Template de cruz '+' SÓLIDA (retângulos preenchidos).

    v3.14: casa com o desenho do pre_exame v5.5 (dois retângulos preenchidos
    que se sobrepõem no centro). O template matching reconhece a cruz maciça.
    """
    template = np.zeros((tamanho_px, tamanho_px), dtype=np.uint8)
    centro = tamanho_px // 2
    # Braço horizontal (retângulo preenchido)
    cv2.rectangle(template,
                  (centro - braco_px, centro - espessura_px // 2),
                  (centro + braco_px, centro + espessura_px // 2),
                  255, -1)
    # Braço vertical (retângulo preenchido)
    cv2.rectangle(template,
                  (centro - espessura_px // 2, centro - braco_px),
                  (centro + espessura_px // 2, centro + braco_px),
                  255, -1)
    return template


def _detectar_cruz(imagem: np.ndarray, x_mm: float, y_mm: float,
                   px_mm_x: float, px_mm_y: float) -> tuple[float, float] | None:
    """Detecta a cruz de referência perto de (x_mm, y_mm) — busca local.

    Usa template matching numa janela de ±CRUZ_JANELA_MM ao redor da
    posição esperada. Devolve o centro em px, ou None se não achar.
    """
    cx = int(round(x_mm * px_mm_x))
    cy = int(round(y_mm * px_mm_y))
    w = int(round(CRUZ_JANELA_MM * px_mm_x))
    h = int(round(CRUZ_JANELA_MM * px_mm_y))
    x0, y0 = max(0, cx - w), max(0, cy - h)
    x1, y1 = cx + w, cy + h
    regiao = imagem[y0:y1, x0:x1]
    if regiao.size == 0:
        return None
    cinza = cv2.cvtColor(regiao, cv2.COLOR_BGR2GRAY)
    braco_px = max(3, int(round(CRUZ_BRACO_MM * px_mm_x)))
    espessura_px = max(1, int(round(CRUZ_ESPESSURA_MM * px_mm_x)))
    tam = braco_px * 2 + 4
    template = _gerar_template_cruz(tam, braco_px, espessura_px)
    resultado = cv2.matchTemplate(cinza, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(resultado)
    if max_val < CRUZ_CONFIANCA_MIN:
        return None
    centro_x = x0 + max_loc[0] + tam // 2
    centro_y = y0 + max_loc[1] + tam // 2
    return float(centro_x), float(centro_y)


def _calibrar_por_marcadores(alinhada: np.ndarray,
                             marcadores: list[dict],
                             px_mm_x: float, px_mm_y: float):
    """Calcula o conversor LOCAL a partir das cruzes detectadas.

    Com 2+ cruzes: escala + translação (corrige deslocamento e escala da
    impressora NAQUELA região — linha ou rodapé).
    Sem cruzes suficientes: devolve None (o chamador usa o fallback global).
    """
    detectadas: list[tuple[float, float, float, float]] = []  # (x_px, y_px, x_mm, y_mm)
    for m in marcadores:
        centro = _detectar_cruz(alinhada, m["x_mm"], m["y_mm"], px_mm_x, px_mm_y)
        if centro is not None:
            detectadas.append((centro[0], centro[1], m["x_mm"], m["y_mm"]))

    if len(detectadas) >= 2:
        melhor_par = None
        melhor_dist = -1.0
        for i in range(len(detectadas)):
            for j in range(i + 1, len(detectadas)):
                d_mm = ((detectadas[i][2] - detectadas[j][2]) ** 2 +
                        (detectadas[i][3] - detectadas[j][3]) ** 2) ** 0.5
                if d_mm > melhor_dist:
                    melhor_dist = d_mm
                    melhor_par = (i, j)
        i, j = melhor_par
        p1, p2 = detectadas[i], detectadas[j]
        d_mm = ((p1[2] - p2[2]) ** 2 + (p1[3] - p2[3]) ** 2) ** 0.5
        d_px = ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
        escala = d_px / d_mm if d_mm > 0 else px_mm_x
        centro_mm_x = (p1[2] + p2[2]) / 2
        centro_mm_y = (p1[3] + p2[3]) / 2
        centro_px_x = (p1[0] + p2[0]) / 2
        centro_px_y = (p1[1] + p2[1]) / 2
        transl_x = centro_px_x - escala * centro_mm_x
        transl_y = centro_px_y - escala * centro_mm_y

        def converter(x_mm: float, y_mm: float) -> tuple[float, float]:
            return escala * x_mm + transl_x, escala * y_mm + transl_y
        return converter

    return None  # sem cruzes suficientes — usar fallback global


# ---------------------------------------------------------------------------
# Medição e classificação de balões
# ---------------------------------------------------------------------------
def medir_balao(imagem: np.ndarray, x_mm: float, y_mm: float, r_mm: float,
                px_mm_x: float, px_mm_y: float) -> dict:
    """Mede escuridão adaptativa + conectividade do INTERIOR do balão.
    Usa recuo de 20% — a borda do balão (e linhas adjacentes) ficam FORA
    da área medida, evitando falsos positivos.
    """
    cx = int(round(x_mm * px_mm_x))
    cy = int(round(y_mm * px_mm_y))
    r = max(1, int(round(r_mm * px_mm_x)))
    recuo = max(1, int(round(r * 0.2)))
    x0, y0 = max(0, cx - r + recuo), max(0, cy - r + recuo)
    x1, y1 = cx + r - recuo, cy + r - recuo
    if x1 <= x0 or y1 <= y0:
        return {"taxa_escuros": 0.0, "fracao_blob": 0.0, "fora_da_imagem": True}
    interior = imagem[y0:y1, x0:x1]
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


def medir_balao_calibrado(imagem: np.ndarray, x_mm: float, y_mm: float,
                          r_mm: float, converter, px_mm_x: float,
                          px_mm_y: float) -> dict:
    """medir_balao com coordenadas CORRIGIDAS pela calibração (QRs ou cruzes).

    O centro do balão é convertido pela função de calibração (que absorve
    o deslocamento/escala da impressora). O raio usa a escala nominal.
    """
    cx_f, cy_f = converter(x_mm, y_mm)
    cx = int(round(cx_f))
    cy = int(round(cy_f))
    r = max(1, int(round(r_mm * px_mm_x)))
    recuo = max(1, int(round(r * 0.2)))
    x0, y0 = max(0, cx - r + recuo), max(0, cy - r + recuo)
    x1, y1 = cx + r - recuo, cy + r - recuo
    if x1 <= x0 or y1 <= y0:
        return {"taxa_escuros": 0.0, "fracao_blob": 0.0, "fora_da_imagem": True}
    interior = imagem[y0:y1, x0:x1]
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


def classificar_balao(medida: dict) -> str:
    """Classifica o balão: 'marcado' | 'vazio' | 'suspeito' | 'erro'."""
    if medida is None or medida.get("fora_da_imagem"):
        return "erro"
    if (medida["taxa_escuros"] >= LIMIAR_TAXA
            and medida["fracao_blob"] >= LIMIAR_BLOB):
        return "marcado"
    if (medida["taxa_escuros"] < LIMIAR_VAZIO_TAXA
            and medida["fracao_blob"] < LIMIAR_VAZIO_BLOB):
        return "vazio"
    return "suspeito"


def _ler_qr_em_mm(imagem: np.ndarray, box_mm: dict,
                  px_mm_x: float, px_mm_y: float,
                  padding_mm: float = _QR_ALUNO_PADDING_MM) -> str | None:
    """Lê o QR numa região definida em mm, com PADDING ao redor."""
    x = max(0, int(round((box_mm["x"] - padding_mm) * px_mm_x)))
    y = max(0, int(round((box_mm["y"] - padding_mm) * px_mm_y)))
    w = int(round((box_mm["w"] + 2 * padding_mm) * px_mm_x))
    h = int(round((box_mm["h"] + 2 * padding_mm) * px_mm_y))
    regiao = imagem[y:y + h, x:x + w]
    if regiao.size == 0:
        return None
    return decodificar_qr_com_prefixo(regiao, "ALUNO")


def _qr_aluno_fallback(imagem: np.ndarray, px_mm_x: float, px_mm_y: float,
                       num_aluno: int) -> str | None:
    """Fallback: decodifica TODOS os QRs da imagem e escolhe o mais próximo
    da posição esperada do aluno (num_aluno)."""
    esperado_x = _QR_ALUNO_CAB_X_MM[num_aluno - 1]
    esperado_y = _QR_ALUNO_CAB_Y_MM + _QR_ALUNO_CAB_TAM_MM / 2
    melhor = None
    melhor_dist = float("inf")
    try:
        from pyzbar.pyzbar import decode
    except Exception:  # noqa: BLE001
        return None
    for img in [imagem] + variantes_qr(imagem):
        try:
            simbolos = decode(img)
        except Exception:  # noqa: BLE001
            continue
        for obj in simbolos:
            if obj.type != "QRCODE" or len(obj.polygon) < 4:
                continue
            dados = obj.data.decode("utf-8", errors="replace")
            if not dados or "ALUNO" not in dados:
                continue
            pts = np.array([[p.x, p.y] for p in obj.polygon], dtype="float32")
            cx_mm = float(pts[:, 0].mean()) / px_mm_x
            cy_mm = float(pts[:, 1].mean()) / px_mm_y
            dist = ((cx_mm - esperado_x) ** 2 + (cy_mm - esperado_y) ** 2) ** 0.5
            if dist < melhor_dist:
                melhor_dist = dist
                melhor = dados
    return melhor


def ler_qrs_alunos_pyzbar(imagem: np.ndarray) -> list[dict]:
    """Lê TODOS os QRs dos alunos (payload ALUNO=...) na imagem, via pyzbar."""
    try:
        from pyzbar.pyzbar import decode
    except Exception:  # noqa: BLE001
        return []
    candidatas: list[np.ndarray] = [imagem]
    if imagem.ndim == 3:
        candidatas.append(cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY))
    alunos: list[dict] = []
    for img in candidatas:
        try:
            simbolos = decode(img)
        except Exception:  # noqa: BLE001
            continue
        for obj in simbolos:
            if obj.type != "QRCODE" or len(obj.polygon) < 4:
                continue
            dados = obj.data.decode("utf-8", errors="replace")
            if not dados or "ALUNO=" not in dados:
                continue
            meta = parse_payload_qr(dados)
            alunos.append({
                "id": meta.get("aluno"),
                "faixa": meta.get("faixa"),
                "payload": dados,
            })
        if alunos:
            break
    return alunos


# ---------------------------------------------------------------------------
# Processamento de um aluno (uma linha da folha)
# ---------------------------------------------------------------------------
def _processar_aluno(alinhada: np.ndarray, baloes_aluno: list[dict],
                     converter_linha, conversores_obs: dict,
                     px_mm_x: float, px_mm_y: float) -> dict:
    """Processa uma linha de aluno: frequência por critério + presença + obs.

    v3.14: balões de observação usam o conversor LOCAL do rodapé (cruzes da
    margem, bloco 0); os demais balões usam o conversor da linha.
    """
    criterios: dict[tuple[str, int], dict[int, str]] = {}
    presenca: bool | None = None
    obs: dict[str, str] = {}
    for b in baloes_aluno:
        # Escolhe o conversor conforme o tipo do balão.
        if b.get("tipo") in ("obs_p", "obs_m"):
            converter = conversores_obs.get(0, converter_linha)  # rodapé global
        else:
            converter = converter_linha
        medida = medir_balao_calibrado(alinhada, b["x_mm"], b["y_mm"],
                                       b["r_mm"], converter, px_mm_x, px_mm_y)
        status = classificar_balao(medida)
        tipo = b.get("tipo")
        if tipo == "presenca":
            presenca = (status == "marcado")
        elif tipo == "criterio":
            criterios.setdefault((b["quesito"], b["criterio"]),
                                 {})[b["balao"]] = status
        elif tipo in ("obs_p", "obs_m"):
            obs[f"{tipo}{b['indice']}"] = status
    frequencias: dict[str, dict[str, int]] = {}
    avisos: list[str] = []
    incidentes: list[str] = []
    for (quesito, criterio), baloes in criterios.items():
        marcados = [i for i, s in baloes.items() if s == "marcado"]
        suspeitos = [i for i, s in baloes.items() if s == "suspeito"]
        if len(marcados) == 1:
            freq = marcados[0]
        elif len(marcados) == 0:
            freq = 0
        else:
            freq = max(marcados)
            avisos.append(f"{quesito}.{criterio}: múltiplos balões marcados "
                          f"{marcados} — revisão manual")
        if suspeitos:
            incidentes.append(f"{quesito}.{criterio}")
        frequencias.setdefault(quesito, {})[str(criterio)] = freq
    marcadas = [chave for chave, s in obs.items() if s == "marcado"]
    avisos_obs = [f"{chave} suspeita — revisão manual"
                  for chave, s in obs.items() if s == "suspeito"]
    contradicoes: list[dict] = []
    for p, m in PARES_CONTRADICAO:
        if p in marcadas and m in marcadas:
            marcadas.remove(p)
            marcadas.remove(m)
            contradicoes.append({"par": [p, m], "anuladas": True})
    return {
        "frequencias": frequencias,
        "presenca": presenca,
        "observacoes_marcadas": sorted(marcadas),
        "avisos": avisos,
        "avisos_observacoes": avisos_obs,
        "contradicoes": contradicoes,
        "incidentes_auditoria": incidentes,
    }


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------
def processar_imagem(caminho_imagem: Path, base_cfg=None, faixa: str | None = None,
                     origem: str | None = None) -> list[dict]:
    """Fluxo completo -> lista de JSON v2.0 (um por aluno da folha).

    Args:
        caminho_imagem: PDF (renderizado a 300 DPI) ou PNG/JPG da folha.
        base_cfg: pasta config/ (padrão) OU caminho direto do JSON de
                  coordenadas.
        faixa: força a faixa; sem isso, a faixa vem do QR do aluno.
        origem: 'scanner' | 'foto' | None. Controla a normalização.

    Returns:
        Lista de resultados, um por aluno presente na folha (1-3).
    """
    imagem = carregar_imagem(caminho_imagem)
    payload = decodificar_qr_com_prefixo(imagem, "AVALIADOR")

    eh_pdf = caminho_imagem.suffix.lower() == ".pdf"
    if eh_pdf:
        alinhada = imagem
    elif origem == "scanner":
        if _parece_a4_ja_alinhada(imagem):
            largura, altura = A4_LANDSCAPE_PX
            alinhada = cv2.resize(imagem, (largura, altura),
                                  interpolation=cv2.INTER_AREA)
        else:
            alinhada = detectar_e_corrigir(imagem)
            fracao_preta = _fracao_preta(alinhada)
            if fracao_preta > _FRACAO_PRETA_MAX:
                raise ValueError(
                    f"folha cortada no scan (área preta de {fracao_preta:.0%}) — "
                    f"refaça o scan com a folha inteira no quadro")
    elif origem == "foto":
        alinhada = detectar_e_corrigir(imagem)
        fracao_preta = _fracao_preta(alinhada)
        if fracao_preta > _FRACAO_PRETA_MAX:
            raise ValueError(
                f"folha cortada na foto (área preta de {fracao_preta:.0%}) — "
                f"refaça a foto com a folha inteira no quadro")
    else:
        if _parece_a4_ja_alinhada(imagem):
            alinhada = imagem
        else:
            alinhada = detectar_e_corrigir(imagem)

    if not payload:
        payload = decodificar_qr_com_prefixo(alinhada, "AVALIADOR")
    if not payload:
        raise ValueError("QR do cabeçalho não encontrado — folha inválida ou sem QR")
    metadados_cab = parse_payload_qr(payload)

    altura_px, largura_px = alinhada.shape[:2]
    px_mm_x = largura_px / LARGURA_A4_MM
    px_mm_y = altura_px / ALTURA_A4_MM

    # Calibração GLOBAL pelos QRs (fallback quando não há cruzes na região).
    converter_global = _calibrar_conversor(alinhada, px_mm_x, px_mm_y)

    coordenadas_path = _resolver_coordenadas(
        base_cfg, metadados_cab, alinhada, px_mm_x, px_mm_y)
    baloes = carregar_coordenadas_baloes(coordenadas_path)

    qrs_alunos = ler_qrs_alunos_pyzbar(alinhada)

    # v3.14: conversor LOCAL do rodapé (2 cruzes globais na margem, y=202).
    marcadores_obs = [b for b in baloes if b.get("tipo") == "marcador_obs"]
    conversores_obs: dict[int, Any] = {}
    conv_rodape = _calibrar_por_marcadores(alinhada, marcadores_obs,
                                           px_mm_x, px_mm_y)
    conversores_obs[0] = (conv_rodape if conv_rodape is not None
                          else converter_global)

    # v3.14: ignora marcadores (cruzes) no agrupamento por aluno — eles não
    # têm o campo 'aluno' (são globais).
    baloes_por_aluno = [b for b in baloes if b.get("aluno") is not None]
    resultados: list[dict] = []
    for num_aluno in sorted({b["aluno"] for b in baloes_por_aluno}):
        baloes_aluno = [b for b in baloes_por_aluno if b["aluno"] == num_aluno]
        marcadores = [b for b in baloes_aluno if b.get("tipo") == "marcador"]
        baloes_medir = [b for b in baloes_aluno
                        if b.get("tipo") not in ("marcador", "marcador_obs")]

        # v3.12: calibração LOCAL por linha (cruzes de referência da linha).
        converter_linha = _calibrar_por_marcadores(
            alinhada, marcadores, px_mm_x, px_mm_y)
        if converter_linha is None:
            converter_linha = converter_global

        # QR do aluno no CABEÇALHO — posição define a linha.
        qr_box = {"x": _QR_ALUNO_CAB_X_MM[num_aluno - 1],
                  "y": _QR_ALUNO_CAB_Y_MM,
                  "w": _QR_ALUNO_CAB_TAM_MM, "h": _QR_ALUNO_CAB_TAM_MM}
        payload_aluno = _ler_qr_em_mm(alinhada, qr_box, px_mm_x, px_mm_y)

        if not payload_aluno:
            payload_aluno = _qr_aluno_fallback(
                alinhada, px_mm_x, px_mm_y, num_aluno)

        if not payload_aluno and qrs_alunos:
            if len(qrs_alunos) >= num_aluno:
                payload_aluno = qrs_alunos[num_aluno - 1]["payload"]

        metadados_aluno = (parse_payload_qr(payload_aluno)
                           if payload_aluno else {})
        faixa_efetiva = (metadados_aluno.get("faixa")
                         or (faixa or "").strip().lower() or None)
        processado = _processar_aluno(alinhada, baloes_medir,
                                      converter_linha, conversores_obs,
                                      px_mm_x, px_mm_y)
        if processado["presenca"] is False:
            status_presenca = "AUSENTE"
        elif processado["presenca"] is True:
            status_presenca = "PRESENTE"
        else:
            status_presenca = "PRESENCA_NAO_DETECTADA"
        resultado: dict[str, Any] = {
            "metadados": {
                "versao_schema": "2.0",
                "dojo_id": metadados_cab.get("dojo"),
                "exame_id": metadados_cab.get("exame"),
                "avaliador_id": metadados_cab.get("avaliador"),
                "aluno_id": metadados_aluno.get("aluno"),
                "faixa": faixa_efetiva,
            },
            "aluno": {
                "id": metadados_aluno.get("aluno"),
                "faixa_atual": faixa_efetiva,
                "presenca": status_presenca,
            },
            "avaliacoes": {
                q: {"frequencias": processado["frequencias"].get(q, {})}
                for q in QUESITOS
            },
            "observacoes_marcadas": processado["observacoes_marcadas"],
        }
        if processado["avisos"]:
            resultado["avisos"] = processado["avisos"]
        if processado["avisos_observacoes"]:
            resultado["avisos_observacoes"] = processado["avisos_observacoes"]
        if processado["contradicoes"]:
            resultado["contradicoes_observacoes"] = processado["contradicoes"]
        if processado["incidentes_auditoria"]:
            resultado["auditoria_visual"] = processado["incidentes_auditoria"]
        try:
            from core import observacoes
            resultado = observacoes.merge_no_json(resultado)
        except ImportError:
            pass
        resultados.append(resultado)
    return resultados