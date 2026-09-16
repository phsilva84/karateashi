"""tests/test_omr_robustez.py — Cobertura da robustez v2col-2.9 do core.omr_reader.

Cobre o que entrou sem teste p/ foto de celular: variantes de QR,
decodificar/localizar QR, âncora QR+fiduciais (warp_pela_ancora), guardas
(_fracao_preta, _quad_folha_plausivel) e o pipeline completo de
processar_imagem (incluindo caminhos de erro).

Determinístico:
- QR sintético gerado com a lib qrcode (dependência do tools/pre_exame.py).
- pyzbar/libzbar0 é opcional: os testes que dependem usam pytest.importorskip.
  No runner do GitHub Actions (sem libzbar0) eles são pulados; a cobertura é
  mantida pelos testes de pipeline com monkeypatch.
"""
from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from core import omr_reader
from core.omr_reader import (
    _validar_coordenadas,
    carregar_json,
    classificar_checkbox,
    contar_marcacoes_linha,
    decodificar_qr,
    detectar_e_corrigir,
    parse_payload_qr,
    processar_imagem,
    roi_mm_para_px,
    validar_folha,
)

LIMIARES = {"limiar_vazio_max": 0.05, "limiar_suspeito_max": 0.30}

# ============================== Helpers =====================================

def _img_branca(largura=400, altura=600):
    return np.full((altura, largura, 3), 255, dtype=np.uint8)

def _img_preta(largura=400, altura=600):
    return np.zeros((altura, largura, 3), dtype=np.uint8)

def _qr_array(payload: str):
    qrcode = pytest.importorskip("qrcode")
    img = qrcode.make(payload)
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def _roi(cor: int) -> np.ndarray:
    return np.full((20, 20, 3), cor, dtype=np.uint8)

def _obs_rois():
    """16 ROIs de observação válidas (contrato v2col-2.8)."""
    return {
        f"obs_{p}{i}": {"x": 15.0, "y": 230.0 + i, "w": 4.5, "h": 4.5}
        for p in ("p", "m")
        for i in range(1, 9)
    }

def _coords_ok():
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 5.0, "h": 5.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = _obs_rois()
    return coords

def _folha_sintetica() -> np.ndarray:
    """Fundo claro + folha escura (600x440 px) — via INV vira o maior contorno."""
    img = np.full((600, 800, 3), 230, dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (700, 520), (30, 30, 30), -1)
    return img

def _folha_sintetica_com_qr(largura, altura):
    """Folha branca com QR no canto superior direito (posição do template)."""
    qrcode = pytest.importorskip("qrcode")
    img = _img_branca(largura, altura)
    escala = largura / omr_reader.LARGURA_A4_MM
    qr = qrcode.make("KA|D01|EXA-D01-2026-02|A01|S01|BRANCA")
    qr_arr = cv2.cvtColor(np.array(qr.convert("RGB")), cv2.COLOR_RGB2BGR)
    lado = int(round(22.0 * escala))
    qr_red = cv2.resize(qr_arr, (lado, lado), interpolation=cv2.INTER_NEAREST)
    x0 = largura - int(round((10.0 + 22.0) * escala))
    y0 = int(round(10.0 * escala))
    img[y0:y0 + lado, x0:x0 + lado] = qr_red
    pontos_qr = np.array([[x0, y0], [x0 + lado, y0],
                          [x0 + lado, y0 + lado], [x0, y0 + lado]],
                         dtype="float32")
    return img, pontos_qr

def _config_tmp(tmp_path):
    cfg = tmp_path / "config"
    (cfg / "coordenadas").mkdir(parents=True)
    (cfg / "omr_thresholds.json").write_text(
        json.dumps(LIMIARES), encoding="utf-8")
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 70.0, "h": 10.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = _obs_rois()
    (cfg / "coordenadas" / "branca.json").write_text(
        json.dumps(coords), encoding="utf-8")
    return cfg

def _folha_com_marcas() -> np.ndarray:
    """A4 sintético 1485x1050 px (5 px/mm): 3 primeiras células de c1 marcadas."""
    img = np.full((1485, 1050, 3), 255, dtype=np.uint8)
    img[50:100, 50:200] = (0, 0, 0)
    return img

# ====================== parse_payload_qr ====================================

def test_parse_payload_qr_valido():
    meta = parse_payload_qr("KA|DOJO1|EXAME2|ALUNO3|SENSEI4|BRANCA")
    assert meta["versao_schema"] == "2.0"
    assert meta["dojo_id"] == "DOJO1"
    assert meta["avaliador_id"] == "SENSEI4"
    assert meta["faixa"] == "BRANCA"

def test_parse_payload_qr_invalido():
    with pytest.raises(ValueError):
        parse_payload_qr("XX|DOJO|EXAME|ALUNO|SENSEI|BRANCA")
    with pytest.raises(ValueError):
        parse_payload_qr("KA|DOJO|EXAME|ALUNO|SENSEI")

# ====================== carregar_json =======================================

def test_carregar_json(tmp_path):
    arquivo = tmp_path / "cfg.json"
    arquivo.write_text('{"chave": 1}', encoding="utf-8")
    assert carregar_json(arquivo) == {"chave": 1}

# ====================== roi_mm_para_px ======================================

def test_roi_mm_para_px():
    roi = roi_mm_para_px({"x": 10.0, "y": 20.0, "w": 30.0, "h": 40.0}, 2100, 2970)
    assert roi == {"x": 100, "y": 200, "w": 300, "h": 400}

# ====================== classificar_checkbox ================================

def test_classificar_checkbox_vazio():
    assert classificar_checkbox(_roi(255), LIMIARES) == "vazio"

def test_classificar_checkbox_marcado():
    assert classificar_checkbox(_roi(0), LIMIARES) == "marcado"

def test_classificar_checkbox_suspeito():
    roi = _roi(255)
    roi[:6, :6] = 0
    assert classificar_checkbox(roi, LIMIARES) == "suspeito"

# ====================== contar_marcacoes_linha ==============================

def test_contar_marcacoes_contiguas():
    res = contar_marcacoes_linha(
        ["marcado", "marcado", "vazio", "vazio", "vazio", "vazio", "vazio"], {})
    assert res["frequencia"] == 2
    assert res["avisos"] == []

def test_contar_marcacoes_nao_contiguas():
    res = contar_marcacoes_linha(
        ["marcado", "vazio", "marcado", "vazio", "vazio", "vazio", "vazio"], {})
    assert res["frequencia"] == 2
    assert any("não-contígua" in a for a in res["avisos"])

def test_contar_marcacoes_suspeitas():
    res = contar_marcacoes_linha(
        ["suspeito", "vazio", "vazio", "vazio", "vazio", "vazio", "vazio"], {})
    assert res["frequencia"] == 0
    assert any("suspeitas" in a for a in res["avisos"])

# ====================== validar_folha =======================================

def test_validar_folha_ok():
    freq = {"kihon": {"c1": {"frequencia": 2}}}
    assert validar_folha(freq) == []

def test_validar_folha_limite_7():
    freq = {"kihon": {"c1": {"frequencia": 8}}}
    assert any("mais de 7" in e for e in validar_folha(freq))

def test_validar_folha_branca():
    freq = {"kihon": {"c1": {"frequencia": 0}}}
    assert any("folha sem nenhuma marcação" in e for e in validar_folha(freq))

# ====================== _validar_coordenadas ================================

def test_validar_coordenadas_ok():
    _validar_coordenadas(_coords_ok(), "branca")

def test_validar_coordenadas_zeradas():
    coords = {q: {"c1": {"x": 0.0, "y": 0.0, "w": 5.0, "h": 5.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = _obs_rois()
    with pytest.raises(ValueError, match="não calibradas"):
        _validar_coordenadas(coords, "branca")

def test_validar_coordenadas_sem_quesito():
    coords = {"kihon": {"c1": {"x": 1.0, "y": 1.0, "w": 5.0, "h": 5.0}}}
    coords["observacoes"] = _obs_rois()
    with pytest.raises(ValueError, match="sem o quesito"):
        _validar_coordenadas(coords, "branca")

def test_validar_coordenadas_sem_observacoes():
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 5.0, "h": 5.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    with pytest.raises(ValueError, match="sem a seção 'observacoes'"):
        _validar_coordenadas(coords, "branca")

def test_validar_coordenadas_obs_zeradas():
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 5.0, "h": 5.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = {"obs_p1": {"x": 0.0, "y": 0.0, "w": 4.5, "h": 4.5}}
    with pytest.raises(ValueError, match="não calibradas"):
        _validar_coordenadas(coords, "branca")

# ====================== decodificar_qr ======================================

def test_decodificar_qr_cv2_direto():
    qrcode = pytest.importorskip("qrcode")
    if not hasattr(cv2, "QRCodeDetector"):
        pytest.importorskip("pyzbar.pyzbar")
    payload = "KA|D01|EXA-D01-2026-02|A01|S01|BRANCA"
    assert decodificar_qr(_qr_array(payload)) == payload

def test_decodificar_qr(monkeypatch):
    pytest.importorskip("pyzbar.pyzbar")
    class Simbolo:
        data = b"KA|D|E|A|S|BRANCA"
    monkeypatch.setattr("pyzbar.pyzbar.decode", lambda imagem: [Simbolo()])
    assert decodificar_qr(np.zeros((10, 10, 3), dtype=np.uint8)) == "KA|D|E|A|S|BRANCA"

def test_decodificar_qr_sem_qr(monkeypatch):
    pytest.importorskip("pyzbar.pyzbar")
    monkeypatch.setattr("pyzbar.pyzbar.decode", lambda imagem: [])
    assert decodificar_qr(np.zeros((10, 10, 3), dtype=np.uint8)) is None

# ====================== variantes_qr ========================================

def test_variantes_qr_colorida_pequena():
    img = _img_branca(300, 300)
    v = omr_reader.variantes_qr(img)
    assert v[0] is img
    assert v[1].ndim == 2
    assert len(v) >= 6

def test_variantes_qr_imagem_grande():
    img = _img_branca(2000, 2000)
    v = omr_reader.variantes_qr(img)
    assert any(x.ndim == 2 and x.shape[0] < 2000 for x in v)

def test_variantes_qr_entrada_cinza():
    cinza = np.full((300, 300), 128, dtype=np.uint8)
    v = omr_reader.variantes_qr(cinza)
    assert v[1] is cinza

# ====================== localizar_qr ========================================

def test_localizar_qr_sem_qr():
    assert omr_reader.localizar_qr(_img_branca(200, 200)) is None

def test_localizar_qr_com_qr():
    pytest.importorskip("pyzbar.pyzbar")
    payload = "KA|D01|EXA-D01-2026-02|A01|S01|BRANCA"
    res = omr_reader.localizar_qr(_qr_array(payload))
    assert res is not None
    pontos, dados = res
    assert dados == payload
    assert pontos.shape == (4, 2)

# ====================== detectar_e_corrigir =================================

def test_detectar_e_corrigir_ok():
    alinhada = detectar_e_corrigir(_folha_sintetica())
    assert abs(alinhada.shape[1] - 600) <= 2
    assert abs(alinhada.shape[0] - 440) <= 2

def test_detectar_e_corrigir_sem_folha():
    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="nenhum contorno"):
        detectar_e_corrigir(img)

def test_detectar_e_corrigir_nao_quadrilatero():
    img = np.full((300, 300, 3), 230, dtype=np.uint8)
    cv2.circle(img, (150, 150), 80, (30, 30, 30), -1)
    with pytest.raises(ValueError, match="quadrilátero"):
        detectar_e_corrigir(img)

def test_detectar_e_corrigir_imagem_vazia():
    with pytest.raises(ValueError, match="imagem vazia"):
        detectar_e_corrigir(np.array([], dtype=np.uint8))

def test_detectar_e_corrigir_fallback_ancora(monkeypatch):
    img = _img_branca(400, 600)
    pontos = np.array([[300, 30], [380, 30], [380, 100], [300, 100]],
                      dtype="float32")
    monkeypatch.setattr(omr_reader, "localizar_qr",
                        lambda imagem: (pontos, "KA|D01|EXA|A01|S01|BRANCA"))
    monkeypatch.setattr(omr_reader, "warp_pela_ancora",
                        lambda imagem, pts: img)
    assert detectar_e_corrigir(img) is img

# ====================== guardas =============================================

def test_fracao_preta():
    assert omr_reader._fracao_preta(_img_preta(100, 100)) == 1.0
    assert omr_reader._fracao_preta(_img_branca(100, 100)) == 0.0

def test_quad_folha_plausivel():
    a4 = np.array([[0, 0], [210, 0], [210, 297], [0, 297]], dtype="float32")
    assert omr_reader._quad_folha_plausivel(a4)
    colapsado = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype="float32")
    assert not omr_reader._quad_folha_plausivel(colapsado)
    paisagem = np.array([[0, 0], [297, 0], [297, 210], [0, 210]], dtype="float32")
    assert not omr_reader._quad_folha_plausivel(paisagem)

# ====================== pontos de referência (mm) ===========================

def test_pontos_mm_qr():
    pts = omr_reader._pontos_mm_qr()
    assert pts.shape == (4, 2)
    assert pts[0][0] == 178.0 and pts[0][1] == 10.0
    assert pts[2][0] == 200.0 and pts[2][1] == 32.0

def test_pontos_mm_fiduciais():
    pts = omr_reader._pontos_mm_fiduciais()
    assert pts.shape == (3, 2)
    assert pts[0][0] == 8.0 and pts[0][1] == 8.0
    assert pts[1][0] == 202.0 and pts[1][1] == 289.0
    assert pts[2][0] == 8.0 and pts[2][1] == 289.0

# ====================== fiduciais (template) ================================

def test_template_fiducial():
    t = omr_reader._template_fiducial(1.0)
    assert t.ndim == 2 and t.dtype == np.uint8
    assert t.shape[0] == t.shape[1] and t.shape[0] % 2 == 1
    assert np.any(t == 0) and np.any(t == 255)   # cruz escura em fundo claro

def test_detectar_fiducial_regiao_pequena():
    img = _img_branca(100, 100)
    assert omr_reader._detectar_fiducial(img, np.array([0.0, 0.0]), 1.0) is None

def test_detectar_fiducial_sem_cruz():
    img = _img_branca(400, 400)
    assert omr_reader._detectar_fiducial(img, np.array([200.0, 200.0]), 1.0) is None

def test_detectar_fiducial_com_cruz():
    img = _img_branca(400, 400)
    t = omr_reader._template_fiducial(1.0)
    c = t.shape[0] // 2
    regiao = img[200 - c:200 + c + 1, 200 - c:200 + c + 1]
    regiao[t == 0] = 0   # pinta a cruz (escura) sobre o fundo branco
    centro = omr_reader._detectar_fiducial(img, np.array([200.0, 200.0]), 1.0)
    assert centro is not None
    assert abs(centro[0] - 200) <= 2 and abs(centro[1] - 200) <= 2

# ====================== warp_pela_ancora ====================================

def test_warp_pela_ancora_sem_fiduciais():
    img, pontos_qr = _folha_sintetica_com_qr(800, 1131)
    out = omr_reader.warp_pela_ancora(img, pontos_qr)
    assert out.shape[0] > 100 and out.shape[1] > 100
    razao = out.shape[1] / out.shape[0]
    assert 0.55 < razao < 0.85

def test_warp_pela_ancora_com_fiduciais():
    img, pontos_qr = _folha_sintetica_com_qr(1050, 1485)
    escala = 1050 / omr_reader.LARGURA_A4_MM
    H_qr, _ = cv2.findHomography(omr_reader._pontos_mm_qr(), pontos_qr)
    pred = cv2.perspectiveTransform(
        omr_reader._pontos_mm_fiduciais().reshape(-1, 1, 2),
        H_qr).reshape(-1, 2)
    t = omr_reader._template_fiducial(escala)
    c = t.shape[0] // 2
    for px, py in pred:
        xi, yi = int(round(px)) - c, int(round(py)) - c
        if (xi >= 0 and yi >= 0 and
                xi + t.shape[0] <= img.shape[1] and
                yi + t.shape[1] <= img.shape[0]):
            img[yi:yi + t.shape[0], xi:xi + t.shape[1]][t > 0] = 0
    out = omr_reader.warp_pela_ancora(img, pontos_qr)
    assert out.shape[0] > 100 and out.shape[1] > 100

def test_warp_pela_ancora_sem_plausibilidade(monkeypatch):
    img, pontos_qr = _folha_sintetica_com_qr(800, 1131)
    monkeypatch.setattr(omr_reader, "_quad_folha_plausivel",
                        lambda cantos: False)
    with pytest.raises(ValueError, match="âncoras"):
        omr_reader.warp_pela_ancora(img, pontos_qr)

def test_warp_pela_ancora_homografia_none(monkeypatch):
    monkeypatch.setattr(omr_reader.cv2, "findHomography",
                        lambda *a, **k: (None, None))
    with pytest.raises(ValueError, match="homografia do QR"):
        omr_reader.warp_pela_ancora(
            _img_branca(100, 100), np.zeros((4, 2), dtype="float32"))

# ====================== processar_imagem ====================================

def test_processar_imagem_ok(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = _folha_com_marcas()
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: folha)
    monkeypatch.setattr(
        omr_reader, "decodificar_qr",
        lambda im: "KA|DOJO1|EXAME2|ALUNO3|SENSEI4|BRANCA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)

    resultado = processar_imagem(caminho, cfg, "branca")
    assert resultado["aluno"]["id"] == "ALUNO3"
    for q in ["kihon", "kata", "bunkai", "kumite"]:
        assert resultado["avaliacoes"][q]["frequencias"]["c1"] == 3
    assert resultado["observacoes_marcadas"] == []
    assert resultado["observacao_montada"] == ""

def test_processar_imagem_com_observacoes(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = _folha_com_marcas()
    # marca obs_p1: x=15mm -> 75px, y=231mm -> 1155px, w/h=4.5mm -> ~23px
    folha[1153:1178, 73:999] = folha[1153:1178, 73:999]  # mantém (sem op)
    folha[1153:1178, 73:98] = (0, 0, 0)
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: folha)
    monkeypatch.setattr(
        omr_reader, "decodificar_qr",
        lambda im: "KA|DOJO1|EXAME2|ALUNO3|SENSEI4|BRANCA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)

    resultado = processar_imagem(caminho, cfg, "branca")
    assert "obs_p1" in resultado["observacoes_marcadas"]
    assert resultado["observacao_montada"] != ""

def test_processar_imagem_sem_qr(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = _folha_com_marcas()
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: folha)
    monkeypatch.setattr(omr_reader, "decodificar_qr", lambda im: None)
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)
    with pytest.raises(ValueError, match="QR Code não encontrado"):
        processar_imagem(caminho, cfg, "branca")

def test_processar_imagem_faixa_divergente(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = _folha_com_marcas()
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: folha)
    monkeypatch.setattr(
        omr_reader, "decodificar_qr",
        lambda im: "KA|D|E|A|S|VERMELHA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)
    with pytest.raises(ValueError, match="difere"):
        processar_imagem(caminho, cfg, "branca")

def test_processar_imagem_roi_estreita(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    pequena = np.full((10, 10, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: pequena)
    monkeypatch.setattr(
        omr_reader, "decodificar_qr",
        lambda im: "KA|D|E|A|S|BRANCA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), pequena)
    with pytest.raises(ValueError, match="ROI estreita"):
        processar_imagem(caminho, cfg, "branca")

def test_processar_imagem_folha_cortada(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    foto = tmp_path / "foto.jpg"
    cv2.imwrite(str(foto), _img_preta(200, 300))
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir",
                        lambda img: _img_preta(200, 300))
    with pytest.raises(ValueError, match="folha cortada"):
        processar_imagem(foto, cfg, "branca")