"""core/omr_reader.py — Leitura OMR dos gabaritos Karate-Ashi v2.0.

Pipeline:
1. carregar imagem (foto de celular ou scanner);
2. decodificar o QR Code na foto ORIGINAL (antes de qualquer alinhamento);
3. detectar a folha (contorno quadrangular robusto, multi-binarização);
4. se o contorno falhar (folha cortada na foto, fundo claro fundindo com o
   papel): âncora QR + cruzes de registro (fiduciais) para o warp;
5. corrigir a perspectiva (warpPerspective);
6. extrair as ROIs dos checkboxes (config/coordenadas/<faixa>.json);
7. classificar densidade de pixels (omr_thresholds.json);
8. validar (contiguidade, suspeitos, folha em branco, limite 7);
9. anular contradições de observação (v2col-3.0) e gerar JSON schema v2.0.

Coordenadas:
o JSON da faixa guarda x,y,w,h em MILÍMETROS, com origem no canto superior
esquerdo da folha A4. O leitor converte para pixels usando o tamanho real da
imagem já alinhada — por isso a mesma coordenada vale para qualquer resolução
de foto ou scanner. O gerador é o tools/pre_exame.py (folha e leitor gêmeos
por construção); coordenadas não calibradas (tudo zero) são rejeitadas com
mensagem clara, em vez de produzir nota vazia.

Robustez para foto de celular (v2col-2.9):
- O QR é decodificado PRIMEIRO na foto original. Se o recorte de perspectiva
  sair errado, o QR da foto crua ainda é lido.
- A detecção da folha testa TRÊS binarizações (Otsu normal, Otsu invertido e
  Canny) e valida borda e retangularidade.
- Fallback de âncora: quando o contorno falha (folha cortada no quadro ou
  fundo claro), o QR (localizado pelo pyzbar — o detector nativo do OpenCV
  falha em foto) + as cruzes de registro dos 3 cantos estimam a homografia
  da página e fazem o warp direto para a geometria A4. As cruzes só entram
  se passarem em score e distância; a homografia refinada só é aceita se
  continuar respeitando a posição do QR — senão cai para a homografia só do
  QR antes de desistir.
- Guarda de folha cortada: se o warp deixar área preta > 15% (região fora da
  foto), o leitor recusa com mensagem clara em vez de ler lixo.

Observações estruturadas (Fase 04 v2col-2.8) e contradições (v2col-3.0):
- A observação nasce na FOLHA como checkboxes (obs_p1..p8 'Ótimo!' e
  obs_m1..m8 'A Melhorar'), lidos AQUI na mesma passada dos códigos de erro.
- Regra de contradição: se o MESMO avaliador (uma folha) marca o par
  contraditório ('Ótimo!' + 'A melhorar' oposto), as DUAS são anuladas e a
  contradição é registrada em resultado['contradicoes_observacoes'] para o
  mestre refinar com o avaliador no relatório geral.
- O vocabulário dos pares é data-driven (config/observacoes_contradicoes.json
  via core/contradicoes.py) — o mestre ajusta sem tocar no código.

Correção Fase 07: import do pyzbar movido para DENTRO de decodificar_qr()
(lazy import). O pyzbar depende da biblioteca nativa libzbar0, ausente no
runner ubuntu-latest do GitHub Actions. Com o import local, as funções puras
não dependem da lib nativa e o módulo importa sem quebrar em qualquer
ambiente.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# NOTA: NÃO importar pyzbar aqui no topo.
# O import acontece dentro de decodificar_qr() e localizar_qr().

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

# Dimensões A4 em mm — base da conversão mm -> px das coordenadas.
LARGURA_A4_MM = 210.0
ALTURA_A4_MM = 297.0

# --- Detecção da folha (robustez p/ foto) ---------------------------------
_EPSILON_CANDIDATOS = (0.010, 0.015, 0.020, 0.025, 0.030)
_AREA_MINIMA = 0.05             # fração mínima da imagem
_RETANGULARIDADE_MINIMA = 0.80  # área do contorno / área do retângulo mínimo
_MARGEM_BORDA = 0.02            # fração do menor lado
_LADO_DETECCAO_PX = 1600        # downscale p/ detecção (velocidade)

# --- Âncora QR + fiduciais (fallback p/ folha cortada) ---------------------
_QR_LADO_MM = 22.0
_QR_MARGEM_MM = 10.0
_FIDUCIAL_MARGEM_MM = 8.0
_FIDUCIAL_TOLERANCIA_MM = 6.0    # desvio máx. do centro previsto
_FIDUCIAL_SCORE_MIN = 0.50       # match mínimo do template da cruz
_QR_ERRO_MAX_FRACAO = 0.15       # erro máx. da refinada vs QR (fração do lado)
_RAZAO_A4_MIN = 0.60             # razão largura/altura aceitável (A4 ≈ 0.707)
_RAZAO_A4_MAX = 0.85
_LADO_MIN_PX = 50
_FRACAO_PRETA_MAX = 0.15         # guarda de folha cortada no warp

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

# --- QR Code ---------------------------------------------------------------

def variantes_qr(imagem: np.ndarray) -> list[np.ndarray]:
    """Variantes de pré-processamento para o leitor de QR.

    Foto de celular falha por escala/contraste/foco; tentar a imagem crua,
    em cinza, reescalada, nítida e binarizada multiplica as chances.
    """
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
    # nitidez (unsharp): realça as bordas do QR
    nitido = cv2.addWeighted(cinza, 1.6,
                             cv2.GaussianBlur(cinza, (0, 0), 3.0), -0.6, 0)
    variantes.append(nitido)
    # binarização adaptativa (contraste local — QR em sombra/reflexo)
    variantes.append(cv2.adaptiveThreshold(
        cinza, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10))
    _, otsu = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variantes.append(otsu)
    return variantes

def decodificar_qr(imagem: np.ndarray) -> str | None:
    """Decodifica o primeiro QR encontrado; devolve o texto ou None.

    Ordem: leitor nativo do OpenCV (não depende da libzbar) e, em seguida,
    pyzbar sobre as variantes pré-processadas. O import do pyzbar segue
    local — correção Fase 07.
    """
    try:
        detector = cv2.QRCodeDetector()
        dados, _, _ = detector.detectAndDecode(imagem)
        if dados:
            return dados
    except Exception:  # noqa: BLE001 — cv2 pode falhar em imagens ruins
        pass

    try:
        from pyzbar.pyzbar import decode  # import local — correção Fase 07
    except Exception:  # noqa: BLE001 — libzbar0 ausente
        return None

    for variante in variantes_qr(imagem):
        try:
            simbolos = decode(variante)
        except Exception:  # noqa: BLE001 — pyzbar pode falhar em imagem ruim
            continue
        for obj in simbolos:
            texto = obj.data.decode("utf-8", errors="replace")
            if texto:
                return texto
    return None

def parse_payload_qr(payload: str) -> dict:
    """KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA -> dict de metadados."""
    partes = [p.strip() for p in payload.split("|")]
    if len(partes) != 6 or partes[0] != "KA":
        raise ValueError(f"payload QR inválido: {payload!r}")
    return {
        "versao_schema": "2.0",
        "dojo_id": partes[1],
        "exame_id": partes[2],
        "aluno_id": partes[3],
        "avaliador_id": partes[4],
        "faixa": partes[5],
    }

# --- Detecção e correção de perspectiva ------------------------------------

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

def _pontos_quadrilatero(contorno: np.ndarray) -> int:
    """Nº de vértices do contorno (para a mensagem de erro)."""
    peri = cv2.arcLength(contorno, True)
    if peri <= 0:
        return 0
    hull = cv2.convexHull(contorno)
    return len(cv2.approxPolyDP(hull, 0.02 * peri, True))

def _toca_borda(pts: np.ndarray, largura: int, altura: int,
                margem: float) -> bool:
    """True se algum canto está colado na borda (contorno do fundo/moldura)."""
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

# --- Âncora QR + fiduciais (fallback) --------------------------------------

def _pontos_mm_qr() -> np.ndarray:
    """Cantos do QR em mm, origem no topo-esquerda da página A4.

    Desenhado pelo tools/pre_exame.py no canto superior direito, com
    QR_LADO_MM=22 e QR_MARGEM_MM=10 (margem do topo e da direita).
    """
    x0 = LARGURA_A4_MM - _QR_MARGEM_MM - _QR_LADO_MM
    y0 = _QR_MARGEM_MM
    return np.array([
        [x0, y0],
        [x0 + _QR_LADO_MM, y0],
        [x0 + _QR_LADO_MM, y0 + _QR_LADO_MM],
        [x0, y0 + _QR_LADO_MM],
    ], dtype="float32")

def _pontos_mm_fiduciais() -> np.ndarray:
    """Centros das cruzes de registro em mm (origem topo-esquerda).

    Três cantos (TL, BR, BL) — o QR no canto superior direito é a 4ª
    referência. Desenhados por desenhar_marcadores_fiduciais().
    """
    m = _FIDUCIAL_MARGEM_MM
    return np.array([
        [m, m],
        [LARGURA_A4_MM - m, ALTURA_A4_MM - m],
        [m, ALTURA_A4_MM - m],
    ], dtype="float32")

def localizar_qr(imagem: np.ndarray) -> tuple[np.ndarray, str] | None:
    """Localiza o QR na imagem e devolve (pontos_px_ordenados, dados).

    O detector nativo do OpenCV (cv2.QRCodeDetector) falha em foto de
    celular; o pyzbar decodifica e devolve o polígono do QR — é ele que
    alimenta a âncora do warp.
    """
    try:
        from pyzbar.pyzbar import decode
    except Exception:
        return None
    candidatas: list[np.ndarray] = [imagem]
    if imagem.ndim == 3:
        candidatas.append(cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY))
    for img in candidatas:
        try:
            simbolos = decode(img)
        except Exception:
            continue
        for obj in simbolos:
            if obj.type != "QRCODE" or len(obj.polygon) < 4:
                continue
            dados = obj.data.decode("utf-8", errors="replace")
            if not dados:
                continue
            pontos = np.array([[p.x, p.y] for p in obj.polygon],
                              dtype="float32")
            return _ordenar_cantos(pontos), dados
    return None

def _template_fiducial(escala_px_mm: float) -> np.ndarray:
    """Template da cruz de registro (cruz + quadrado central), na escala.

    A cruz é impressa PRETA sobre papel branco — o template reproduz a mesma
    polaridade (cruz escura 0 em fundo claro 255) para casar com o
    TM_CCOEFF_NORMED.
    """
    braco = max(4, int(round(3.0 * escala_px_mm)))
    esp = max(1, int(round(0.3 * escala_px_mm)))
    tam = braco * 2 + 1
    t = np.full((tam, tam), 255, dtype=np.uint8)   # fundo branco
    c = tam // 2
    t[c - esp:c + esp + 1, :] = 0
    t[:, c - esp:c + esp + 1] = 0
    t[c - braco:c + braco + 1, c - braco:c - braco + esp + 1] = 0
    t[c - braco:c + braco + 1, c + braco - esp:c + braco + 1] = 0
    t[c - braco:c - braco + esp + 1, c - braco:c + braco + 1] = 0
    t[c + braco - esp:c + braco + 1, c - braco:c + braco + 1] = 0
    return t

def _detectar_fiducial(imagem: np.ndarray, centro_predito: np.ndarray,
                       escala_px_mm: float) -> np.ndarray | None:
    """Procura a cruz de registro perto do centro previsto (template match).

    Só aceita cruz com score alto E próxima da previsão — o match frouxo
    gerava falsos positivos que corrompiam a homografia.
    """
    h, w = imagem.shape[:2]
    janela = int(round(_FIDUCIAL_TOLERANCIA_MM * escala_px_mm)) + 12
    cx, cy = int(round(centro_predito[0])), int(round(centro_predito[1]))
    x0 = max(0, cx - janela); x1 = min(w, cx + janela)
    y0 = max(0, cy - janela); y1 = min(h, cy + janela)
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    regiao = imagem[y0:y1, x0:x1]
    cinza = cv2.cvtColor(regiao, cv2.COLOR_BGR2GRAY)
    template = _template_fiducial(escala_px_mm)
    if template.shape[0] > cinza.shape[0] or template.shape[1] > cinza.shape[1]:
        return None
    res = cv2.matchTemplate(cinza, template, cv2.TM_CCOEFF_NORMED)
    _, mx, _, mloc = cv2.minMaxLoc(res)
    if mx < _FIDUCIAL_SCORE_MIN:
        return None
    c = template.shape[0] // 2
    centro = np.array([x0 + mloc[0] + c, y0 + mloc[1] + c], dtype="float32")
    if np.linalg.norm(centro - centro_predito) > _FIDUCIAL_TOLERANCIA_MM * escala_px_mm:
        return None
    return centro

def _quad_folha_plausivel(cantos: np.ndarray) -> bool:
    """Valida se os 4 cantos formam uma página A4 retrato plausível."""
    ordem = _ordenar_cantos(cantos)
    largura = max(float(np.linalg.norm(ordem[1] - ordem[0])),
                  float(np.linalg.norm(ordem[2] - ordem[3])))
    altura = max(float(np.linalg.norm(ordem[3] - ordem[0])),
                 float(np.linalg.norm(ordem[2] - ordem[1])))
    if largura < _LADO_MIN_PX or altura < _LADO_MIN_PX:
        return False
    razao = largura / altura
    return _RAZAO_A4_MIN <= razao <= _RAZAO_A4_MAX

def warp_pela_ancora(imagem: np.ndarray, pontos_qr_px: np.ndarray) -> np.ndarray:
    """Warp da folha usando o QR + cruzes de registro como âncoras.

    O QR dá a homografia base (exata pelos 4 cantos detectados). As cruzes
    só refinam se passarem na validação; a refinada é aceita apenas se
    continuar respeitando a posição do QR. Se nada for plausível, cai para
    a homografia só do QR antes de desistir.
    """
    # ATENÇÃO: cv2.findHomography retorna (H, mask) — precisa desempacotar.
    H_qr, _ = cv2.findHomography(_pontos_mm_qr(), pontos_qr_px)
    if H_qr is None:
        raise ValueError("não foi possível estimar a homografia do QR")

    escala = float(np.linalg.norm(pontos_qr_px[1] - pontos_qr_px[0])) / _QR_LADO_MM
    pagina_mm = np.array([[0, 0], [LARGURA_A4_MM, 0],
                          [LARGURA_A4_MM, ALTURA_A4_MM], [0, ALTURA_A4_MM]],
                         dtype="float32")
    pagina_rs = pagina_mm.reshape(-1, 1, 2)

    # Refino com fiduciais validados
    mm_pts = list(_pontos_mm_qr())
    px_pts = [tuple(p) for p in pontos_qr_px]
    preditos = cv2.perspectiveTransform(
        _pontos_mm_fiduciais().reshape(-1, 1, 2), H_qr).reshape(-1, 2)
    for mm_pt, pred in zip(_pontos_mm_fiduciais(), preditos):
        centro = _detectar_fiducial(imagem, pred, escala)
        if centro is not None:
            mm_pts.append(mm_pt)
            px_pts.append(tuple(centro))

    H_refinada = None
    if len(mm_pts) > 4:
        H_refinada, _ = cv2.findHomography(
            np.array(mm_pts, dtype="float32"),
            np.array(px_pts, dtype="float32"), cv2.RANSAC)
        if H_refinada is not None:
            qr_prev = cv2.perspectiveTransform(
                _pontos_mm_qr().reshape(-1, 1, 2), H_refinada).reshape(-1, 2)
            erro = float(np.mean(np.linalg.norm(qr_prev - pontos_qr_px, axis=1)))
            if erro > _QR_ERRO_MAX_FRACAO * _QR_LADO_MM * escala:
                H_refinada = None

    for H in (H_refinada, H_qr):
        if H is None:
            continue
        cantos = cv2.perspectiveTransform(pagina_rs, H).reshape(-1, 2)
        if _quad_folha_plausivel(cantos):
            return _warp(imagem, _ordenar_cantos(cantos))

    raise ValueError("não foi possível estimar a folha pelas âncoras "
                     "(QR/fiduciais) — refaça a foto com a folha inteira "
                     "e boa luz")

def _fracao_preta(imagem: np.ndarray) -> float:
    """Fração de pixels quase pretos (área fora da foto no warp)."""
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cinza < 30))

def detectar_e_corrigir(imagem: np.ndarray) -> np.ndarray:
    """Detecta a folha e corrige a perspectiva (robusto p/ foto de celular).

    Estratégia:
    1. reduz a imagem p/ detecção (velocidade e menos ruído);
    2. binariza por três vias — cobre folha clara s/ fundo escuro e vice-versa;
    3. para cada contorno grande, tenta um quadrilátero convexo e valida borda
       (rejeita o contorno da própria imagem/fundo) e retangularidade;
    4. escolhe o melhor candidato por área × retangularidade;
    5. se nada passar (folha cortada na foto, fundo claro fundindo com o
       papel), usa o QR + cruzes de registro como âncoras do warp.
    """
    if imagem is None or imagem.size == 0:
        raise ValueError("imagem vazia")

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
    houve_forma = False
    forma_pts = 0

    for binaria in binarizacoes(cinza):
        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        for contorno in contornos:
            area = cv2.contourArea(contorno)
            if area < _AREA_MINIMA * area_img:
                continue
            quad = _quatro_cantos(contorno)
            if quad is None:
                pts = contorno.reshape(-1, 2).astype("float32")
                if not _toca_borda(pts, largura, altura, margem):
                    houve_forma = True
                    forma_pts = _pontos_quadrilatero(contorno)
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
        # Fallback: folha cortada na foto ou fundo claro fundindo com o
        # papel — usa o QR + cruzes de registro como âncoras do warp.
        local = localizar_qr(imagem)
        if local is not None:
            pontos_qr, _ = local
            return warp_pela_ancora(imagem, pontos_qr)
        if houve_forma:
            raise ValueError(
                f"folha não detectada como quadrilátero ({forma_pts} pontos) — "
                f"enquadre a folha inteira, com as quatro bordas visíveis e "
                f"bom contraste")
        raise ValueError("nenhum contorno de folha encontrado")

    if escala < 1.0:
        melhor = melhor / escala
    return _warp(imagem, _ordenar_cantos(melhor))

# --- Classificação e validação ---------------------------------------------

def classificar_checkbox(roi: np.ndarray, limiares: dict) -> str:
    """Classifica uma ROI: 'vazio' | 'suspeito' | 'marcado'."""
    cinza = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(cinza, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    densidade = float(np.count_nonzero(binaria)) / binaria.size
    if densidade <= limiares["limiar_vazio_max"]:
        return "vazio"
    if densidade <= limiares["limiar_suspeito_max"]:
        return "suspeito"
    return "marcado"

def contar_marcacoes_linha(classificacoes: list[str], limiares: dict) -> dict:
    """Conta marcações de uma linha de 7 checkboxes e valida contiguidade."""
    marcados = [i + 1 for i, c in enumerate(classificacoes) if c == "marcado"]
    suspeitos = [i + 1 for i, c in enumerate(classificacoes) if c == "suspeito"]
    avisos: list[str] = []
    if suspeitos:
        avisos.append(f"caixas suspeitas: {suspeitos} — revisão manual")
    if marcados and marcados != list(range(1, max(marcados) + 1)):
        avisos.append(f"marcação não-contígua: {marcados} (processado, verificar)")
    return {"frequencia": len(marcados), "avisos": avisos}

def validar_folha(frequencias: dict[str, dict]) -> list[str]:
    """Regras globais: folha em branco é rejeitada; limite 7 por critério."""
    erros: list[str] = []
    total = 0
    for quesito, criterios in frequencias.items():
        for chave, info in criterios.items():
            total += info["frequencia"]
            if info["frequencia"] > 7:
                erros.append(f"{quesito}.{chave}: mais de 7 marcações")
    if total == 0:
        erros.append("folha sem nenhuma marcação — verificar digitalização")
    return erros

def roi_mm_para_px(roi_mm: dict, largura_px: int, altura_px: int) -> dict:
    """Converte uma ROI em mm (origem no topo-esquerda) para pixels da imagem
    alinhada — usa o tamanho REAL da imagem, então vale para qualquer
    resolução de foto ou scanner."""
    px_mm_x = largura_px / LARGURA_A4_MM
    px_mm_y = altura_px / ALTURA_A4_MM
    x = round(float(roi_mm["x"]) * px_mm_x)
    y = round(float(roi_mm["y"]) * px_mm_y)
    w = round(float(roi_mm["w"]) * px_mm_x)
    h = round(float(roi_mm["h"]) * px_mm_y)
    return {"x": x, "y": y, "w": w, "h": h}

def _validar_coordenadas(coordenadas: dict, faixa: str) -> None:
    """Rejeita coordenadas não calibradas (placeholders em zero).

    Sem isso, um arquivo com x=0,y=0 faz o leitor ler o canto da imagem e
    produzir nota silenciosamente errada. Também exige a seção 'observacoes'
    (Fase 04 v2col-2.8) — sem ela, a folha não tem observações para ler.
    """
    for quesito in QUESITOS:
        linhas = coordenadas.get(quesito, {})
        if not linhas:
            raise ValueError(
                f"coordenadas sem o quesito '{quesito}' na faixa '{faixa}' — "
                f"gere as folhas com tools/pre_exame.py (que grava "
                f"config/coordenadas/{faixa}.json)")
        for chave, roi in linhas.items():
            if float(roi.get("x", 0)) == 0 and float(roi.get("y", 0)) == 0:
                raise ValueError(
                    f"coordenadas não calibradas em '{faixa}.{quesito}.{chave}' "
                    f"(x=0, y=0) — gere as folhas com tools/pre_exame.py")
    obs = coordenadas.get("observacoes", {})
    if not obs:
        raise ValueError(
            f"coordenadas sem a seção 'observacoes' na faixa '{faixa}' — "
            f"gere as folhas com tools/pre_exame.py (v2col-2.8)")
    for chave, roi in obs.items():
        if float(roi.get("x", 0)) == 0 and float(roi.get("y", 0)) == 0:
            raise ValueError(
                f"coordenadas não calibradas em '{faixa}.observacoes.{chave}' "
                f"(x=0, y=0) — gere as folhas com tools/pre_exame.py")

# --- Pipeline completo -----------------------------------------------------

def processar_imagem(caminho_imagem: Path, base_cfg: Path, faixa: str) -> dict:
    """Fluxo completo com layout da faixa -> JSON v2.0.

    Coordenadas em mm (config/coordenadas/<faixa>.json) são convertidas para
    pixels pelo tamanho real da imagem alinhada. As observações estruturadas
    (seção 'observacoes') são lidas na mesma passada dos códigos de erro e
    devolvidas como 'observacoes_marcadas'; core/observacoes.py monta o texto
    legível em 'observacao_montada'. Contradições (v2col-3.0) anulam pares
    Ótimo/A melhorar do mesmo avaliador e são registradas em
    'contradicoes_observacoes' para o relatório geral.
    """
    limiares = carregar_json(base_cfg / "omr_thresholds.json")
    coordenadas = carregar_json(base_cfg / "coordenadas" / f"{faixa}.json")
    _validar_coordenadas(coordenadas, faixa)

    imagem = cv2.imread(str(caminho_imagem))
    if imagem is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho_imagem}")

    # QR: tenta na foto ORIGINAL antes do alinhamento — se o recorte de
    # perspectiva sair errado, o QR da foto crua ainda é decodificável.
    payload = decodificar_qr(imagem)

    alinhada = detectar_e_corrigir(imagem)

    # Guarda de folha cortada: área preta no warp = região fora da foto.
    fracao_preta = _fracao_preta(alinhada)
    if fracao_preta > _FRACAO_PRETA_MAX:
        raise ValueError(
            f"folha cortada na foto (área preta de {fracao_preta:.0%}) — "
            f"refaça a foto com a folha inteira no quadro")

    altura_px, largura_px = alinhada.shape[:2]

    if not payload:
        payload = decodificar_qr(alinhada)
    if not payload:
        raise ValueError("QR Code não encontrado — folha inválida ou sem QR")

    metadados = parse_payload_qr(payload)

    # A faixa do QR deve bater com a faixa esperada (validação cruzada):
    if metadados.get("faixa", "").lower() != faixa.lower():
        raise ValueError(
            f"faixa do QR ({metadados.get('faixa')}) difere do "
            f"layout carregado ({faixa})")

    frequencias: dict[str, dict[str, Any]] = {}
    for quesito in QUESITOS:
        frequencias[quesito] = {}
        for chave, roi_mm in coordenadas.get(quesito, {}).items():
            roi_px = roi_mm_para_px(roi_mm, largura_px, altura_px)
            x, y, w, h = roi_px["x"], roi_px["y"], roi_px["w"], roi_px["h"]
            if w < 7:
                raise ValueError(
                    f"ROI estreita demais em {quesito}.{chave} (w={w}px) — "
                    f"coordenadas incorretas ou imagem muito pequena")
            roi = alinhada[y:y + h, x:x + w]
            passo = w // 7
            classes = []
            for i in range(7):
                celula = roi[:, i * passo:(i + 1) * passo]
                classes.append(classificar_checkbox(celula, limiares))
            frequencias[quesito][chave] = contar_marcacoes_linha(classes, limiares)

    erros = validar_folha(frequencias)
    if erros:
        raise ValueError("; ".join(erros))

    # ------------------------------------------------------------------
    # Observações estruturadas (Fase 04 v2col-2.8): cada ROI da seção
    # 'observacoes' é um checkbox individual (obs_p1..p8, obs_m1..m8).
    # ------------------------------------------------------------------
    marcadas: list[str] = []
    avisos_obs: list[str] = []
    for chave, roi_mm in coordenadas.get("observacoes", {}).items():
        roi_px = roi_mm_para_px(roi_mm, largura_px, altura_px)
        x, y, w, h = roi_px["x"], roi_px["y"], roi_px["w"], roi_px["h"]
        if w < 3 or h < 3:
            raise ValueError(
                f"ROI pequena demais em observacoes.{chave} ({w}x{h}px) — "
                f"coordenadas incorretas ou imagem muito pequena")
        roi = alinhada[y:y + h, x:x + w]
        classe = classificar_checkbox(roi, limiares)
        if classe == "marcado":
            marcadas.append(chave)
        elif classe == "suspeito":
            avisos_obs.append(f"{chave} suspeita — revisão manual")

    # ------------------------------------------------------------------
    # Contradições (v2col-3.0): par Ótimo/A melhorar do MESMO avaliador.
    # As duas observações são anuladas e a contradição vai ao relatório.
    # IMPORTA: precisa rodar ANTES do merge_no_json (o texto motado já
    # sai sem as observações anuladas).
    # ------------------------------------------------------------------
    from core import contradicoes as mod_contradicoes
    pares = mod_contradicoes.carregar_pares(base_cfg)
    marcadas, lista_contradicoes = mod_contradicoes.detectar(marcadas, pares)

    resultado = {
        "metadados": metadados,
        "aluno": {"id": metadados["aluno_id"], "faixa_atual": metadados["faixa"]},
        "avaliacoes": {
            q: {"frequencias": {k: v["frequencia"]
                                for k, v in criterios.items()}}
            for q, criterios in frequencias.items()
        },
        "observacoes_marcadas": sorted(marcadas),
    }
    if avisos_obs:
        resultado["avisos_observacoes"] = avisos_obs
    if lista_contradicoes:
        resultado["contradicoes_observacoes"] = lista_contradicoes

    # Observação legível do relatório: as chaves marcadas viram texto via
    # core/observacoes.py (vocabulário oficial — folha e relatório gêmeos).
    try:
        from core import observacoes
        resultado = observacoes.merge_no_json(resultado)
    except ImportError:
        pass

    return resultado