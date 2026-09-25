"""tests/test_omr_validador.py — Validadores do core.omr_reader (contrato v3.14).

Alinha a suíte ao reader ENXUTO (busca local por balão):
- classificar_checkbox agora recebe (taxa, blob) numéricos (não imagem+dict);
- _frequencia substitui contar_marcacoes_linha;
- _anular_contradicoes substitui o antigo PARES_CONTRADICAO do módulo;
- _carregar_coordenadas substitui _validar_coordenadas (glob em output/pre_exame);
- processar_imagem devolve LISTA (um dict por aluno) — não dict único.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import cv2
import numpy as np

from core import omr_reader


# --- classificar_checkbox (limiares numéricos) ------------------------------
def test_classificar_checkbox_marcado():
    assert omr_reader.classificar_checkbox(0.50, 0.60) == "marcado"


def test_classificar_checkbox_vazio():
    assert omr_reader.classificar_checkbox(0.05, 0.02) == "vazio"


def test_classificar_checkbox_suspeito():
    assert omr_reader.classificar_checkbox(0.20, 0.10) == "suspeito"


# --- _frequencia (5 balões 1..5) ---------------------------------------------
def test_frequencia_um_marcado():
    # 1 balao marcado -> frequencia 1 (contagem, nao posicao)
    densidades = [(0.05, 0.02), (0.90, 0.80), (0.05, 0.02),
                  (0.05, 0.02), (0.05, 0.02)]
    freq, avisos = omr_reader._frequencia(densidades)
    assert freq == 1 and avisos == []


def test_frequencia_tres_marcados():
    # avaliador marcou 3 ocorrencias -> frequencia 3
    densidades = [(0.90, 0.80), (0.05, 0.02), (0.88, 0.75),
                  (0.05, 0.02), (0.92, 0.78)]
    freq, avisos = omr_reader._frequencia(densidades)
    assert freq == 3 and avisos == []


def test_frequencia_cinco_marcados():
    # 5/5 e legitimo -> frequencia 5
    densidades = [(0.95, 0.80)] * 5
    freq, avisos = omr_reader._frequencia(densidades)
    assert freq == 5 and avisos == []


def test_frequencia_nenhum_marcado():
    densidades = [(0.05, 0.02)] * 5
    freq, avisos = omr_reader._frequencia(densidades)
    assert freq == 0 and avisos == []


# --- _anular_contradicoes ----------------------------------------------------
def test_anular_contradicoes():
    marcadas = {"obs_p1", "obs_m1", "obs_p2"}
    incidentes: list[str] = []
    omr_reader._anular_contradicoes(marcadas, incidentes)
    assert marcadas == {"obs_p2"}
    assert any("contradicao:obs_p1/obs_m1" in i for i in incidentes)


# --- _carregar_coordenadas ---------------------------------------------------
def test_carregar_coordenadas_encontra(tmp_path):
    pasta = tmp_path / "pre_exame"
    pasta.mkdir(parents=True)
    (pasta / "EXA-T-2026_S01_folha1_coordenadas.json").write_text(
        json.dumps({"exame": "EXA-T-2026"}), encoding="utf-8")
    dados = omr_reader._carregar_coordenadas(pasta, "EXA-T-2026", "S01")
    assert dados == {"exame": "EXA-T-2026"}


def test_carregar_coordenadas_ausente(tmp_path):
    pasta = tmp_path / "pre_exame"
    pasta.mkdir(parents=True)
    assert omr_reader._carregar_coordenadas(pasta, "EXA-X", "S09") is None


# --- processar_imagem: caminhos de erro (com monkeypatch) --------------------
def _config_tmp(tmp_path, com_coords=True):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    if com_coords:
        (tmp_path / "output" / "pre_exame").mkdir(parents=True, exist_ok=True)
    return cfg


def test_processar_imagem_sem_qr(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = tmp_path / "folha.png"
    cv2.imwrite(str(folha), np.full((10, 10, 3), 255, dtype=np.uint8))
    monkeypatch.setattr(omr_reader, "_payload_por_prefixo",
                        lambda im, p: None)
    with pytest.raises(ValueError, match="QR do exame"):
        omr_reader.processar_imagem(folha, cfg, "branca")


def test_processar_imagem_sem_coordenadas(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path, com_coords=False)
    folha = tmp_path / "folha.png"
    cv2.imwrite(str(folha), np.full((10, 10, 3), 255, dtype=np.uint8))
    monkeypatch.setattr(omr_reader, "_payload_por_prefixo",
                        lambda im, p: "KA|AVALIADOR=S01|DOJO=D01|EXAME=EXA-T")
    with pytest.raises(ValueError, match="JSON de coordenadas"):
        omr_reader.processar_imagem(folha, cfg, "branca")