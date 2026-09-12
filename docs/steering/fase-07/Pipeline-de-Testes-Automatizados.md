FASE 07 — Pipeline de Testes Automatizados (GitHub Actions)0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Engenheiro SRE/DevOps — GitHub Actions, quality gates, dependências Python, jobs parametrizados.
Dev Python Sênior — pytest, fixtures, cobertura, testes de borda e estresse.
QA / Testador — cenários da Seção 14 da especificação v2.0 (zero faltas, saturação, trava, variação de bancas).
Regras de conduta:
Use SEMPRE a estrutura de módulos das Fases 00–06 (core/engine.py, core/parser.py, core/omr_reader.py, core/relatorios.py, tools/pre_exame.py, config/faixas/, config/coordenadas/).
Não invente testes que dependam de arquivos que não existem no repositório (ex: testes de imagem real só no job manual).
Cada job de testes falha se a cobertura do módulo cair abaixo de 80%.
Ao final, preencha o checklist de aceite com o resultado real do workflow na aba Actions.

1. ObjetivoCriar o pipeline de testes automatizados do Karate-Ashi no GitHub Actions, integrado ao repositório, que roda a cada push/PR e garante:
   Validação de todos os JSONs de configuração antes de qualquer teste.
   Quality gates por fase: engine, parser, faixas, OMR (funções puras), relatórios — cada um com cobertura mínima de 80%.
   Testes de estresse (Seção 14 da especificação) como etapa bloqueadora.
   Job manual (workflow_dispatch) para calibração OMR com folhas de teste reais.
   Badge de status no README.
2. Contexto mínimo do projetoO Karate-Ashi é Python 3.9+ (uso do str | None no OMR exige 3.10+; recomendado Python 3.11 no CI). O repositório já usa GitHub Actions para orquestração de produção (pipeline.yml). Cada fase de steering entregou seus testes: tests/test_engine.py (Fase 01), tests/test_parser.py (Fase 02), tests/test_omr_validador.py (Fase 03), tests/test_faixas.py (Fase 06), tests/test_relatorios.py (Fase 05). Falta o pipeline que roda tudo automaticamente.3. Decisões aprovadas (não reabrir)
   Plataforma: GitHub Actions (definitivo — não Jenkins nesta fase).
   Runner: ubuntu-latest · Python 3.11.
   Cobertura mínima: 80% por módulo (--cov-fail-under=80).
   Validar todos os config/*.json como primeiro passo.
   Testes de estresse rodam em job separado e são bloqueadores.
   Calibração OMR = job manual (workflow_dispatch), sem fotos reais no CI automático.
   Badge de status no README.md.
3. Tarefas
   Criar .github/workflows/testes.yml (código na seção 5).
   Criar requirements-dev.txt (pytest + pytest-cov).
   Criar tests/conftest.py (fixture base_cfg).
   Criar tests/test_estresse.py (cenários da Seção 14).
   Criar tools/calibrar_omr.py — esqueleto que mede densidade de pixels de folhas de teste e sugere thresholds (usado só no job manual).
   Adicionar o badge de status no README.md.
   Fazer push e validar na aba Actions que todos os jobs passam.
   Registrar resultado no Status (seção 7).
4. Código de referência.github/workflows/testes.yml:

name: Testes Automatizados Karate-Ashi

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
        run: pytest tests/test_faixas.py -q --cov=core --cov-fail-under=80

  estresse:
    name: Testes de Estresse (Seção 14)
    runs-on: ubuntu-latest
    needs: validacao-config
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

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

      - name: Instalar dependências
        run: |
          pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Medir densidade das folhas de teste
        run: python tools/calibrar_omr.py --gabaritos data/gabaritos/teste/

`requirements-dev.txt`:

pytest>=7.4
pytest-cov>=4.1

`tests/conftest.py`:

"""Fixtures compartilhadas dos testes do Karate-Ashi."""
from pathlib import Path

import pytest

@pytest.fixture
def base_cfg() -> Path:
    """Caminho até a pasta config/ do repositório (Fases 00 e 06)."""
    return Path(__file__).resolve().parents[1] / "config"

`tests/test_estresse.py` (cenários da Seção 14; usar as funções reais de `core/engine.py`):

"""Testes de estresse do Karate-Ashi — Seção 14 da especificação v2.0."""
from pathlib import Path

import pytest

from core.engine import processa_aluno

def _avaliacao_vazia(aluno_id: str = "A01") -> list[dict]:
    """Três avaliadores SEM nenhuma marcação (categoria zerada)."""
    criterios = ["base_incorreta", "execucao_tecnica_incorreta",
                 "movimento_sem_carga", "falta_foco", "perda_equilibrio",
                 "ausencia_kiai"]
    freq = {c: 0 for c in criterios}
    return [
        {"avaliacoes": {q: {"frequencias": dict(freq), "observacao": ""}
                        for q in ["kihon", "kata", "bunkai", "kumite"]}}
        for _ in range(3)
    ]

def _avaliacao_saturada() -> list[dict]:
    """Todos os critérios com 7 marcações (saturação máxima)."""
    avaliacoes = _avaliacao_vazia()
    for av in avaliacoes:
        for q in av["avaliacoes"]:
            for chave in av["avaliacoes"][q]["frequencias"]:
                av["avaliacoes"][q]["frequencias"][chave] = 7
    return avaliacoes

def test_cenario_1_zero_faltas(base_cfg: Path):
    """Cenário 1: avaliação impecável deve dar 100,0 e APROVADO."""
    resultado = processa_aluno(_avaliacao_vazia(), base_cfg, "branca")
    assert resultado["nota_final"] == 100.0
    assert resultado["status"] == "APROVADO"

def test_cenario_2_saturacao_maxima(base_cfg: Path):
    """Cenário 2: saturação total deve zerar todos os quesitos."""
    resultado = processa_aluno(_avaliacao_saturada(), base_cfg, "branca")
    for q in ["kihon", "kata", "bunkai", "kumite"]:
        assert resultado["quesitos"][q]["nota"] == 0.0
    assert resultado["nota_final"] == 0.0
    assert resultado["status"] == "REPROVADO"

def _com_falta_controle(n_avaliadores_com_marcacao: int) -> list[dict]:
    """Banca de 3 com falta de controle em Kumite em N dos avaliadores."""
    base = _avaliacao_vazia()
    for i in range(3):
        if i < n_avaliadores_com_marcacao:
            base[i]["avaliacoes"]["kumite"]["frequencias"][
                "falta_controle"] = 1
    return base

def test_cenario_3_trava_consenso_total(base_cfg: Path):
    """3/3 marcaram falta de controle → teto de 10,0 no Kumite."""
    resultado = processa_aluno(_com_falta_controle(3), base_cfg, "branca")
    assert resultado["quesitos"]["kumite"]["nota"] == 10.0
    assert resultado["quesitos"]["kumite"]["alerta"] == "TRAVA_ATIVADA"

def test_cenario_3b_trava_parcial_alerta_etico(base_cfg: Path):
    """1/3 marcaram → NÃO trava; deve gerar ALERTA_ETICO."""
    resultado = processa_aluno(_com_falta_controle(1), base_cfg, "branca")
    assert resultado["quesitos"]["kumite"]["nota"] > 10.0
    assert resultado["quesitos"]["kumite"]["alerta"] == "ALERTA_ETICO"

def test_cenario_4_variacao_de_bancas(base_cfg: Path):
    """1, 2 e 3 avaliadores com o mesmo padrão → divisor N correto.

    Cada avaliador marca 2 em 'base_incorreta' no Kihon.
    fc esperado: 1 avaliador → 2,0 | 2 avaliadores → 2,0 | 3 → 2,0
    (ou seja: a MÉDIA é a mesma, pois o padrão é idêntico).
    """
    for n in [1, 2, 3]:
        avaliacoes = _avaliacao_vazia()[:n]
        for av in avaliacoes:
            av["avaliacoes"]["kihon"]["frequencias"]["base_incorreta"] = 2
        resultado = processa_aluno(avaliacoes, base_cfg, "branca")
        detalhe = resultado["quesitos"]["kihon"]["detalhes"]["base_incorreta"]
        assert detalhe["fc"] == 2.0, f"N={n}: fc={detalhe['fc']}"

`tools/calibrar_omr.py` (esqueleto — job manual):

"""tools/calibrar_omr.py — Mede densidade de pixels de folhas de teste.

Uso (job manual no GitHub Actions ou local):
    python tools/calibrar_omr.py --gabaritos data/gabaritos/teste/

Funcionalidade:

- Para cada imagem, aplica o pipeline OMR (correção de perspectiva);
- Para cada checkbox (coordenadas de config/coordenadas/<faixa></faixa>.json),
  mede a densidade de pixels escuros;
- Agrupa por classe conhecida (vazio/suspeito/marcado) e exibe a média
  e o desvio padrão, para calibrar os limiares de omr_thresholds.json.
  """
  from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from core.omr_reader import carregar_json, detectar_e_corrigir

def medir_densidade(imagem_path: Path, coordenadas: dict) -> list[float]:
    img = cv2.imread(str(imagem_path))
    if img is None:
        raise ValueError(f"imagem não abriu: {imagem_path}")
    alinhada = detectar_e_corrigir(img)
    densidades: list[float] = []
    for quesito, criterios in coordenadas.items():
        if not criterios:
            continue
        for chave, roi in criterios.items():
            x, y, w, h = (int(v) for v in roi.values())
            celula = alinhada[y:y + h, x:x + w]
            cinza = cv2.cvtColor(celula, cv2.COLOR_BGR2GRAY)
            _, binaria = cv2.threshold(
                cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            densidades.append(float(np.count_nonzero(binaria)) / binaria.size)
    return densidades

def main() -> int:
    ap = argparse.ArgumentParser(description="Calibração OMR Karate-Ashi")
    ap.add_argument("--gabaritos", type=Path, required=True,
                    help="pasta com as fotos/scan das folhas de teste")
    ap.add_argument("--faixa", default="branca")
    ap.add_argument("--config", type=Path, default=Path("config"))
    args = ap.parse_args()

    coordenadas = carregar_json(
        args.config / "coordenadas" / f"{args.faixa}.json")
    for img in sorted(args.gabaritos.glob("*.jpg")) +
              sorted(args.gabaritos.glob("*.png")):
        densidades = medir_densidade(img, coordenadas)
        if densidades:
            print(f"{img.name}: média {np.mean(densidades):.3f} | "
                  f"min {min(densidades):.3f} | max {max(densidades):.3f}")
        else:
            print(f"{img.name}: nenhuma ROI com coordenadas preenchidas")
    print("Use os valores medidos para ajustar "
          "config/omr_thresholds.json (Fase 03).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

**Badge no **`README.md` (adicionar no topo):

# Karate-Ashi

![Testes]([[https://github.com/seu_usuario<SEU_REPOSITORIO</a/actions/workflows/testes.yml/badge.svg&gt;&gt;)](](<%5Bhttps://github.com/seu_usuario%3C/%3CSEU_REPOSITORIO>)[https://github.com/%3CSEU_USUARIO](<https://github.com/%3CSEU_USUARIO>))

6. Critérios de aceite
   Workflow Testes Automatizados Karate-Ashi aparece na aba Actions do repositório.
   Roda automaticamente em push (main) e pull_request.
   validacao-config passa com todos os JSONs de config/ válidos.
   Todos os jobs de testes por fase passam, cada um com cobertura ≥ 80%.
   estresse passa com os 5 cenários (zero faltas, saturação, trava total, trava parcial, variação de bancas).
   Job calibracao-omr visível e executável manualmente (workflow_dispatch).
   Badge verde aparecendo no README.md.
   Execução local equivalente: pytest -q roda a suíte inteira sem erros.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
   Resumindo
   Fase 07 entrega o testes.yml com 4 jobs: validação de JSONs, testes por fase (cobertura ≥ 80%), estresse e calibração OMR manual.
   Ela não inventa testes: amarra os tests/ já definidos nas Fases 01–06 e adiciona test_estresse.py com os cenários da Seção 14.
   O requisito pendente da Fase 07 é criar tools/calibrar_omr.py (esqueleto incluso acima), usado apenas no job manual.


## 0.5. HERANÇA DA FASE ANTERIOR

- Fases 01–06 entregaram os módulos e os testes por fase (test_engine, test_parser, test_omr_validador, test_faixas, test_relatorios).
- processa_aluno já recebe faixa (Fase 06) — os testes de estresse usam essa assinatura.

## 8. ENTREGA PARA A PRÓXIMA FASE

- testes.yml (4 jobs), requirements-dev.txt, conftest.py, test_estresse.py, calibrar_omr.py → validam as Fases 01–06 antes da Fase 08.

## 9. RESUMO DA EXECUÇÃO

- Fase NÃO executada (pendente).
- Notas: badge do README com placeholder a corrigir (usar https://github.com/phsilva84/karateashi/actions/workflows/testes.yml/badge.svg); o helper _avaliacao_vazia cobre só os critérios de Kihon — considerar completar para exercitar embusen_incorreto e falta_combatividade.
