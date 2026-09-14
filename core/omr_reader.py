"""core/omr_reader.py — Leitura OMR dos gabaritos Karate-Ashi v2.0.

Pipeline:
1. carregar imagem (foto de celular ou scanner);
2. detectar a folha (maior contorno quadrangular);
3. corrigir perspectiva (warpPerspective);
4. decodificar QR Code (pyzbar) e extrair metadados;
5. extrair as ROIs dos checkboxes (config/coordenadas/.json);
6. classificar densidade de pixels (omr_thresholds.json);
7. validar (contiguidade, suspeitos, folha em branco, limite 7);
8. gerar JSON intermediário schema v2.0.

Coordenadas: o JSON da faixa guarda x,y,w,h em MILÍMETROS, com origem no
canto superior esquerdo da folha A4. O leitor converte para pixels usando o
tamanho real da imagem já alinhada — por isso a mesma coordenada vale para
qualquer resolução de foto ou scanner. O gerador é o tools/pre_exame.py
(folha e leitor gêmeos por construção); coordenadas não calibradas (tudo
zero) são rejeitadas com mensagem clara, em vez de produzir nota vazia.

Observações: avaliacoes[q]["observacao"] vem de data/observacoes//.csv via
core/observacoes.py. Se o módulo não existir, o campo sai vazio
(comportamento anterior).

Correção Fase 07: import do pyzbar movido para DENTRO de decodificar_qr()
(lazy import). O pyzbar depende da biblioteca nativa libzbar0, ausente no
runner ubuntu-latest do GitHub Actions. Com o import local, as funções puras
(validação, densidade, contiguidade) não dependem da lib nativa e o módulo
importa sem quebrar em qualquer ambiente.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# NOTA: NÃO importar pyzbar aqui no topo.
# O import acontece dentro de decodificar_qr() — ver abaixo.

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

# Dimensões A4 em mm — base da conversão mm -> px das coordenadas.
LARGURA_A4_MM = 210.0
ALTURA_A4_MM = 297.0

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def decodificar_qr(imagem: np.ndarray) -> str | None:
    """Decodifica o primeiro QR encontrado; devolve o texto ou None."""
    from pyzbar.pyzbar import decode  # import local — correção Fase 07

    for obj in decode(imagem):
        return obj.data.decode("utf-8", errors="replace")
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

def detectar_e_corrigir(imagem: np.ndarray) -> np.ndarray:
    """Detecta a folha (maior contorno) e aplica correção de perspectiva."""
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(cinza, (5, 5), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(otsu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        raise ValueError("nenhum contorno de folha encontrado")
    folha = max(contornos, key=cv2.contourArea)
    peri = cv2.arcLength(folha, True)
    approx = cv2.approxPolyDP(folha, 0.02 * peri, True)
    if len(approx) != 4:
        raise ValueError(f"folha não detectada como quadrilátero "
                         f"({len(approx)} pontos)")
    pts = np.array([p[0] for p in approx], dtype="float32")
    # Ordena: topo-esq, topo-dir, baixo-dir, baixo-esq
    soma = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).ravel()
    topo_esq = pts[np.argmin(soma)]
    baixo_dir = pts[np.argmax(soma)]
    topo_dir = pts[np.argmin(diff)]
    baixo_esq = pts[np.argmax(diff)]
    ordem = np.array([topo_esq, topo_dir, baixo_dir, baixo_esq], dtype="float32")
    largura = max(int(np.linalg.norm(ordem[1] - ordem[0])),
                  int(np.linalg.norm(ordem[2] - ordem[3])))
    altura = max(int(np.linalg.norm(ordem[3] - ordem[0])),
                 int(np.linalg.norm(ordem[2] - ordem[1])))
    destino = np.array([[0, 0], [largura - 1, 0],
                        [largura - 1, altura - 1], [0, altura - 1]],
                       dtype="float32")
    matriz = cv2.getPerspectiveTransform(ordem, destino)
    return cv2.warpPerspective(imagem, matriz, (largura, altura))

def classificar_checkbox(roi: np.ndarray, limiares: dict) -> str:
    """Classifica uma ROI: 'vazio' | 'suspeito' | 'marcado'."""
    cinza = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binaria = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
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
    """Converte uma ROI em mm (origem no topo-esquerda) para pixels da
    imagem alinhada — usa o tamanho REAL da imagem, então vale para qualquer
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
    produzir nota silenciosamente errada.
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

def processar_imagem(caminho_imagem: Path, base_cfg: Path, faixa: str) -> dict:
    """Fluxo completo com layout da faixa -> JSON v2.0.

    Coordenadas em mm (config/coordenadas/.json) são convertidas para pixels
    pelo tamanho real da imagem alinhada.
    """
    limiares = carregar_json(base_cfg / "omr_thresholds.json")
    coordenadas = carregar_json(base_cfg / "coordenadas" / f"{faixa}.json")
    _validar_coordenadas(coordenadas, faixa)

    imagem = cv2.imread(str(caminho_imagem))
    if imagem is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho_imagem}")

    alinhada = detectar_e_corrigir(imagem)
    altura_px, largura_px = alinhada.shape[:2]

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
            contagem = contar_marcacoes_linha(classes, limiares)
            frequencias[quesito][chave] = contagem

    erros = validar_folha(frequencias)
    if erros:
        raise ValueError("; ".join(erros))

    resultado = {
        "metadados": metadados,
        "aluno": {"id": metadados["aluno_id"], "faixa_atual": metadados["faixa"]},
        "avaliacoes": {
            q: {"frequencias": {k: v["frequencia"] for k, v in criterios.items()},
                "observacao": ""}
            for q, criterios in frequencias.items()
        },
    }

    # Observações digitais (item 3): preenche avaliacoes[q]["observacao"].
    try:
        from core import observacoes
        resultado = observacoes.merge_no_json(resultado)
    except ImportError:
        pass

    return resultado