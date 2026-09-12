"""Fixtures compartilhadas dos testes do Karate-Ashi."""

from pathlib import Path

import pytest

@pytest.fixture
def base_cfg() -> Path:
    """Caminho até a pasta config/ do repositório (Fases 00 e 06)."""
    return Path(__file__).resolve().parents[1] / "config"