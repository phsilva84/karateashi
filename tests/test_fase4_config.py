# tests/test_fase4_config.py
import json
from pathlib import Path

from core import engine, omr_reader, relatorios
from core.config import (
    QUESITOS,
    FAIXAS_SUPORTADAS,
    carregar_json,
    faixas_suportadas,
)

RAIZ = Path(__file__).parent.parent
BASE_CFG = RAIZ / "config"

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

def test_faixas_derivam_do_indice():
    """A lista canônica deriva de config/faixas.json (não é hardcoded)."""
    indice = json.loads((BASE_CFG / "faixas.json").read_text(encoding="utf-8"))
    esperado = [str(f).strip().lower() for f in indice["suportadas"]]
    assert faixas_suportadas(BASE_CFG) == esperado
    assert FAIXAS_SUPORTADAS == esperado
    
def test_cadastro_usa_fonte_unica():
    """cadastro usa o carregar_json central (nada duplicado)."""
    from core import cadastro
    from core.config import carregar_json

    assert cadastro.carregar_json is carregar_json