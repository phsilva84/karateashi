# tests/conftest.py
from pathlib import Path

import pytest

@pytest.fixture
def base_cfg() -> Path:
    return Path(__file__).resolve().parents[1] / "config"