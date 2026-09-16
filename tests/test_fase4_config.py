# tests/test_fase4_config.py
from pathlib import Path

from core import engine, omr_reader, relatorios
from core.config import QUESITOS, FAIXAS_SUPORTADAS, carregar_json

RAIZ = Path(__file__).parent.parent

def test_carregar_json_centralizado():
    """Os módulos usam a MESMA função central (fonte única)."""
    assert engine.carregar_json is carregar_json
    assert relatorios.carregar_json is carregar_json
    assert omr_reader.carregar_json is carregar_json

def test_quesitos_fonte_unica():
    """Uma única lista de quesitos alimenta todos os módulos."""
    assert engine.QUESTOS_ORDEM == QUESITOS
    assert omr_reader.QUESITOS == QUESITOS

def test_faixas_suportadas_consistente():
    """engine e config concordam sobre as faixas suportadas."""
    assert engine.FAIXAS_SUPORTADAS == FAIXAS_SUPORTADAS