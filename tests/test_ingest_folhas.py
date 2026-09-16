# tests/test_ingest_folhas.py (novo) — garante o alinhamento de assinatura
import inspect
import re
from pathlib import Path

from core import omr_reader

RAIZ = Path(__file__).parent.parent

def test_processar_imagem_nao_aceita_origem():
    """Quebra #5: a assinatura canônica do leitor não pode ganhar 'origem'."""
    params = inspect.signature(omr_reader.processar_imagem).parameters
    assert "origem" not in params, "processar_imagem não deve aceitar kwarg 'origem'"
    assert set(params) == {"caminho_imagem", "base_cfg", "faixa"}, list(params)

def test_ingest_folhas_chama_sem_kwarg_espurio():
    """O script de ingestão não pode repassar 'origem' na chamada ao leitor."""
    fonte = (RAIZ / "tools" / "ingest_folhas.py").read_text(encoding="utf-8")
    chamadas = re.findall(r"processar_imagem\([^)]*\)", fonte)
    assert chamadas, "chamada a processar_imagem não encontrada"
    for chamada in chamadas:
        assert "origem=" not in chamada, f"kwarg espúrio presente: {chamada.strip()}"