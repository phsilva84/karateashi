# tests/test_ingest_folhas.py — alinhado à assinatura canônica v3.14
import inspect
from pathlib import Path

from core import omr_reader

RAIZ = Path(__file__).parent.parent


def test_processar_imagem_aceita_origem():
    """v3.14: 'origem' (scanner|foto) controla a normalização."""
    params = inspect.signature(omr_reader.processar_imagem).parameters
    assert "origem" in params
    assert set(params) == {"caminho_imagem", "base_cfg", "faixa", "origem"}


def test_ingest_folhas_grava_origem_no_json():
    """O ingest grava 'origem' no JSON (o pipeline lê em 'origens')."""
    fonte = (RAIZ / "tools" / "ingest_folhas.py").read_text(encoding="utf-8")
    assert "origem" in fonte