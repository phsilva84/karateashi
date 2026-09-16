# tests/test_engine_fronteira.py — RL-03: precedência de arredondamento
from decimal import Decimal, ROUND_HALF_UP

from core.engine import classificar_status

REGRAS = {"status": {"aprovado_min": 70.0, "recuperacao_min": 60.0}}

def _arredondar_nota(soma: float) -> float:
    """Mesma rotina do engine: 2 casas -> 1 casa com aritmética decimal."""
    return float(Decimal(str(round(soma, 2))).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP))

def test_arredondamento_half_up_decimal():
    """A aritmética decimal é determinística: 69.95 -> 70.0 e 69.94 -> 69.9."""
    assert Decimal("69.95").quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP) == Decimal("70.0")
    assert Decimal("69.94").quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP) == Decimal("69.9")

def test_fronteira_69_95_e_69_96_aprovam():
    """Nota exibida 70.0 na fronteira -> APROVADO."""
    assert _arredondar_nota(69.96) == 70.0
    assert _arredondar_nota(69.95) == 70.0
    assert classificar_status(_arredondar_nota(69.96), REGRAS) == "APROVADO"
    assert classificar_status(_arredondar_nota(69.95), REGRAS) == "APROVADO"

def test_fronteira_69_94_recuperacao():
    """Abaixo da meia-fronteira: 69.9 -> RECUPERACAO."""
    assert _arredondar_nota(69.94) == 69.9
    assert classificar_status(69.9, REGRAS) == "RECUPERACAO"