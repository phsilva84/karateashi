"""core/omr_reader.py — Leitura OMR dos gabaritos Karate-Ashi v2.0.
Pipeline:
1. carregar imagem (300 DPI recomendado);
2. detectar a folha (maior contorno quadrangular);
3. corrigir perspectiva (warpPerspective);
4. decodificar QR Code (pyzbar) e extrair metadados;
5. extrair as ROIs dos checkboxes (coordenadas_template.json);
6. classificar densidade de pixels (omr_thresholds.json);
7. validar (contiguidade, suspeitos, folha em branco, limite 7);
8. gerar JSON intermediário schema v2.0.
Calibração: os thresholds e as coordenadas NÃO ficam no código — vêm de
config/omr_thresholds.json e config/coordenadas_template.json.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from pyzbar.pyzbar import decode

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def decodificar_qr(imagem: np.ndarray) -> str | None:
    """Decodifica o primeiro QR encontrado; devolve o texto ou None."""
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
    contornos, _ = cv2.findContours(otsu, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
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
    ordem = np.array([topo_esq, topo_dir, baixo_dir, baixo_esq],
                     dtype="float32")
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

def processar_imagem(caminho_imagem: Path, base_cfg: Path,
                     coordenadas: dict) -> dict:
    """Fluxo completo: imagem -> JSON v2.0 (ou raise com erro claro)."""
    limiares = carregar_json(base_cfg / "omr_thresholds.json")
    imagem = cv2.imread(str(caminho_imagem))
    if imagem is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho_imagem}")
    alinhada = detectar_e_corrigir(imagem)
    payload = decodificar_qr(alinhada)
    if not payload:
        raise ValueError("QR Code não encontrado — folha inválida ou sem QR")
    metadados = parse_payload_qr(payload)
    frequencias: dict[str, dict[str, Any]] = {}
    for quesito in QUESITOS:
        frequencias[quesito] = {}
        for chave, roi_mapa in coordenadas[quesito].items():
            x, y, w, h = (int(v) for v in roi_mapa.values())
            roi = alinhada[y:y + h, x:x + w]
            classes = []
            passo = w // 7
            for i in range(7):
                celula = roi[:, i * passo:(i + 1) * passo]
                classes.append(classificar_checkbox(celula, limiares))
            contagem = contar_marcacoes_linha(classes, limiares)
            frequencias[quesito][chave] = contagem
    erros = validar_folha(frequencias)
    if erros:
        raise ValueError("; ".join(erros))
    return {
        "metadados": metadados,
        "aluno": {"id": metadados.pop("aluno_id"),
                  "faixa_atual": metadados.pop("faixa")},
        "avaliacoes": {
            q: {"frequencias": {k: v["frequencia"]
                                for k, v in criterios.items()},
                "observacao": ""}
            for q, criterios in frequencias.items()
        },
    }
    
    # core/omr_reader.py — (trecho) Fase 06: carregar coordenadas por faixa.

def processar_imagem(caminho_imagem: Path, base_cfg: Path, faixa: str) -> dict:
    """Fluxo completo com layout da faixa."""
    limiares = carregar_json(base_cfg / "omr_thresholds.json")
    coordenadas = carregar_json(base_cfg / "coordenadas" / f"{faixa}.json")

    imagem = cv2.imread(str(caminho_imagem))
    if imagem is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho_imagem}")

    alinhada = detectar_e_corrigir(imagem)
    payload = decodificar_qr(alinhada)
    if not payload:
        raise ValueError("QR Code não encontrado — folha inválida ou sem QR")

    metadados = parse_payload_qr(payload)

    # A faixa do QR deve bater com a faixa esperada (validação cruzada):
    if metadados.get("faixa", "").lower() != faixa.lower():
        raise ValueError(
            f"faixa do QR ({metadados.get('faixa')}) difere do "
            f"layout carregado ({faixa})"
        )

    # Segmentação usando coordenadas[quesito][chave] (restante idêntico à Fase 03)
    ...