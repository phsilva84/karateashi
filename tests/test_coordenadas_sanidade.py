# tests/test_coordenadas_sanidade.py
"""Fase 3 (item 1): valida o CONTEÚDO das coordenadas OMR.

O desvio de 4,63 mm identificado na auditoria nasce quando coordenadas em
mm são usadas como pixels (ou vice-versa), ou quando a matriz muda e as
coordenadas não acompanham. Este teste, contra o config REAL, garante que:
1. toda ROI das 5 faixas cabe na página A4 e tem tamanho positivo;
2. a seção 'observacoes' existe com ROIs válidas (v2col-2.8);
3. o nº de ROIs por quesito == nº de critérios da matriz da faixa
   (pega o desvio estrutural: matriz mudou, coordenadas não seguiram).

Regra do playbook: validar contra o config real — sem fixtures falsas.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.config import QUESITOS, FAIXAS_SUPORTADAS

RAIZ = Path(__file__).parent.parent
LARGURA_A4_MM = 210.0
ALTURA_A4_MM = 297.0

def _rois_validas(secao: str, rois: dict, faixa: str) -> None:
    """Cada ROI tem x,y,w,h numéricos positivos e está contida no A4."""
    for chave, roi in rois.items():
        for campo in ("x", "y", "w", "h"):
            assert campo in roi, f"{faixa}.{secao}.{chave} sem '{campo}'"
            assert isinstance(roi[campo], (int, float)), \
                f"{faixa}.{secao}.{chave}.{campo} não é numérico"
        assert roi["w"] > 0 and roi["h"] > 0, \
            f"{faixa}.{secao}.{chave} com w/h zerado"
        assert roi["x"] >= 0 and roi["y"] >= 0, \
            f"{faixa}.{secao}.{chave} com origem negativa"
        assert roi["x"] + roi["w"] <= LARGURA_A4_MM, \
            f"{faixa}.{secao}.{chave} estoura a largura A4 (x+w > 210 mm)"
        assert roi["y"] + roi["h"] <= ALTURA_A4_MM, \
            f"{faixa}.{secao}.{chave} estoura a altura A4 (y+h > 297 mm)"

def test_coordenadas_dentro_do_a4():
    """Toda ROI das 5 faixas cabe na página e tem tamanho positivo."""
    for faixa in FAIXAS_SUPORTADAS:
        caminho = RAIZ / "config" / "coordenadas" / f"{faixa}.json"
        coord = json.loads(caminho.read_text(encoding="utf-8"))
        for quesito in QUESITOS:
            rois = coord.get(quesito, {})
            assert rois, f"{faixa} sem coordenadas do quesito '{quesito}'"
            _rois_validas(quesito, rois, faixa)

def test_coordenadas_observacoes_validas():
    """A seção 'observacoes' existe com ROIs válidas (Fase 04 v2col-2.8)."""
    for faixa in FAIXAS_SUPORTADAS:
        caminho = RAIZ / "config" / "coordenadas" / f"{faixa}.json"
        coord = json.loads(caminho.read_text(encoding="utf-8"))
        obs = coord.get("observacoes", {})
        assert obs, f"{faixa} sem seção 'observacoes'"
        _rois_validas("observacoes", obs, faixa)

def test_coordenadas_consistentes_com_matriz():
    """Nº de ROIs por quesito == nº de critérios da matriz da faixa.

    Esta é a checagem que pega o desvio estrutural: se a matriz v2.0 ganha
    ou perde um critério e as coordenadas não acompanham, o número de linhas
    de checkboxes deixa de bater — e o OMR leria uma linha errada.
    """
    for faixa in FAIXAS_SUPORTADAS:
        matriz = json.loads(
            (RAIZ / "config" / "faixas" / f"{faixa}.json")
            .read_text(encoding="utf-8"))
        coord = json.loads(
            (RAIZ / "config" / "coordenadas" / f"{faixa}.json")
            .read_text(encoding="utf-8"))
        for quesito in QUESITOS:
            n_criterios = len(matriz["quesitos"][quesito]["criterios"])
            n_rois = len(coord.get(quesito, {}))
            assert n_rois == n_criterios, (
                f"{faixa}.{quesito}: {n_rois} ROIs vs "
                f"{n_criterios} critérios na matriz — "
                "coordenadas defasadas da matriz?")

if __name__ == "__main__":
    # Execução direta: mostra as inconsistências sem depender do pytest.
    for faixa in FAIXAS_SUPORTADAS:
        matriz = json.loads(
            (RAIZ / "config" / "faixas" / f"{faixa}.json")
            .read_text(encoding="utf-8"))
        coord = json.loads(
            (RAIZ / "config" / "coordenadas" / f"{faixa}.json")
            .read_text(encoding="utf-8"))
        for quesito in QUESITOS:
            n_c = len(matriz["quesitos"][quesito]["criterios"])
            n_r = len(coord.get(quesito, {}))
            if n_c != n_r:
                print(f"INCONSISTENCIA: {faixa}.{quesito} "
                      f"({n_r} ROIs vs {n_c} criterios)")
    print("auditoria de coordenadas concluida")