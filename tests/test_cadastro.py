# tests/test_cadastro.py
import json
from pathlib import Path

RAIZ = Path(__file__).parent.parent

def _faixas_suportadas() -> set[str]:
    """Deriva as faixas suportadas do disco real (config/faixas/*.json).

    Mesma lógica do core/engine.carregar_faixa: uma faixa é suportada se
    existe o arquivo config/faixas/<faixa>.json SEM 'nao_suportada': true
    e COM 'quesitos' preenchido (o placeholder Roxa tem quesitos vazio).
    """
    dir_faixas = RAIZ / "config" / "faixas"
    suportadas = set()
    if dir_faixas.is_dir():
        for arquivo in dir_faixas.glob("*.json"):
            try:
                spec = json.loads(arquivo.read_text(encoding="utf-8"))
            except Exception:
                continue  # arquivo auxiliar sem JSON válido — ignora
            if not spec.get("nao_suportada", False) and spec.get("quesitos"):
                suportadas.add(arquivo.stem.strip().lower())
    return suportadas

def test_alunos_ativos_so_com_faixas_suportadas():
    """Quebra #6: nenhum aluno ativo pode mirar faixa não suportada na v2.0."""
    alunos = json.loads(
        (RAIZ / "data" / "cadastro" / "alunos.json").read_text(encoding="utf-8")
    )["alunos"]
    suportadas = _faixas_suportadas()
    assert suportadas, "nenhuma faixa suportada encontrada em config/faixas/"

    for aluno in alunos:
        if aluno.get("ativo", False):
            pretendida = aluno["faixa_pretendida"].strip().lower()
            assert pretendida in suportadas, (
                f"aluno {aluno['id']} ({aluno['nome']}) ativo com "
                f"faixa_pretendida não suportada: {aluno['faixa_pretendida']}"
            )

def test_registro_a08_inativo():
    """O registro de teste com meta Roxa deve estar inativo."""
    alunos = json.loads(
        (RAIZ / "data" / "cadastro" / "alunos.json").read_text(encoding="utf-8")
    )["alunos"]
    a08 = next(a for a in alunos if a["id"] == "A08")
    assert a08["ativo"] is False, "A08 (Teste Azul / meta Roxa) precisa estar inativo"