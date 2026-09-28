"""tests/test_relatorios_cobertura.py — Cobertura dos blocos de core/relatorios.py
que o test_relatorios.py não exercita (gate CI --cov=core.relatorios >= 80%).
Cobre: pares de contradição, classificação de observações, agrupamento,
Sensei completo (5 status), Master estruturado, tendências e ramos de vazio.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import carregar_json
from core import relatorios as R

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


def resultado_fake(nota_final=80.0, status="APROVADO", quesitos=None,
                   aluno_id="AL01", faixa="branca", **extra):
    r = {
        "aluno_id": aluno_id,
        "faixa": faixa,
        "nota_final": nota_final,
        "status": status,
        "quesitos": quesitos if quesitos is not None else {},
    }
    r.update(extra)
    return r


# --- Pares de contradição -------------------------------------------------

def test_carregar_pares_contradicao_real():
    pares = R._carregar_pares_contradicao()
    assert isinstance(pares, list)


def test_carregar_pares_contradicao_fallback(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(R, "carregar_json", boom)
    assert R._carregar_pares_contradicao() == []


def _par_com_textos():
    """Par sintético construído com os IDs reais de OBS_POSITIVAS/OBS_MELHORAR.

    Não depende do config (que usa chave 'otimo', enquanto _contradicoes_aluno
    lê 'bom') — monkeypatchando _carregar_pares_contradicao com este par, a
    detecção dispara de forma determinística.
    """
    pos_ids = list(R.OBS_POSITIVAS)
    mel_ids = list(R.OBS_MELHORAR)
    assert pos_ids and mel_ids, "constantes OBS_POSITIVAS/OBS_MELHORAR vazias"
    pid, mid = pos_ids[0], mel_ids[0]
    par = {"topico": "kihon", "bom": pid, "melhorar": mid}
    return par, R.OBS_POSITIVAS[pid], R.OBS_MELHORAR[mid]


def test_contradicoes_aluno_detecta_par(monkeypatch):
    par, bom, mel = _par_com_textos()
    monkeypatch.setattr(R, "_carregar_pares_contradicao", lambda: [par])
    r = {"observacoes": {"gerais": [f"{bom}. {mel}"]}}
    contrad = R._contradicoes_aluno(r)
    assert contrad, "esperava contradição detectada"
    assert "marcações anuladas" in contrad[0]


def test_contradicoes_aluno_sem_obs():
    assert R._contradicoes_aluno({"observacoes": {}}) == []
    assert R._contradicoes_aluno({}) == []


# --- Classificação de observações -----------------------------------------

def test_classificar_observacao_outra():
    assert R._classificar_observacao("frase sem marcador zzz") == "outra"


def test_classificar_observacao_positivas_melhorar():
    pos = list(R._OBS_POSITIVAS_TXT)
    if pos:
        assert R._classificar_observacao(pos[0]) == "forte"
    mel = list(R._OBS_MELHORAR_TXT)
    if mel:
        assert R._classificar_observacao(mel[0]) == "melhorar"


def test_observacoes_aluno_agrupa():
    pos = list(R._OBS_POSITIVAS_TXT)
    mel = list(R._OBS_MELHORAR_TXT)
    frase = "frase neutra zzz"
    if pos:
        frase += ". " + pos[0]
    if mel:
        frase += "; " + mel[0]
    r = {
        "observacoes": {
            "gerais": [frase],
            "por_quesito": {"kihon": ["outra marca", ""]},
        },
        "observacoes_automaticas": [{"texto": "Auto 1"}, {"texto": ""}],
    }
    obs = R._observacoes_aluno(r)
    assert obs["outras"], "esperava ao menos uma observação 'outra'"
    assert obs["pontos_fortes"] or not pos
    assert obs["a_melhorar"] or not mel
    assert obs["automaticas"] == ["Auto 1", ""]


# --- Recomendações e agrupamento -------------------------------------------

def test_gerar_recomendacoes_ignora_fc_zero():
    quesitos = {
        "kihon": {"alerta": None, "detalhes": {
            "base_incorreta": detalhe(1.0, [1, 0, 0], "Base Incorreta"),
            "falta_foco": detalhe(0.0, [0, 0, 0], "Falta de Foco"),
        }},
    }
    recs = R.gerar_recomendacoes(resultado_fake(quesitos=quesitos), RECOMENDACOES)
    assert any(i["criterio"] == "Base Incorreta" for i in recs)
    assert not any(i["criterio"] == "Falta de Foco" for i in recs)


def test_grupo_por_status_default():
    rs = [
        resultado_fake(status="APROVADO"),
        resultado_fake(status="AUSENTE"),
        resultado_fake(status=None),
        resultado_fake(status="NAO_EXISTE"),
    ]
    g = R._grupo_por_status(rs)
    assert len(g["APROVADO"]) == 1
    assert len(g["AUSENTE"]) == 1
    assert len(g["REVISAO_PENDENTE"]) == 1  # status None -> default
    assert len(g["NAO_EXISTE"]) == 1        # status desconhecido vira chave própria


def test_bloco_aluno_ausente():
    linhas = R._bloco_aluno(resultado_fake(status="AUSENTE"), RECOMENDACOES, False)
    assert any("ausente" in l for l in linhas)


# --- Relatório do Sensei (completo, 5 status) ------------------------------

def test_relatorio_sensei_completo(monkeypatch):
    par, bom, mel = _par_com_textos()
    monkeypatch.setattr(R, "_carregar_pares_contradicao", lambda: [par])
    q1 = {
        "kihon": {"alerta": None, "detalhes": {
            "base_incorreta": detalhe(1.5, [1, 1, 0], "Base Incorreta")}},
        "kata": {"alerta": None, "detalhes": {}},
        "bunkai": {"alerta": None, "detalhes": {}},
        "kumite": {"alerta": None, "detalhes": {}},
    }
    resultados = [
        resultado_fake(aluno_id="A1", status="APROVADO", nota_final=90.5,
                       quesitos=q1,
                       observacoes={"gerais": [f"{bom}. {mel}"]},
                       observacoes_automaticas=[{"texto": "Auto do sistema"}]),
        resultado_fake(aluno_id="A2", status="APROVADO_PONTO_ATENCAO",
                       nota_final=79.0,
                       observacoes={"gerais": ["frase neutra zzz"]}),
        resultado_fake(aluno_id="A3", status="REPROVADO", nota_final=55.0),
        resultado_fake(aluno_id="A4", status="AUSENTE", nota_final=0.0),
        resultado_fake(aluno_id="A5", status="REVISAO_PENDENTE", nota_final=0.0),
    ]
    texto, dados = R.gerar_relatorio_sensei(
        resultados, REGRA_PADRAO, RECOMENDACOES, "D01", "EXA-2026-01")

    assert dados["tipo"] == "sensei"
    assert dados["dojo_id"] == "D01"
    assert dados["exame_id"] == "EXA-2026-01"
    assert dados["total_alunos"] == 5
    assert dados["total_presentes"] == 4
    assert len(dados["aprovados"]) == 1
    assert len(dados["aprovado_ponto_atencao"]) == 1
    assert len(dados["reprovados"]) == 1
    assert len(dados["ausentes"]) == 1
    assert dados["revisao_pendente"] == ["A5"]
    assert len(dados["desempenho_alunos"]) == 4
    assert dados["desempenho_alunos"][0]["pontos_atencao"]

    assert "RELATORIO DO SENSEI — DOJO D01" in texto
    assert "Exame: EXA-2026-01" in texto
    assert "Total de alunos: 5 | Presentes: 4 | Ausentes: 1" in texto
    assert "APROVADOS:" in texto and "A1 (branca) — 90.5" in texto
    assert "REPROVADOS:" in texto and "A3" in texto
    assert "DESEMPENHO POR ALUNO:" in texto
    assert "Pontos de atenção: (nenhum)" in texto
    assert "Pontos fortes:" in texto and "A melhorar:" in texto
    assert "Automaticas: Auto do sistema" in texto
    assert "marcações anuladas" in texto


def test_relatorio_sensei_sem_exame_id():
    texto, dados = R.gerar_relatorio_sensei(
        [resultado_fake(aluno_id="A1")], REGRA_PADRAO, RECOMENDACOES, "D01", "")
    assert "Exame:" not in texto
    assert dados["exame_id"] == ""


# --- Master estruturado -----------------------------------------------------

def test_media_marcacoes_por_quesito_vazio():
    res = R._media_marcacoes_por_quesito([])
    assert set(res) == {"kihon", "kata", "bunkai", "kumite"}
    assert all(v["pct"] == 0.0 for v in res.values())


def test_gerar_relatorio_master_completo(monkeypatch):
    par, bom, mel = _par_com_textos()
    monkeypatch.setattr(R, "_carregar_pares_contradicao", lambda: [par])
    qa = {
        "kihon": {"alerta": None, "detalhes": {
            "base_incorreta": detalhe(2.0, [2, 2, 2], "Base Incorreta")}},
        "kata": {"alerta": None, "detalhes": {}},
        "bunkai": {"alerta": None, "detalhes": {}},
        "kumite": {"alerta": None, "detalhes": {}},
    }
    dojo_a = {"dojo_id": "D01", "alunos": [
        resultado_fake(aluno_id="A1", status="APROVADO", nota_final=90.0,
                       quesitos=qa,
                       observacoes={"gerais": [f"{bom}. {mel}"]},
                       observacoes_automaticas=[{"texto": "Auto do sistema"}]),
        resultado_fake(aluno_id="A2", status="AUSENTE", nota_final=0.0),
    ]}
    dojo_b = {"dojo_id": "D02", "alunos": [
        resultado_fake(aluno_id="B1", status="APROVADO_PONTO_ATENCAO",
                       nota_final=75.0),
    ]}
    texto, dados = R.gerar_relatorio_master([dojo_a, dojo_b], REGRA_PADRAO,
                                            RECOMENDACOES)
    assert dados["tipo"] == "master"
    assert dados["n_presentes_total"] == 2
    assert len(dados["dojos"]) == 2
    assert dados["dojos"][0]["media"] == 90.0
    assert dados["dojos"][0]["taxa_aprovacao"] == 100.0
    assert dados["dojos"][1]["taxa_atencao"] == 100.0
    assert dados["media_quesitos"]["kihon"]["pct"] > 0
    assert len(dados["alunos"]) == 2

    assert "Dojos considerados: 2" in texto
    assert "Alunos presentes: 2" in texto
    assert "MEDIA DE MARCACOES POR QUESITO (%)" in texto
    assert "DESEMPENHO POR ALUNO" in texto
    assert "Auto do sistema" in texto
    assert "marcações anuladas" in texto


def test_gerar_relatorio_master_vazio():
    texto, dados = R.gerar_relatorio_master([], REGRA_PADRAO, RECOMENDACOES)
    assert "Sem dados de dojos" in texto
    assert dados["dojos"] == []


def test_gerar_relatorio_master_todos_ausentes():
    dojo = {"dojo_id": "D01", "alunos": [resultado_fake(status="AUSENTE")]}
    texto, dados = R.gerar_relatorio_master([dojo], REGRA_PADRAO, RECOMENDACOES)
    assert "Nenhum aluno presente" in texto
    assert dados["n_presentes_total"] == 0


# --- Individual, Tendências e Master (ramos de vazio) -----------------------

def test_relatorio_individual_obs_automaticas():
    r = resultado_fake(nota_final=90.0)
    r["observacoes_automaticas"] = [{"texto": "Texto automatico do sistema"}]
    texto = R.relatorio_individual(r, REGRA_PADRAO, RECOMENDACOES,
                                   {"nome": "Aluno X"})
    assert "ALUNO: Aluno X" in texto
    assert "Texto automatico do sistema" in texto


def test_tendencias_sem_alunos():
    assert "Sem alunos avaliados" in R.relatorio_tendencias([], RECOMENDACOES)


def test_tendencias_sem_criterios_recorrentes():
    r = resultado_fake(quesitos={
        "kihon": {"alerta": None, "detalhes": {}},
        "kata": {"alerta": None, "detalhes": {}},
        "bunkai": {"alerta": None, "detalhes": {}},
        "kumite": {"alerta": None, "detalhes": {}},
    })
    texto = R.relatorio_tendencias([r], RECOMENDACOES)
    assert "Nenhum critério recorrente" in texto


def test_relatorio_master_vazio():
    assert "Sem dados de dojos" in R.relatorio_master([], REGRA_PADRAO,
                                                      RECOMENDACOES)


def test_relatorio_master_sem_diretriz_50():
    def _dojo(did, chave):
        return {"dojo_id": did, "alunos": [resultado_fake(quesitos={
            "kihon": {"alerta": None, "detalhes": {
                chave: detalhe(1.0, [1, 0, 0], chave)}},
            "kata": {"alerta": None, "detalhes": {}},
            "bunkai": {"alerta": None, "detalhes": {}},
            "kumite": {"alerta": None, "detalhes": {}},
        })]}

    dojos = [_dojo("D01", "base_incorreta"),
             _dojo("D02", "falta_foco"),
             _dojo("D03", "ausencia_kiai")]
    texto = R.relatorio_master(dojos, REGRA_PADRAO, RECOMENDACOES)
    assert "DIRETRIZES PEDAGOGICAS GLOBAIS" in texto
    assert "Nenhum critério atingiu 50%" in texto