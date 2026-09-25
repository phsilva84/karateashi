"""tests/test_omr_robustez.py — Robustez do core.omr_reader (contrato v3.17).

Cobre as primitivas do reader ENXUTO e o pipeline completo em 2 etapas:
- folha em BRANCO -> zero falsos positivos (presenca AUSENTE, freq vazias);
- folha PREENCHIDA -> presenca PRESENTE, frequencia por CONTAGEM no
  criterio certo, observacao marcada (item a item).

Semantica (dominio): o avaliador marca TODOS os baloes observados (1..5);
cada balao preenchido = 1 ocorrencia. Frequencia = QUANTIDADE de baloes
marcados. 5/5 e legitimo.

Determinístico: imagens sintéticas + monkeypatch do QR (sem depender de
pyzbar/libzbar0 no runner — os testes de QR usam importorskip).
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from core import omr_reader

A4_W, A4_H = omr_reader.A4_W_PX, omr_reader.A4_H_PX      # 3508 x 2480
ESCALA = omr_reader.A4_W_PX / omr_reader.A4_W_MM          # ~11.81 px/mm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _balao(x_mm, y_mm, r_mm=1.8):
    return {"x_mm": x_mm, "y_mm": y_mm, "r_mm": r_mm}


def _coords_para_teste() -> dict:
    """3 alunos, página 1: presença + kihon_base_incorreta (5 balões) + 12 obs."""
    alunos = []
    for i, aluno_id in enumerate(("T01", "T02", "T03")):
        y_pres = 66.67 + i * 50.67
        criterio = [_balao(44.0 + b * 5.0, y_pres - 38.5) for b in range(5)]
        obs = {}
        for oi in range(6):
            obs[f"obs_p{oi + 1}"] = _balao(13.5, 181.9 + oi * 3.8, 1.5)
            obs[f"obs_m{oi + 1}"] = _balao(59.0, 181.9 + oi * 3.8, 1.5)
        alunos.append({
            "id": aluno_id, "faixa": "branca", "pagina": 1,
            "presenca": _balao(12.0, y_pres, 1.8),
            "frequencias": {"kihon_base_incorreta": criterio},
            "observacoes": obs,
        })
    return {"versao": "teste", "exame": "EXA-T-2026",
            "avaliador_id": "S01", "dojo_id": "D01", "alunos": alunos}


def _escrever_coords(tmp_path: Path) -> None:
    (tmp_path / "output" / "pre_exame").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "pre_exame" /
     "EXA-T-2026_S01_folha1_coordenadas.json").write_text(
        json.dumps(_coords_para_teste()), encoding="utf-8")


def _config_tmp(tmp_path: Path) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    _escrever_coords(tmp_path)
    return cfg


def _folha_a4() -> np.ndarray:
    return np.full((A4_H, A4_W, 3), 255, dtype=np.uint8)


def _desenhar_circulo_preenchido(img, balao):
    """Pinta um círculo do MESMO raio do balão (anel impresso preenchido)."""
    cx = int(balao["x_mm"] * ESCALA)
    cy = int(balao["y_mm"] * ESCALA)
    r = int(balao["r_mm"] * ESCALA)
    cv2.circle(img, (cx, cy), max(r, 2), (0, 0, 0), -1)


def _marcar_t01(img, coords):
    a1 = coords["alunos"][0]
    _desenhar_circulo_preenchido(img, a1["presenca"])
    # CONTAGEM: marca 2 baloes no criterio -> frequencia 2 (nao posicao)
    _desenhar_circulo_preenchido(
        img, a1["frequencias"]["kihon_base_incorreta"][1])
    _desenhar_circulo_preenchido(
        img, a1["frequencias"]["kihon_base_incorreta"][2])
    _desenhar_circulo_preenchido(img, a1["observacoes"]["obs_p1"])


def _rodar(tmp_path, monkeypatch, img) -> list[dict]:
    cfg = _config_tmp(tmp_path)
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), img)
    monkeypatch.setattr(
        omr_reader, "_payload_por_prefixo",
        lambda im, p: "KA|AVALIADOR=S01|DOJO=D01|EXAME=EXA-T-2026")
    monkeypatch.setattr(
        omr_reader, "_ler_alunos_do_qr",
        lambda a4: [("T01", "branca"), ("T02", "branca"), ("T03", "branca")])
    return omr_reader.processar_imagem(caminho, cfg, "branca")


# ---------------------------------------------------------------------------
# Primitivas de imagem
# ---------------------------------------------------------------------------
def test_achar_anel_encontra_circulo():
    img = _folha_a4()
    balao = _balao(50.0, 50.0)
    _desenhar_circulo_preenchido(img, balao)
    cinza = omr_reader._cinza(img)
    anel = omr_reader._achar_anel(
        cinza, balao["x_mm"] * ESCALA, balao["y_mm"] * ESCALA,
        balao["r_mm"] * ESCALA, omr_reader.JANELA_MM * ESCALA)
    assert anel is not None
    assert max(abs(anel[0] - balao["x_mm"] * ESCALA),
               abs(anel[1] - balao["y_mm"] * ESCALA)) <= 2


def test_achar_anel_tolerante_a_offset():
    img = _folha_a4()
    balao = _balao(50.0, 50.0)
    cx = (balao["x_mm"] + 2.0) * ESCALA
    cy = balao["y_mm"] * ESCALA
    cv2.circle(img, (int(cx), int(cy)), int(1.4 * ESCALA), (0, 0, 0), -1)  # 1.4mm (dentro 0.6r..1.4r)
    cinza = omr_reader._cinza(img)
    anel = omr_reader._achar_anel(
        cinza, balao["x_mm"] * ESCALA, balao["y_mm"] * ESCALA,
        balao["r_mm"] * ESCALA, omr_reader.JANELA_MM * ESCALA)
    assert anel is not None


def test_achar_anel_sem_circulo():
    img = _folha_a4()
    cinza = omr_reader._cinza(img)
    anel = omr_reader._achar_anel(
        cinza, 50.0 * ESCALA, 50.0 * ESCALA, 1.8 * ESCALA,
        omr_reader.JANELA_MM * ESCALA)
    assert anel is None


def test_medir_preenchido_e_vazio():
    img = _folha_a4()
    balao = _balao(50.0, 50.0)
    _desenhar_circulo_preenchido(img, balao)
    cinza = omr_reader._cinza(img)
    taxa, blob = omr_reader._medir(cinza, balao["x_mm"] * ESCALA,
                                   balao["y_mm"] * ESCALA,
                                   balao["r_mm"] * ESCALA)
    assert taxa >= 0.30 and blob >= 0.25
    taxa2, blob2 = omr_reader._medir(
        cinza, 150.0 * ESCALA, 150.0 * ESCALA, 1.8 * ESCALA)
    assert taxa2 < 0.15 and blob2 < 0.08


def test_normalizar_a4_ja_ok():
    img = _folha_a4()
    out = omr_reader.normalizar_a4(img)
    assert out.shape[0] == A4_H and out.shape[1] == A4_W


# ---------------------------------------------------------------------------
# QR (monkeypatch pyzbar)
# ---------------------------------------------------------------------------
def test_ler_qrs_e_prefixo(monkeypatch):
    pytest.importorskip("pyzbar")
    class Simbolo:
        type = "QRCODE"
        data = b"KA|AVALIADOR=S01|DOJO=D01|EXAME=EXA-T-2026"
        rect = (10, 10, 20, 20)
    monkeypatch.setattr("pyzbar.pyzbar.decode", lambda imagem: [Simbolo()])
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    qrs = omr_reader._ler_qrs(img)
    assert qrs and qrs[0][0] == "KA|AVALIADOR=S01|DOJO=D01|EXAME=EXA-T-2026"
    assert omr_reader._payload_por_prefixo(img, "AVALIADOR") == \
        "KA|AVALIADOR=S01|DOJO=D01|EXAME=EXA-T-2026"
    assert omr_reader._payload_por_prefixo(img, "ALUNO") is None


# ---------------------------------------------------------------------------
# Pipeline: folha em branco -> zero falsos positivos
# ---------------------------------------------------------------------------
def test_pipeline_folha_em_branco(tmp_path, monkeypatch):
    img = _folha_a4()
    res = _rodar(tmp_path, monkeypatch, img)
    assert isinstance(res, list) and len(res) == 3
    for r in res:
        assert r["presenca"] == "AUSENTE"
        for q in ("kihon", "kata", "bunkai", "kumite"):
            assert r["avaliacoes"][q]["frequencias"] == {}
        assert r["observacoes_marcadas"] == []


# ---------------------------------------------------------------------------
# Pipeline: folha preenchida -> item a item (contagem)
# ---------------------------------------------------------------------------
def test_pipeline_folha_preenchida(tmp_path, monkeypatch):
    coords = _coords_para_teste()
    img = _folha_a4()
    _marcar_t01(img, coords)
    res = _rodar(tmp_path, monkeypatch, img)

    t01 = next(r for r in res if r["aluno"]["id"] == "T01")
    assert t01["presenca"] == "PRESENTE"
    # 2 baloes marcados no criterio -> frequencia 2 (contagem livre)
    assert t01["avaliacoes"]["kihon"]["frequencias"]["base_incorreta"] == 2
    assert "obs_p1" in t01["observacoes_marcadas"]
    assert t01["observacao_montada"] != ""

    for r in res:
        if r["aluno"]["id"] != "T01":
            assert r["presenca"] == "AUSENTE"