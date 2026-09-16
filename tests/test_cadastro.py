# tests/test_cadastro.py (novo)
import json
from pathlib import Path

RAIZ = Path(__file__).parent.parent

def test_alunos_ativos_so_com_faixas_suportadas():
    """Quebra #6: nenhum aluno ativo pode mirar faixa não suportada na v2.0."""
    alunos = json.loads((RAIZ / "data" / "cadastro" / "alunos.json").read_text(encoding="utf-8"))["alunos"]
    faixas = json.loads((RAIZ / "config" / "faixas.json").read_text(encoding="utf-8"))

    # Faixas suportadas = as que têm matriz com quesitos (não nao_suportada)
    suportadas = {
        nome.lower().strip()
        for nome, spec in faixas.items()
        if not spec.get("nao_suportada", False)
    }

    for aluno in alunos:
        if aluno.get("ativo", False):
            pretendida = aluno["faixa_pretendida"].lower().strip()
            assert pretendida in suportadas, (
                f"aluno {aluno['id']} ({aluno['nome']}) ativo com "
                f"faixa_pretendida não suportada: {aluno['faixa_pretendida']}"
            )

def test_registro_a08_inativo():
    """O registro de teste com meta Roxa deve estar inativo."""
    alunos = json.loads((RAIZ / "data" / "cadastro" / "alunos.json").read_text(encoding="utf-8"))["alunos"]
    a08 = next(a for a in alunos if a["id"] == "A08")
    assert a08["ativo"] is False, "A08 (Teste Azul / meta Roxa) precisa estar inativo"