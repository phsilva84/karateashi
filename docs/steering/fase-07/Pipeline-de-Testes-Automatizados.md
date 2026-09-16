
FASE 07 — Pipeline de Testes Automatizados (GitHub Actions)0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Engenheiro SRE/DevOps — GitHub Actions, quality gates, dependências Python, jobs parametrizados.
Dev Python Sênior — pytest, fixtures, cobertura, testes de borda e estresse.
QA / Testador — cenários da Seção 14 da especificação v2.0 (zero faltas, saturação, trava, variação de bancas).
Regras de conduta:
Use SEMPRE a estrutura de módulos das Fases 00–06 (core/engine.py, core/parser.py, core/omr_reader.py, core/relatorios.py, tools/pre_exame.py, config/faixas/, config/coordenadas/).
Não invente testes que dependam de arquivos que não existem no repositório (ex: testes de imagem real só no job manual).
Cada job de testes falha se a cobertura do módulo cair abaixo de 80% — nunca baixar o gate.
Ao final, preencha o checklist de aceite com o resultado real do workflow na aba Actions.

1. ObjetivoCriar o pipeline de testes automatizados do Karate-Ashi no GitHub Actions, integrado ao repositório, que roda a cada push/PR e garante:
   Validação de todos os JSONs de configuração antes de qualquer teste.
   Quality gates por fase: engine, parser, faixas, OMR (funções puras), relatórios — cada um com cobertura mínima de 80%.
   Testes de estresse (Seção 14 da especificação) como etapa bloqueadora.
   Job manual (workflow_dispatch) para calibração OMR com folhas de teste reais.
   Badge de status no README.
   ✅ Objetivo atingido — pipeline 100% verde na PR #5 ("New system - Refatoração do sistema").2. Contexto mínimo do projetoO Karate-Ashi é Python 3.9+ (uso do str | None no OMR exige 3.10+; recomendado Python 3.11 no CI). O repositório já usa GitHub Actions para orquestração de produção (pipeline.yml). Cada fase de steering entregou seus testes: tests/test_engine.py (Fase 01), tests/test_parser.py (Fase 02), tests/test_omr_validador.py (Fase 03), tests/test_faixas.py (Fase 06), tests/test_relatorios.py (Fase 05). Falta o pipeline que roda tudo automaticamente.
   Atenção de runtime descoberta na execução: core/omr_reader.py importa pyzbar (dependência nativa libzbar0), e o core.engine importa o OMR. Qualquer teste que toque o engine exige a lib no runner — corrigido nesta fase (seção 8.1).
2. Decisões aprovadas (não reabrir)
   Plataforma: GitHub Actions (definitivo — não Jenkins nesta fase).
   Runner: ubuntu-latest · Python 3.11.
   Cobertura mínima: 80% por módulo (--cov-fail-under=80).
   Validar todos os config/*.json como primeiro passo.
   Testes de estresse rodam em job separado e são bloqueadores.
   Calibração OMR = job manual (workflow_dispatch), sem fotos reais no CI automático.
   Badge de status no README.md.
   NOVO — Cobertura insuficiente nunca se resolve baixando o gate; resolve-se ampliando os testes (aprendizado da execução, seção 8).
   NOVO — o --cov deve escopar o módulo que a suíte exercita, não o pacote inteiro (evita falso negativo, seção 8.4).
3. Tarefas (status real)

TarefaStatusCriar .github/workflows/testes.yml✅ concluído e aprovado (versão final na seção 5.1)Criar requirements-dev.txt (pytest + pytest-cov)✅ concluído (seção 5.2)Criar tests/conftest.py (fixture base_cfg)✅ concluído (seção 5.3)Criar tests/test_estresse.py (cenários da Seção 14)✅ concluído e aprovado no CI (seção 5.4)Criar tools/calibrar_omr.py — esqueleto de densidade✅ concluído (seção 5.7) — roda só no job manualAdicionar o badge de status no README.md✅ concluído (seção 5.8, URL corrigida)Fazer push e validar na aba Actions que todos os jobs passam✅ validado — 3 jobs verdes em ~54s (seção 6)Ampliar cobertura do OMR para ≥80% (37% inicial)✅ 37% → 97% (seção 8.2)Ampliar cobertura do engine via test_faixas.py (77% inicial)✅ ≥80% (seções 8.5–8.7)Registrar resultado no Status (seção 7)✅ feito5. Código de referência — versão final implementada5.1 .github/workflows/testes.yml (FINAL — com correções aplicadas)Diferenças em relação ao rascunho original: (a) step libzbar0 adicionado nos jobs Python (resolve ImportError de runtime); (b) etapa Fase 06 escopada para --cov=core.engine (o rascunho usava --cov=core, que media o pacote inteiro e gerava falso 16%).Código1234567891011121314151617181920212223242526272829303132333435363738394041424344454647484950515253545556575859606162636465666768697071727374757677787980818283848586878889909192name: Testes Automatizados Karate-Ashi

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  validacao-config:
    name: Validar Configurações JSON
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Validar todos os JSONs de config/
        run: |
          python -c "
          import json, pathlib
          arquivos = list(pathlib.Path('config').rglob('*.json'))
          assert arquivos, 'Nenhum JSON encontrado em config/'
          for p in arquivos:
              json.loads(p.read_text(encoding='utf-8'))
          print(f'OK: {len(arquivos)} JSON(s) válido(s)')
          "

  testes:
    name: Testes por Fase (Quality Gates)
    runs-on: ubuntu-latest
    needs: validacao-config
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Instalar dependências de sistema (libzbar)
        run: sudo apt-get update && sudo apt-get install -y libzbar0
      - name: Instalar dependências
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Motor de cálculo (Fase 01)
        run: pytest tests/test_engine.py -q --cov=core.engine --cov-fail-under=80
      - name: Parser de fallback TXT (Fase 02)
        run: pytest tests/test_parser.py -q --cov=core.parser --cov-fail-under=80
      - name: OMR - funções puras (Fase 03)
        run: pytest tests/test_omr_validador.py -q --cov=core.omr_reader --cov-fail-under=80
      - name: Relatórios em 3 camadas (Fase 05)
        run: pytest tests/test_relatorios.py -q --cov=core.relatorios --cov-fail-under=80
      - name: Estrutura multi-faixa (Fase 06)
        run: pytest tests/test_faixas.py -q --cov=core.engine --cov-fail-under=80

  estresse:
    name: Testes de Estresse (Seção 14)
    runs-on: ubuntu-latest
    needs: validacao-config
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Instalar dependências de sistema (libzbar)
        run: sudo apt-get update && sudo apt-get install -y libzbar0
      - name: Instalar dependências
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Cenários de borda e convergência
        run: pytest tests/test_estresse.py -q -v

  calibracao-omr:
    name: Calibração OMR (manual)
    runs-on: ubuntu-latest
    if: github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Instalar dependências de sistema (libzbar)
        run: sudo apt-get update && sudo apt-get install -y libzbar0
      - name: Instalar dependências
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Medir densidade das folhas de teste
        run: python tools/calibrar_omr.py --gabaritos data/gabaritos/teste/5.2 requirements-dev.txtCódigopytest>=7.4
pytest-cov>=4.15.3 tests/conftest.pyCódigo12345678"""Fixtures compartilhadas dos testes do Karate-Ashi."""
from pathlib import Path
import pytest

@pytest.fixture
def base_cfg() -> Path:
    """Caminho até a pasta config/ do repositório (Fases 00 e 06)."""
    return Path(__file__).resolve().parents[1] / "config"
Nota de execução local (QA): o erro pytest: error: unrecognized arguments: --cov=... --cov-fail-under=... indica pytest-cov ausente no venv — rodar pip install -r requirements-dev.txt (o CI já instala).
5.4 tests/test_estresse.py (rascunho original — aprovado sem alteração)O código da seção 4 do rascunho (cenários 1, 2, 3, 3b e 4 da Seção 14) foi mantido sem alteração e passou no CI como job bloqueador.Pendência documentada (não reaberta na Fase 07): o helper _avaliacao_vazia cobre só os critérios de Kihon; considerar completá-lo para exercitar embusen_incorreto (Kata) e falta_combatividade (Kumite) na Fase 08, sem impacto no gate (job de estresse não mede cobertura).5.5 tests/test_omr_validador.py — bloco adicional de cobertura (37% → 97%)Adicionado ao final do arquivo. Estratégia: imagens sintéticas (geradas em código com cv2.rectangle/cv2.circle, sem binários no repositório) + monkeypatch de pyzbar.pyzbar.decode e omr_reader.decodificar_qr para o pipeline rodar sem QR real e sem lib nativa.Cobertura dos cenários:
parse_payload_qr válido e inválido (ValueError)
carregar_json (sucesso)
roi_mm_para_px (conversão) e _validar_coordenadas (ok / zeradas / quesito faltando)
classificar_checkbox (vazio / marcado / suspeito)
contar_marcacoes_linha (contíguas / não-contíguas / suspeitas)
validar_folha (ok / limite 7 / folha em branco)
decodificar_qr com pyzbar mockado (sucesso / sem QR)
detectar_e_corrigir com folha sintética (sucesso / nenhum contorno / não-quadrilátero)
processar_imagem completo com mocks (sucesso / QR ausente / faixa divergente / ROI estreita)
Resultado verificado: core/omr_reader.py — 133 stmts, 4 miss, 97% de cobertura, 25 testes aprovados.5.6 tests/test_faixas.py — bloco adicional + cenário RECUPERACAO calibradoAdicionado ao final do arquivo, mantendo os testes originais da Fase 06. Componentes:
from __future__ import annotations no topo (proteção contra NameError de anotações avaliadas antes do import).
Constante CRITERIOS_ENGINE (A1–A12, a mesma lista validada no test_estresse.py) para montar o avaliador saturado — o config guarda critérios como dicionários, não strings (por isso o helper não lê o JSON diretamente).
Testes: descontos por critério (detalhes[...]["fc"]), REPROVADO (saturação), ALERTA_ETICO (1/3 com falta_controle), TRAVA no Kumite (3/3, teto 10,0), consenso com N=1 e N=2, zero faltas nas demais faixas (amarela→azul), derivação de faixa via aluno.faixa_atual, REVISAO_PENDENTE (dados legados), repasse de observações.
Cenário-chave — status intermediário (calibrado com as fontes reais):Código12345678910111213141516171819202122232425262728def test_processa_aluno_recuperacao(base_cfg: Path):
    """Nota 68,0 → status RECUPERACAO (60 ≤ nota < 70).

    Fórmula real do engine: desconto = fc × peso × multiplicador
    (regras_gerais.json: fc=2 → mult 1,5 | fc=1 → mult 1,0).
    Desconto de 8,0 por quesito → 25 - 8 = 17,0 × 4 = 68,0.
    Sem falta_controle → a trava de segurança não interfere.
    """
    from core.engine import processa_aluno

    avs = [
        _avaliador(
            kihon={"base_incorreta": 2, "execucao_tecnica_incorreta": 2,
                   "movimento_sem_carga": 1, "falta_foco": 1},
            kata={"embusen_incorreto": 1, "base_incorreta": 1,
                  "execucao_tecnica_incorreta": 1, "movimento_sem_carga": 1,
                  "falta_foco": 1, "perda_equilibrio": 1,
                  "falta_ritmo": 1, "ausencia_kiai": 1},
            bunkai={"base_incorreta": 2, "execucao_tecnica_incorreta": 2,
                    "movimento_sem_carga": 1, "falta_foco": 1},
            kumite={"movimento_sem_carga": 2, "falta_foco": 2,
                    "perda_equilibrio": 1, "distancia_inadequada": 1},
        )
        for _ in range(3)
    ]
    r = processa_aluno(avs, base_cfg, "branca")
    assert r["status"] == "RECUPERACAO"
    assert r["nota_final"] == 68.0Resultado verificado: gate do core.engine ≥ 80% atingido (execução local e CI verdes).5.7 tools/calibrar_omr.py (esqueleto — job manual)Mantido o esqueleto do rascunho (medir_densidade + main com --gabaritos/--faixa/--config). Não executado no CI automático — o job calibracao-omr depende de data/gabaritos/teste/ e de folhas com QR real (por design).5.8 Badge no README.md (corrigido)Markdown# Karate-Ashi

![Testes](https://github.com/phsilva84/karateashi/actions/workflows/testes.yml/badge.svg)
O placeholder do rascunho foi substituído pela URL real do repositório phsilva84/karateashi.
6. Critérios de aceite — CHECKLIST PREENCHIDO (resultado real)
✅ Workflow Testes Automatizados Karate-Ashi aparece na aba Actions do repositório.
✅ Roda automaticamente em push (main) e pull_request (verificado no evento pull_request da PR #5).
✅ validacao-config passa com todos os JSONs de config/ válidos.
✅ Todos os jobs de testes por fase passam, cada um com cobertura ≥ 80%.
✅ estresse passa com os 5 cenários (zero faltas, saturação, trava total, trava parcial, variação de bancas).
✅ Job calibracao-omr visível e executável manualmente (workflow_dispatch) — não executado (depende de gabaritos reais).
✅ Badge verde no README.md.
✅ Execução local equivalente: pytest -q roda a suíte inteira sem erros (validado em Windows/Python 3.9 e Linux/Python 3.11).
Execução verificada: PR #5 ("New system - Refatoração do sistema") — 3 jobs verdes em ~54s.7. Status
 Pendente
 Em execução
 Concluída (16/09/2026)
8. Registro de execução — ocorrências e correções8.1 ImportError: Unable to find zbar shared librarySintoma — o job testes falhava já na primeira etapa (Fase 01), antes de qualquer cálculo.
Causa raiz — core/omr_reader.py importava from pyzbar.pyzbar import decode no topo do módulo; como core.engine importa o OMR, qualquer teste exigia a lib nativa libzbar0, ausente no runner.
Correção (código) — import movido para dentro de decodificar_qr() (lazy import); o módulo importa sem a lib e as funções puras funcionam em qualquer ambiente. git diff mostra exatamente duas linhas alteradas.
Correção (workflow) — sudo apt-get install -y libzbar0 antes do pip install nos jobs testes, estresse e calibracao-omr.8.2 Cobertura 37% < 80% em core.omr_reader (Fase 03)Causa raiz — pipeline OpenCV, decode de QR e caminhos de erro sem teste.
Correção — bloco da seção 5.5 (imagens sintéticas + mocks do QR).
Resultado — 37% → 97% (25 testes).8.3 unrecognized arguments: --cov=... --cov-fail-under=... (ambiente local)Causa raiz — pytest-cov ausente no venv (vive no requirements-dev.txt).
Correção — pip install -r requirements-dev.txt; conferir com pytest --version listando o plugin cov.8.4 Cobertura 16% < 80% na Fase 06 (defeito do rascunho)Causa raiz — etapa usava --cov=core (pacote inteiro); test_faixas.py só exercita core.engine, e os demais módulos entravam com 0%.
Correção — escopo alterado para --cov=core.engine, consistente com a Fase 01.
Descoberta — mesmo escopado, a suíte cobria só 77% do engine → foi preciso ampliar os testes (8.5–8.7), não afrouxar o gate.8.5 NameError: name 'Path' is not definedCausa raiz — bloco novo inserido acima do from pathlib import Path; anotações de tipo são avaliadas na definição da função.
Correção — imports no topo + from __future__ import annotations em todo módulo de teste.
Do mesmo erro — o cenário de ALERTA_ETICO marcava 3/3 (cenário de trava); corrigido para 1/3.8.6 TypeError: unhashable type: 'dict'Causa raiz — criterios no JSON é uma lista de dicionários (codigo/chave/nome/peso), não de strings; um dict não pode ser chave de outro dict.
Correção — usar a lista CRITERIOS_ENGINE (A1–A12 validada no test_estresse.py).8.7 AssertionError: 'APROVADO' == 'RECUPERAÇÃO' (duas tentativas)Três causas encadeadas — a correção mais instrutiva da fase:
Acentuação — o engine devolve "RECUPERACAO" (ASCII, sem cedilha).
Multiplicador progressivo — config/regras_gerais.json define o fator por faixa de fc: 0,0→0 · 0,1–1,0→1,0 · 1,1–2,5→1,5 · 2,6–4,5→2,0 · 4,6–7,0→2,5. Desconto = fc × peso × multiplicador. Cenários iniciais assumiam multiplicador 1,0 e inflavam a nota (92,0 e ~82,0) para APROVADO.
Critérios por quesito — config/faixas/branca.json define pesos por quesito (embusen_incorreto só no Kata; base_incorreta não existe no Kumite); critério inexistente vira zero silencioso (.get(chave, 0)).
Correção — cenário recalculado com a tabela real e os multiplicadores reais (seção 5.6) → 68,0 → RECUPERACAO, sem usar falta_controle (trava).9. Herança da fase anterior
Fases 01–06 entregaram os módulos e os testes por fase (test_engine, test_parser, test_omr_validador, test_faixas, test_relatorios).
processa_aluno já recebe faixa (Fase 06) — os testes de estresse usam essa assinatura.
Fontes da verdade consolidadas nesta fase: config/faixas/<faixa></faixa>.json (critérios por quesito) e config/regras_gerais.json (multiplicador, trava, status) — a tabela v1.1 (A10 = 12,0 etc.) está obsoleta; a referência válida é a v2.0 dos JSONs.
10. Entrega para a próxima fase
testes.yml consolidado (4 jobs), requirements-dev.txt, conftest.py, test_estresse.py, blocos de cobertura de test_omr_validador.py e test_faixas.py, calibrar_omr.py → validam as Fases 01–06 antes da Fase 08.
Passos de fechamento imediatos: (1) merge da PR #5 em main com --no-ff; (2) proteção de branch na main exigindo os status checks Testes por Fase (Quality Gates) e Testes de Estresse (Seção 14); (3) apagar a branch new-system; (4) revisar test_parser.py e test_relatorios.py para blindar Fases 02 e 05 contra regressão.
Pendência para a Fase 08: completar _avaliacao_vazia do estresse com embusen_incorreto e falta_combatividade; calibração OMR real via job manual; escopo detalhado da Fase 08.
11. Resumo da execução
Fase executada e concluída em 16/09/2026. Pipeline 100% verde na PR #5: validacao-config, Testes por Fase (Quality Gates) com 5 etapas e Testes de Estresse com 5 cenários — ~54s por execução.
Coberturas: core.omr_reader 37% → 97% (25 testes); core.engine (via test_faixas.py) 77% → ≥80%.
Correções aplicadas: lazy import do pyzbar + libzbar0 nos jobs; escopo da Fase 06 para core.engine; ampliação dos dois arquivos de teste com dados sintéticos e cenários calibrados às regras reais (multiplicador progressivo e critérios por quesito).
Merge e proteção de branch: passos de fechamento (seção 10), pendentes de execução pelo operador.
Notas: badge do README corrigido para phsilva84/karateashi; job calibracao-omr permanece manual, por depender de gabaritos e QR reais.
Resumindo
O MD passou de "Fase NÃO executada (pendente)" para concluída em 16/09/2026, com checklist de aceite preenchido com o resultado real (3 jobs verdes, ~54s, PR #5).
O testes.yml final incorpora as duas correções da sessão: libzbar0 nos jobs Python e --cov=core.engine na Fase 06.
A seção 8 registra as 7 ocorrências com causa-raiz e correção — incluindo a descoberta do multiplicador progressivo e dos critérios por quesito.
Coberturas consolidadas: OMR 97% e engine ≥80%, ambos acima do gate.
