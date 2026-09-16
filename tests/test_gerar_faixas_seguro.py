# tests/test_gerar_faixas_seguro.py
"""Fase 3 (RL-06): o gerador de faixas não sobrescreve trabalho manual.

RODA EM DIRETÓRIO TEMPORÁRIO (tmp_path) — nunca sobre o config/ real.
Testar comportamento de sobrescrita exige um destino descartável; validar
o config real continua sendo papel dos testes de sanidade (ex.:
test_coordenadas_sanidade.py).
"""
import importlib.util
import json
from pathlib import Path

def _carregar_gerador():
    """Importa tools/gerar_faixas.py direto do arquivo (independe de __init__)."""
    caminho = Path(__file__).resolve().parent.parent / "tools" / "gerar_faixas.py"
    spec = importlib.util.spec_from_file_location("gerar_faixas", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _montar_base(tmp_path: Path) -> Path:
    """Estrutura mínima com branca.json (tabela + coordenadas)."""
    base = tmp_path / "config"
    (base / "faixas").mkdir(parents=True)
    (base / "coordenadas").mkdir()
    tabela = {
        "versao_schema": "2.0.0", "faixa": "branca", "nao_suportada": False,
        "quesitos": {"kihon": {"criterios": [{"chave": "base_incorreta"}]}},
    }
    (base / "faixas" / "branca.json").write_text(
        json.dumps(tabela), encoding="utf-8")
    coord = {
        "faixa": "branca", "versao_template": "branca_v1",
        "kihon": {"c1": {"x": 10, "y": 20, "w": 30, "h": 10}},
        "observacoes": {"obs_p1": {"x": 1, "y": 1, "w": 5, "h": 5}},
    }
    (base / "coordenadas" / "branca.json").write_text(
        json.dumps(coord), encoding="utf-8")
    return base

def test_primeira_geracao_cria_arquivos(tmp_path: Path):
    g = _carregar_gerador()
    base = _montar_base(tmp_path)
    g.gerar(base)
    for faixa in ("amarela", "laranja", "verde", "azul"):
        assert (base / "faixas" / f"{faixa}.json").exists()
        assert (base / "coordenadas" / f"{faixa}.json").exists()
    for faixa in ("roxa", "marrom", "preta"):
        assert (base / "faixas" / f"{faixa}.json").exists()

def test_recalibracao_manual_nao_e_sobrescrita(tmp_path: Path):
    g = _carregar_gerador()
    base = _montar_base(tmp_path)
    g.gerar(base)
    verde = base / "coordenadas" / "verde.json"
    dados = json.loads(verde.read_text(encoding="utf-8"))
    dados["kihon"]["c1"]["x"] = 99  # mestre recalibrou a ROI de propósito
    verde.write_text(json.dumps(dados), encoding="utf-8")
    g.gerar(base)
    relido = json.loads(verde.read_text(encoding="utf-8"))
    assert relido["kihon"]["c1"]["x"] == 99, "recalibração foi sobrescrita!"
    assert (base / "coordenadas" / "verde.json.bak").exists()

def test_force_sobrescreve_mas_mantem_backup(tmp_path: Path):
    g = _carregar_gerador()
    base = _montar_base(tmp_path)
    g.gerar(base)
    verde = base / "coordenadas" / "verde.json"
    dados = json.loads(verde.read_text(encoding="utf-8"))
    dados["kihon"]["c1"]["x"] = 99
    verde.write_text(json.dumps(dados), encoding="utf-8")
    g.gerar(base, forcar=True)
    relido = json.loads(verde.read_text(encoding="utf-8"))
    assert relido["kihon"]["c1"]["x"] != 99
    assert (base / "coordenadas" / "verde.json.bak").exists()

def test_geracao_repetida_e_idempotente(tmp_path: Path):
    g = _carregar_gerador()
    base = _montar_base(tmp_path)
    g.gerar(base)
    verde = (base / "coordenadas" / "verde.json").read_text(encoding="utf-8")
    g.gerar(base)
    assert (base / "coordenadas" / "verde.json").read_text(encoding="utf-8") == verde
    assert not (base / "coordenadas" / "verde.json.bak").exists()