
0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE
   Especialista em Visão Computacional — OpenCV, correção de perspectiva, análise de densidade de pixels.
   Dev Python Sênior — integração limpa, dependências, tipagem.
   Engenheiro SRE/DevOps — tolerância a ruído, validações de borda, config externa.
   Regras de conduta: use SEMPRE os valores da Fase 00 (thresholds em config/omr_thresholds.json); nunca invente limiares no código; se algo não estiver especificado, PERGUNTE antes de assumir; ao final, preencha o checklist.1. ObjetivoImplementar o módulo core/omr_reader.py que lê gabaritos preenchidos (foto ou scanner) e gera o JSON intermediário v2.0: detecção da folha, correção de perspectiva, decodificação do QR Code (metadados de aluno/avaliador/dojo/exame/faixa), classificação dos checkboxes por densidade de pixels e validações (contiguidade, suspeito, folha em branco, limite de 7).2. Contexto mínimo do projeto3. Decisões aprovadas (não reabrir)
   Pipeline: ler imagem → detectar folha (maior quadrilátero) → correção de perspectiva → ler QR → extrair ROIs → classificar densidade → validar → JSON.
   Classificação por densidade de pixels escuros: 0–20% vazio · 20–40% suspeito · > 40% marcado (valores da Fase 00).
   Regras de validação: não-contígua → aviso mas processa; suspeito → alerta de revisão manual; folha sem nenhuma marcação → rejeita; máximo 7 marcações por critério.
   QR lido com pyzbar; texto limpo (sem acentos) nos metadados.
   Dependências adicionadas ao requirements.txt: opencv-python, numpy, pyzbar, pillow.
1. Tarefas
   Criar core/omr_reader.py conforme código de referência (seção 5).
   Criar config/coordenadas_template.json (estrutura vazia/documentada, valores a calibrar) — o código apenas carrega.
   Atualizar requirements.txt com as dependências.
   Criar tests/test_omr_validador.py para as funções puras (classificação e validações) — sem depender de imagem real.
   Executar testes e registrar no Status.
2. Código de referência


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


`config/coordenadas_template.json` (estrutura a calibrar com folhas reais):


{
  "versao_template": "branca_v1",
  "pagina": "A4",
  "observacoes": "Valores x,y,w,h são relativos à imagem ALINHADA (pós-perspectiva). Calibrar na Fase de calibração com folhas de teste.",
  "kihon": {
    "base_incorreta": {"x": 0, "y": 0, "w": 350, "h": 30},
    "execucao_tecnica_incorreta": {"x": 0, "y": 0, "w": 350, "h": 30}
  },
  "kata": {},
  "bunkai": {},
  "kumite": {}
}



6. Critérios de aceite
   Funções puras (classificar_checkbox, validar_folha, parse_payload_qr) testadas e passando (sem imagem real).
   Falha com mensagem clara quando: imagem não abre, QR ausente, folha não é quadrilátero, folha em branco.
   Código lê thresholds e coordenadas de config/, nunca hardcoded.
   requirements.txt atualizado.
   Nota: a validação end-to-end com fotos reais fica para a fase de calibração, após imprimir gabaritos de teste.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
