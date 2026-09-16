
# FASE 06 — Estrutura Multi-Faixa (Branca a Azul + Placeholders)

## 0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE

Você atua como uma equipe de 3 especialistas:

- **Modelador de Dados** — JSON limpo, chaves consistentes, sem redundância; multi-arquivo por faixa.
- **Analista Pedagógico de Karatê** — domínio de Kihon, Kata, Bunkai e Kumite; entende a progressão de faixas.
- **Dev Python Sênior** — refatoração segura, compatibilidade com código existente, testes.

**Regras de conduta:**

- Preservar SEMPRE o motor híbrido progressivo já existente (`frequencia_media`, `multiplicador_progressivo`, `desconto_criterio`, `consenso_controle`, `trava_seguranca`).
- Nunca inventar pesos, critérios ou schemas de configuração — ler `regras_gerais.json` e `omr_thresholds.json` reais.
- As 5 faixas (Branca, Amarela, Laranja, Verde, Azul) compartilham a MESMA tabela v2.0.
- Roxa, Marrom e Preta entram como placeholders com `"nao_suportada": true`.
- Não reabrir decisões aprovadas. Se algo não estiver especificado, PERGUNTE.
- Ao final, preencher o checklist de aceite.

---

## 0.5. HERANÇA DA FASE ANTERIOR

- **Fase 00** — tabela de critérios (códigos A1–A12, pesos).
- **Fase 01** — engine sem faixa, motor híbrido progressivo funcional.
- **Fase 03** — OMR com coordenadas injetadas, leitura booleana (marcado/não marcado).

---

## 1. Objetivo

Estruturar o sistema para múltiplas faixas:

1. Criar `config/faixas/` com 5 arquivos de faixa (tabela v2.0) + 3 placeholders.
2. Criar `config/coordenadas/` com um template de layout por faixa (para o OMR e o pré-exame).
3. Atualizar `core/engine.py`, `core/parser.py` e `core/omr_reader.py` para receber o parâmetro `faixa`.

---

## 2. Contexto mínimo do projeto

- **Stack:** Python 3.9+, JSON, Regex, OpenCV, pytest.
- **Raiz:** `karateashi/` (Windows: `C:\Users\shpau\Downloads\karate\projeto avaliacao\karateashi`).
- **Configs existentes (não recriar):** `config/regras_gerais.json`, `config/omr_thresholds.json`, `config/criterios_por_quesito.json`.
- **Motor real:** modelo híbrido progressivo — ver Seção 5.1.
- **Entradas de teste:** `dados_avaliadores.txt` (dados reais, 3 senseis), `exame-matriz-30-05-26.txt`, `dados_template.txt`.

---

## 3. Decisões aprovadas (não reabrir)

| #  | Decisão                                                                                                                                                             |
| -- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1 | As 5 faixas Branca→Azul usam a MESMA tabela de critérios (v2.0). Arquivos idênticos, prontos para divergir no futuro.                                             |
| D2 | Layout específico por faixa: cada faixa tem seu`config/coordenadas/<faixa>.json`.                                                                                 |
| D3 | Roxa, Marrom e Preta: placeholders com`"nao_suportada": true`. Sistema avisa "faixa não suportada nesta versão".                                                 |
| D4 | **Folha em A4 PAISAGEM (2970×2100 px @ 10 px/mm)** — define a geometria do OMR e do pré-exame.                                                              |
| D5 | **7 caixas cumulativas por critério** (1 a 7 ocorrências) — a folha precisa expressar a frequência 0–7 que o motor consome.                               |
| D6 | **Coordenadas derivadas por código** a partir de `core/layout_folha.py`; PDF e OMR consomem o mesmo cálculo. Calibração manual deixa de ser necessária. |
| D7 | **Validação de acurácia do OMR fica para os testes de stress** — não bloqueia a Fase 06 nem a Fase 04.                                                    |
| D8 | `regras_gerais.json` e `omr_thresholds.json` são mantidos exatamente como estão (schemas reais na Seção 5.2).                                                |

---

## 4. Tarefas e status

| #  | Tarefa                                                                                  | Status                                            |
| -- | --------------------------------------------------------------------------------------- | ------------------------------------------------- |
| T1 | Criar`config/faixas/{branca,amarela,laranja,verde,azul}.json` (tabela v2.0 idêntica) | ✅                                                |
| T2 | Criar`config/faixas/{roxa,marrom,preta}.json` (placeholders)                          | ✅                                                |
| T3 | Criar`config/coordenadas/{branca,amarela,laranja,verde,azul}.json`                    | ✅ (regeradas em paisagem por`layout_folha.py`) |
| T4 | `core/engine.py`: `carregar_faixa` + `processa_aluno(..., faixa)`                 | ✅                                                |
| T5 | `core/parser.py`: validar linha FAIXA do TXT                                          | ✅                                                |
| T6 | `core/omr_reader.py`: carregar coordenadas por faixa + validação cruzada com QR     | ✅                                                |
| T7 | Criar e executar`tests/test_faixas.py`                                                | ✅ 13 testes                                      |
| T8 | Validação de acurácia OMR (gabarito/fantasma)                                        | ⏳ adiada para testes de stress (D7)              |

---

## 5. Conteúdo dos arquivos

### 5.1 `core/engine.py` — VERSÃO CORRETA (motor híbrido + multi-faixa)

> **ATENÇÃO:** a versão anterior deste manifesto documentava um cálculo de "soma dos pesos dos códigos" e um `regras_gerais.json` inexistente. Isso estava errado e foi descartado. O motor real abaixo é o híbrido progressivo, preservado integralmente.

```python
"""core/engine.py — Motor de cálculo do Karate-Ashi v2.0.

Modelo híbrido progressivo:
- frequência média por critério (média das marcações dos avaliadores);
- multiplicador progressivo por faixa de frequência;
- desconto = fc * peso * multiplicador;
- nota do quesito = max(0; 25 - soma dos descontos);
- trava de segurança por consenso (Bunkai/Kumite);
- nota final e status.

Fase 06 — multi-faixa:
- a tabela de critérios passa a vir de config/faixas/<faixa>.json;
- roxa, marrom e preta são placeholders (nao_suportada: true);
- processa_aluno passa a receber o parâmetro `faixa`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOTA_MAX_QUESITO = 25.0
FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]

def carregar_json(caminho: Path) -> dict:
    """Lê um JSON de configuração. Falha com mensagem clara se inválido."""
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Configuração não encontrada: {caminho}") from exc
    except json.

JSONDecodeError as exc:
        raise ValueError(f"JSON inválido em {caminho}: {exc}") from exc

def carregar_faixa(base_cfg: Path, faixa: str) -> dict:
    """Carrega a tabela de critérios da faixa (config/faixas/<faixa>.json).

    Devolve o dict de quesitos. Levanta ValueError se o arquivo não existir
    ou se a faixa for placeholder (nao_suportada: true).
    """
    faixa = str(faixa or "").strip().lower()
    caminho = base_cfg / "faixas" / f"{faixa}.json"
    if not caminho.exists():
        raise ValueError(f"faixa '{faixa}' não possui arquivo de configuração")

    cfg = carregar_json(caminho)

    if cfg.get("nao_suportada", False):
        raise ValueError(
            f"faixa '{faixa}' não suportada nesta versão "
            f"(Roxa/Marrom/Preta) — sem processamento"
        )
    return cfg["quesitos"]

def frequencia_media(marcacoes: list[int]) -> float:
    """Média simples das marcações (0 a 7) dos avaliadores presentes."""
    n = len(marcacoes)
    if n == 0:
        return 0.0
    return sum(marcacoes) / n

def multiplicador_progressivo(fc: float, faixas: list[dict]) -> float:
    """Retorna o multiplicador correspondente à faixa de fc."""
    for faixa in faixas:
        if faixa["fc_min"] <= fc <= faixa["fc_max"]:
            return faixa["multiplicador"]
    return 0.0  # fc == 0 ou fora das faixas

def desconto_criterio(fc: float, peso: float, mult: float) -> float:
    """Desconto do critério: fc * |peso| * multiplicador (2 casas)."""
    return round(fc * abs(peso) * mult, 2)

def consenso_controle(marcacoes_controle: list[int]) -> bool:
    """True quando TODOS os avaliadores presentes marcaram >= 1 ocorrência."""
    n = len(marcacoes_controle)
    if n == 0:
        return False
    return all(m >= 1 for m in marcacoes_controle)

def nota_quesito(avaliacoes: list[dict], quesito: str,
                 criterios_q: list[dict], regras: dict) -> dict:
    """Consolida um quesito entre avaliadores e devolve nota + detalhes."""
    total_desconto = 0.0
    detalhes: dict[str, Any] = {}
    controles: list[int] = []
    trava = regras["trava_seguranca"]

    for criterio in criterios_q:
        chave = criterio["chave"]
        marcacoes = [av["avaliacoes"][quesito]["frequencias"].get(chave, 0)
                     for av in avaliacoes]
        fc = frequencia_media(marcacoes)
        mult = multiplicador_progressivo(fc, regras["progressivo"])
        desc = desconto_criterio(fc, criterio["peso"], mult)
        total_desconto += desc
        detalhes[chave] = {
            "nome": criterio["nome"],
            "peso": criterio["peso"],
            "marcacoes": marcacoes,
            "fc": round(fc, 2),
            "multiplicador": mult,
            "desconto": desc,
        }
        if chave == trava["criterio"]:
            controles = marcacoes

    nota = round(max(0.0, NOTA_MAX_QUESITO - total_desconto), 2)

    if quesito in trava["quesitos"] and consenso_controle(controles):
        nota = min(nota, trava["teto"])
        alerta = "TRAVA_ATIVADA"
    elif quesito in trava["quesitos"] and any(m >= 1 for m in controles):
        alerta = "ALERTA_ETICO"
    else:
        alerta = None

    return {
        "quesito": quesito,
        "nota": nota,
        "desconto_total": round(total_desconto, 2),
        "detalhes": detalhes,
        "alerta": alerta,
        "controle_marcacoes": controles,
    }

def classificar_status(nota_final: float, regras: dict) -> str:
    """Classifica a nota final segundo as faixas da configuração."""
    if nota_final >= regras["status"]["aprovado_min"]:
        return "APROVADO"
    if nota_final >= regras["status"]["recuperacao_min"]:
        return "RECUPERACAO"
    return "REPROVADO"

def processa_aluno(avaliacoes: list[dict], base_cfg: Path, faixa: str) -> dict:
    """Recebe os JSONs de cada avaliador e devolve o resultado do aluno.

    avaliacoes: lista com um dict por avaliador, no schema v2.0:
      {"avaliacoes": {"kihon": {"frequencias": {...}, "observacao": "..."}, ...}}

    Fase 06: a tabela de critérios vem de config/faixas/<faixa>.json.
    """
    quesitos_cfg = carregar_faixa(base_cfg, faixa)
    regras = carregar_json(base_cfg / "regras_gerais.json")

    resultados = {}
    soma = 0.0
    for quesito in QUESTOS_ORDEM:
        r = nota_quesito(avaliacoes, quesito,
                         quesitos_cfg[quesito]["criterios"], regras)
        resultados[quesito] = r
        soma += r["nota"]

    nota_final = round(soma, 1)
    return {
        "nota_final": nota_final,
        "status": classificar_status(nota_final, regras),
        "quesitos": resultados,
        "faixa": faixa,
    }
```
