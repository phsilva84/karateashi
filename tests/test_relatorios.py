"""tests/test_relatorios.py — Testes da Fase 05 (relatórios em 3 camadas).

Cobertura: níveis por fc, saturação, ajuste de consenso (sobe/desce),
elogio transversal, quesito perfeito, destaque >= 85, ordem de exibição,
recorrência 50%/80% do Dojo, taxa de status, foco do ciclo, tendências e Master.

Uso: python -m pytest tests/ -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.relatorios import (
    carregar_json,
    consolidar_dojo,
    formatar_consolidado_dojo,
    gerar_elogios,
    nivel_recomendacao,
    relatorio_individual,
    relatorio_master,
    relatorio_tendencias,
)

RAIZ = Path(__file__).resolve().parents[1]
RECOMENDACOES = carregar_json(RAIZ / "config" / "recomendacoes.json")

REGRA_PADRAO = {
    "elogios": {
        "criterio_transversal_min_quesitos": 2,
        "destaque_geral_min": 85.0,
    },
}

def detalhe(fc, marcacoes, nome="Criterio"):
    return {"fc": fc, "marcacoes": marcacoes, "nome": nome}

def resultado_fake(nota_final=80.0, status="APROVADO", quesitos=None):
    if quesitos is None:
        quesitos = {q: {"alerta": None, "detalhes": {}}
                    for q in ["kihon", "kata", "bunkai", "kumite"]}
    return {"nota_final": nota_final, "status": status, "quesitos": quesitos}

def aluno_com(criterios_por_quesito):
    quesitos = {}
    for q in ["kihon", "kata", "bunkai", "kumite"]:
        detalhes = {}
        for chave in criterios_por_quesito.get(q, []):
            detalhes[chave] = detalhe(1.0, [1, 0, 0], chave)
        quesitos[q] = {"alerta": None, "detalhes": detalhes}
    return resultado_fake(nota_final=75.0, quesitos=quesitos)

# --- Níveis e ajustes de consenso ---

def test_nivel_por_fc():
    assert nivel_recomendacao(5.0, [0, 0, 0], 3) == "CRITICO"
    assert nivel_recomendacao(3.0, [0, 0, 0], 3) == "ATENCAO"
    assert nivel_recomendacao(1.0, [0, 0, 0], 3) == "OBSERVACAO"
    assert nivel_recomendacao(0.0, [0, 0, 0], 3) == "FORCA"

def test_saturacao_sete_marcacoes():
    assert nivel_recomendacao(2.0, [7, 0, 0], 3) == "CRITICO"

def test_saturacao_vence_percepcao_isolada():
    # Decisão aprovada: saturação (7+ marcações de um avaliador) é sinal
    # mais forte que percepção isolada — mantém CRITICO mesmo com 1 de 3.
    assert nivel_recomendacao(2.0, [7, 0, 0], 3) == "CRITICO"
    assert nivel_recomendacao(4.0, [8, 0, 0], 3) == "CRITICO"

def test_percepcao_isolada_desce():
    assert nivel_recomendacao(5.0, [3, 0, 0], 3) == "ATENCAO"    # CRITICO -> ATENCAO
    assert nivel_recomendacao(3.0, [2, 0, 0], 3) == "OBSERVACAO"  # ATENCAO -> OBSERVACAO
    assert nivel_recomendacao(1.0, [1, 0, 0], 3) == "OBSERVACAO"  # sem nível abaixo

def test_consenso_total_sobe():
    assert nivel_recomendacao(1.0, [1, 1, 1], 3) == "ATENCAO"   # OBSERVACAO -> ATENCAO
    assert nivel_recomendacao(3.0, [2, 2, 2], 3) == "CRITICO"   # ATENCAO -> CRITICO
    assert nivel_recomendacao(5.0, [3, 3, 3], 3) == "CRITICO"   # já CRITICO

# --- Elogios ---

def test_elogio_transversal():
    quesitos = {
        "kihon": {"alerta": None, "detalhes": {"base_incorreta": detalhe(0.0, [0, 0, 0], "Base incorreta")}},
        "kata": {"alerta": None, "detalhes": {"base_incorreta": detalhe(0.0, [0, 0, 0], "Base incorreta")}},
        "bunkai": {"alerta": None, "detalhes": {"base_incorreta": detalhe(2.0, [1, 1, 0], "Base incorreta")}},
        "kumite": {"alerta": None, "detalhes": {}},
    }
    elogios = gerar_elogios(resultado_fake(quesitos=quesitos), REGRA_PADRAO, RECOMENDACOES)
    assert any("Base exemplar" in e for e in elogios)

def test_quesito_perfeito():
    quesitos = {
        "kihon": {"alerta": None, "detalhes": {"base_incorreta": detalhe(0.0, [0, 0, 0])}},
        "kata": {"alerta": None, "detalhes": {"falta_foco": detalhe(1.0, [1, 0, 0])}},
        "bunkai": {"alerta": None, "detalhes": {}},
        "kumite": {"alerta": None, "detalhes": {}},
    }
    elogios = gerar_elogios(resultado_fake(quesitos=quesitos), REGRA_PADRAO, RECOMENDACOES)
    assert any("Kihon impecável" in e for e in elogios)

def test_destaque_geral_85():
    elogios = gerar_elogios(resultado_fake(nota_final=90.0), REGRA_PADRAO, RECOMENDACOES)
    assert any("Destaque do exame" in e for e in elogios)
    elogios_baixo = gerar_elogios(resultado_fake(nota_final=84.0), REGRA_PADRAO, RECOMENDACOES)
    assert not any("Destaque do exame" in e for e in elogios_baixo)

# --- Ordem de exibição do relatório individual ---

def test_ordem_relatorio_individual():
    quesitos = {
        "kihon": {"alerta": None, "detalhes": {
            "base_incorreta": detalhe(1.0, [1, 0, 0], "Base incorreta"),
            "falta_controle": detalhe(5.0, [3, 3, 3], "Falta de controle"),
        }},
        "kata": {"alerta": None, "detalhes": {
            "falta_foco": detalhe(3.0, [1, 1, 0], "Falta de foco"),  # ATENCAO
        }},
        "bunkai": {"alerta": None, "detalhes": {}},
        "kumite": {"alerta": "ALERTA_ETICO", "detalhes": {
            "falta_controle": detalhe(2.0, [1, 0, 0], "Falta de controle"),
        }},
    }
    texto = relatorio_individual(
        resultado_fake(nota_final=90.0, quesitos=quesitos),
        REGRA_PADRAO, RECOMENDACOES, {"nome": "Aluno Teste"},
    )
    pos = {chave: texto.index(chave) for chave in
           ["ALERTA ETICO", "[CRITICO]", "[ATENCAO]", "[OBSERVACAO]", "PONTOS FORTES"]}
    assert pos["ALERTA ETICO"] < pos["[CRITICO]"] < pos["[ATENCAO]"] < pos["[OBSERVACAO]"] < pos["PONTOS FORTES"]

# --- Consolidação do Dojo (recorrência 50%/80%) ---

def test_recorrencia_50_80():
    alunos = [
        aluno_com({"kihon": ["base_incorreta"], "kata": ["falta_foco"]}),
        aluno_com({"kihon": ["base_incorreta"]}),
        aluno_com({"kihon": ["base_incorreta"]}),
        aluno_com({"kihon": ["base_incorreta"], "kata": ["falta_foco"]}),
    ]
    cons = consolidar_dojo(alunos, REGRA_PADRAO)
    prioridades = dict(cons["prioridades_treino"])
    assert prioridades["Kihon.base_incorreta"] == "Prioridade máxima de treino"
    assert prioridades["Kata.falta_foco"] == "Prioridade de treino do Dojo"

def test_taxa_status_e_foco_ciclo():
    alunos = [
        resultado_fake(nota_final=80.0, status="APROVADO"),
        resultado_fake(nota_final=80.0, status="APROVADO"),
        resultado_fake(nota_final=60.0, status="RECUPERACAO"),
    ]
    cons = consolidar_dojo(alunos, REGRA_PADRAO)
    assert cons["total_alunos"] == 3
    assert cons["taxa"]["APROVADO"] == 66.7
    assert cons["taxa"]["RECUPERACAO"] == 33.3
    assert cons["foco_ciclo"] == "Kihon"  # empate -> primeiro da ordem

def test_formatar_consolidado_dojo():
    alunos = [aluno_com({"kihon": ["base_incorreta"]}) for _ in range(4)]
    texto = formatar_consolidado_dojo(consolidar_dojo(alunos, REGRA_PADRAO))
    assert "RELATORIO CONSOLIDADO DO DOJO" in texto
    assert "Prioridade máxima de treino" in texto

# --- Tendências ---

def test_tendencias_moda_e_exercicio():
    alunos = [aluno_com({"kihon": ["base_incorreta"]}) for _ in range(4)]
    texto = relatorio_tendencias(alunos, RECOMENDACOES)
    assert "Moda do exame" in texto
    assert "Kihon - Base incorreta" in texto
    assert "Kihon de bases" in texto  # exercício corretivo da biblioteca

# --- Master multi-dojo ---

def test_master_consolida_media_e_aprovacao():
    dojo_a = {"dojo_id": "DOJO-A", "alunos": [
        resultado_fake(nota_final=90.0, status="APROVADO"),
        resultado_fake(nota_final=70.0, status="APROVADO"),
    ]}
    dojo_b = {"dojo_id": "DOJO-B", "alunos": [
        resultado_fake(nota_final=60.0, status="RECUPERACAO"),
        resultado_fake(nota_final=80.0, status="APROVADO"),
    ]}
    texto = relatorio_master([dojo_a, dojo_b], REGRA_PADRAO, RECOMENDACOES)
    assert "Dojo DOJO-A" in texto and "média 80.0" in texto and "aprovação 100%" in texto
    assert "Dojo DOJO-B" in texto and "média 70.0" in texto and "aprovação 50%" in texto

def test_master_diretriz_global_50():
    dojo_a = {"dojo_id": "DOJO-A", "alunos": [aluno_com({"kihon": ["base_incorreta"]})]}
    dojo_b = {"dojo_id": "DOJO-B", "alunos": [aluno_com({"kihon": ["base_incorreta"]})]}
    texto = relatorio_master([dojo_a, dojo_b], REGRA_PADRAO, RECOMENDACOES)
    assert "DIRETRIZES PEDAGOGICAS GLOBAIS" in texto
    assert "Base incorreta" in texto

def test_master_alerta_queda_media():
    dojo = {"dojo_id": "DOJO-A", "media_anterior": 85.0,
            "alunos": [resultado_fake(nota_final=70.0, status="APROVADO")]}
    texto = relatorio_master([dojo], REGRA_PADRAO, RECOMENDACOES)
    assert "Alerta de acompanhamento" in texto