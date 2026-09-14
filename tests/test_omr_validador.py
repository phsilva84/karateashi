# ===========================================================================
# BLOCO ADICIONAL — Cobertura do core.omr_reader (Fase 07)
# Adicionar ao final de tests/test_omr_validador.py
# ===========================================================================

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

def _obs_rois():
    """16 ROIs de observação válidas (contrato v2col-2.8: obs_p1..p8, obs_m1..m8).

    y a partir de 230mm: fora da área de critérios (topo da folha) e dentro
    da imagem sintética de teste (1050x1485px = 5px/mm).
    """
    return {f"obs_{p}{i}": {"x": 15.0, "y": 230.0 + i, "w": 4.5, "h": 4.5}
            for p in ("p", "m") for i in range(1, 9)}

def _coords_ok():
    """Coordenadas completas: 4 quesitos + seção 'observacoes' (contrato novo)."""
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 5.0, "h": 5.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = _obs_rois()
    return coords

# --- parse_payload_qr ------------------------------------------------------

def test_parse_payload_qr_valido():
    meta = parse_payload_qr("KA|DOJO1|EXAME2|ALUNO3|SENSEI4|BRANCA")
    assert meta["versao_schema"] == "2.0"
    assert meta["dojo_id"] == "DOJO1"
    assert meta["exame_id"] == "EXAME2"
    assert meta["aluno_id"] == "ALUNO3"
    assert meta["avaliador_id"] == "SENSEI4"
    assert meta["faixa"] == "BRANCA"

def test_parse_payload_qr_invalido():
    with pytest.raises(ValueError):
        parse_payload_qr("XX|DOJO|EXAME|ALUNO|SENSEI|BRANCA")
    with pytest.raises(ValueError):
        parse_payload_qr("KA|DOJO|EXAME|ALUNO|SENSEI")

# --- carregar_json ---------------------------------------------------------

def test_carregar_json(tmp_path):
    arquivo = tmp_path / "cfg.json"
    arquivo.write_text('{"chave": 1}', encoding="utf-8")
    assert carregar_json(arquivo) == {"chave": 1}

# --- roi_mm_para_px --------------------------------------------------------

def test_roi_mm_para_px():
    roi = roi_mm_para_px({"x": 10.0, "y": 20.0, "w": 30.0, "h": 40.0},
                         2100, 2970)  # 10 px/mm
    assert roi == {"x": 100, "y": 200, "w": 300, "h": 400}

# --- classificar_checkbox --------------------------------------------------

def _roi(cor: int) -> np.ndarray:
    return np.full((20, 20, 3), cor, dtype=np.uint8)

def test_classificar_checkbox_vazio():
    assert classificar_checkbox(_roi(255), LIMIARES) == "vazio"

def test_classificar_checkbox_marcado():
    assert classificar_checkbox(_roi(0), LIMIARES) == "marcado"

def test_classificar_checkbox_suspeito():
    roi = _roi(255)
    roi[:6, :6] = 0  # 36/400 = 9% de pixels escuros
    assert classificar_checkbox(roi, LIMIARES) == "suspeito"

# --- contar_marcacoes_linha ------------------------------------------------

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

# --- validar_folha ---------------------------------------------------------

def test_validar_folha_ok():
    freq = {"kihon": {"c1": {"frequencia": 2}}}
    assert validar_folha(freq) == []

def test_validar_folha_limite_7():
    freq = {"kihon": {"c1": {"frequencia": 8}}}
    assert any("mais de 7" in e for e in validar_folha(freq))

def test_validar_folha_branca():
    freq = {"kihon": {"c1": {"frequencia": 0}}}
    assert any("folha sem nenhuma marcação" in e for e in validar_folha(freq))

# --- _validar_coordenadas --------------------------------------------------

def test_validar_coordenadas_ok():
    _validar_coordenadas(_coords_ok(), "branca")  # não deve levantar

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
    """Contrato novo: sem a seção 'observacoes', o leitor recusa o arquivo."""
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

# --- decodificar_qr (com pyzbar mockado) -----------------------------------

def test_decodificar_qr(monkeypatch):
    class Simbolo:
        data = b"KA|D|E|A|S|BRANCA"
    monkeypatch.setattr("pyzbar.pyzbar.decode", lambda imagem: [Simbolo()])
    assert decodificar_qr(np.zeros((10, 10, 3), dtype=np.uint8)) == "KA|D|E|A|S|BRANCA"

def test_decodificar_qr_sem_qr(monkeypatch):
    monkeypatch.setattr("pyzbar.pyzbar.decode", lambda imagem: [])
    assert decodificar_qr(np.zeros((10, 10, 3), dtype=np.uint8)) is None

# --- detectar_e_corrigir (imagens sintéticas) ------------------------------

def _folha_sintetica() -> np.ndarray:
    """Fundo claro + folha escura (600x440 px) — após o INV, a folha é o
    maior contorno, exatamente como o leitor espera."""
    img = np.full((600, 800, 3), 230, dtype=np.uint8)
    cv2.rectangle(img, (100, 80), (700, 520), (30, 30, 30), -1)
    return img

def test_detectar_e_corrigir_ok():
    alinhada = detectar_e_corrigir(_folha_sintetica())
    assert abs(alinhada.shape[1] - 600) <= 2   # largura da folha
    assert abs(alinhada.shape[0] - 440) <= 2   # altura da folha

def test_detectar_e_corrigir_sem_folha():
    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="nenhum contorno"):
        detectar_e_corrigir(img)

def test_detectar_e_corrigir_nao_quadrilatero():
    img = np.full((300, 300, 3), 230, dtype=np.uint8)
    cv2.circle(img, (150, 150), 80, (30, 30, 30), -1)
    with pytest.raises(ValueError, match="quadrilátero"):
        detectar_e_corrigir(img)

# --- processar_imagem (pipeline completo, sem imagem real) -----------------

def _config_tmp(tmp_path):
    cfg = tmp_path / "config"
    (cfg / "coordenadas").mkdir(parents=True)
    (cfg / "omr_thresholds.json").write_text(json.dumps(LIMIARES),
                                             encoding="utf-8")
    coords = {q: {"c1": {"x": 10.0, "y": 10.0, "w": 70.0, "h": 10.0}}
              for q in ["kihon", "kata", "bunkai", "kumite"]}
    coords["observacoes"] = _obs_rois()   # contrato novo: seção obrigatória
    (cfg / "coordenadas" / "branca.json").write_text(json.dumps(coords),
                                                     encoding="utf-8")
    return cfg

def _folha_com_marcas() -> np.ndarray:
    """Folha A4 sintética 1050x1485 px (5 px/mm): 3 primeiros checkboxes
    marcados na linha c1 (x=50..200, y=50..100). A área de observações
    (y>230mm) fica em branco."""
    img = np.full((1485, 1050, 3), 255, dtype=np.uint8)
    img[50:100, 50:200] = (0, 0, 0)  # células 1, 2 e 3 marcadas
    return img

def test_processar_imagem_ok(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    folha = _folha_com_marcas()
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: folha)
    monkeypatch.setattr(omr_reader, "decodificar_qr",
                        lambda im: "KA|DOJO1|EXAME2|ALUNO3|SENSEI4|BRANCA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)

    resultado = processar_imagem(caminho, cfg, "branca")

    assert resultado["metadados"]["aluno_id"] == "ALUNO3"
    assert resultado["aluno"]["id"] == "ALUNO3"
    for q in ["kihon", "kata", "bunkai", "kumite"]:
        assert resultado["avaliacoes"][q]["frequencias"]["c1"] == 3
    # Contrato novo: observações estruturadas (folha sem marcações -> vazias)
    assert resultado["observacoes_marcadas"] == []
    assert resultado["observacao_montada"] == ""

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
    monkeypatch.setattr(omr_reader, "decodificar_qr",
                        lambda im: "KA|D|E|A|S|VERMELHA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), folha)
    with pytest.raises(ValueError, match="difere"):
        processar_imagem(caminho, cfg, "branca")

def test_processar_imagem_roi_estreita(tmp_path, monkeypatch):
    cfg = _config_tmp(tmp_path)
    pequena = np.full((10, 10, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(omr_reader, "detectar_e_corrigir", lambda im: pequena)
    monkeypatch.setattr(omr_reader, "decodificar_qr",
                        lambda im: "KA|D|E|A|S|BRANCA")
    caminho = tmp_path / "folha.png"
    cv2.imwrite(str(caminho), pequena)
    with pytest.raises(ValueError, match="ROI estreita"):
        processar_imagem(caminho, cfg, "branca")