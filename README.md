# 🥋 Sistema Karate-Ashi v2.1

Sistema de avaliação de exames de Karatê: leitura óptica (OMR) das folhas de avaliação, cálculo das notas pelo motor de regras e geração de relatórios visuais (HTML) em duas camadas — **Sensei** (por dojo) e **Master** (consolidado multi-dojo) — com distribuição automática para o Google Drive por sensei responsável.

## 🚀 Visão Geral

- **Entrada:** scans (flatbed, A4 paisagem, ~300–400 DPI) das folhas de avaliação com balões de frequência e QR codes (exame, avaliador, aluno/faixa).
- **Processamento:** ingestão OMR (busca local por balões + leitura de QR) → JSONs por folha → agregação por aluno (múltiplos avaliadores) → motor de cálculo.
- **Saída:** relatórios HTML autossuficientes (prontos para preview no Drive, impressão A4 e arquivamento) + JSONs estruturados.
- **Distribuição:** cópia automática para o Google Drive em pastas estáveis por nível de acesso (`master/` e `senseis/{Sensei}/`).

## 🔄 Fluxo de Funcionamento (Pipeline v2.1)

1. **Geração das folhas** — `tools/pre_exame.py` gera o PDF das folhas com balões, QRs e grade de observações (BOM! / A MELHORAR).
2. **Digitalização** — o dojo escaneia as folhas preenchidas (PNG, paisagem, 300–400 DPI).
3. **Ingestão OMR** — `tools/ingest_folhas.py` lê os scans e produz um JSON por folha (metadados, presença, frequências por quesito/critério, observações marcadas).
4. **Pipeline** — `core/pipeline.py` agrega as folhas por aluno, interpreta as frequências, chama o motor por faixa e gera os relatórios:
   - `output/relatorios/relatorio_sensei_{EXAME}_{DOJO}.html` (camada Sensei);
   - `output/relatorios/relatorio_master_{EXAME}.html` (master consolidado).
5. **Upload ao Google Drive** — os HTMLs são copiados para a estrutura de pastas por nível de acesso (ver seção abaixo).

> Um arquivo por exame — o sistema suporta vários exames no mesmo ano (`{EXAME}` no nome do arquivo).

## 🧱 Arquitetura e Estrutura de Diretórios

```text
config/
  dojos.json              # fonte da verdade dos dojos: id, nome, sensei responsável
  avaliadores.json        # mapa avaliador_id → nome (S02 → Sensei Fabio)
  faixas.json             # ordens de faixas: 'suportadas' (matriz v2.0) + 'placeholder'
  regras_gerais.json      # regras de aprovação/atenção/elogios
  recomendacoes.json      # recomendações por (quesito, critério): 'por_quesito' + legado na raiz
  observacoes*.json       # vocabulário oficial de observações (positivas / a melhorar / contradições)
  faixas/<faixa>.json     # matrizes por faixa (quesitos e critérios)
core/
  engine.py               # motor: processa_aluno, carregar_faixa, cálculo de nota por quesito
  pipeline.py             # orquestração OMR → engine → relatórios → Drive
  relatorio_html.py       # geradores de HTML (Sensei e Master)
  relatorios.py           # dados estruturados e funções de relatório (sensei/master + legadas)
  config.py               # carregamento de config e índices (faixas, quesitos)
  observacoes_automaticas.py  # observações derivadas das marcações
  nomes.py                # abreviação de nomes para as folhas
data/
  cadastro/alunos.csv     # cadastro: id,nome,faixa_atual,faixa_pretendida,dojo_id
  cadastro/alunos.json    # merge idempotente do cadastro (via tools/importar_cadastro.py)
output/
  omr/                    # JSONs por folha gerados pelo ingest
  relatorios/             # HTMLs gerados (Sensei + Master)
tools/
  pre_exame.py            # gera o PDF das folhas
  ingest_folhas.py        # lê os scans (OMR) e emite os JSONs
  importar_cadastro.py    # importa alunos de CSV
tests/                    # testes automatizados (engine, OMR, pipeline, relatórios)
.github/workflows/        # CI (validacao-config, testes, OMR, estresse)
```

## 📏 Regras de Negócio

### Composição de Nota

- O exame é dividido em 4 quesitos, cada um valendo **25.0 pontos**:
  **Kihon** | **Kata** | **Bunkai** | **Kumite**.
- **Nota máxima:** 100.0 · **Meta de aprovação:** >= 70.0.
- Cada quesito tem critérios com pesos padronizados (códigos técnicos A1–A12); a leitura óptica mapeia cada balão posicional para o critério N da matriz vigente da faixa.

### Semântica de Frequências

- **Notas (modo presença):** qualquer balão marcado conta como 1 ocorrência por critério — um avaliador contribui no máximo 1 por critério. Interpretação validada por testes.
- **Relatórios (modo real):** as frequências reais (escala 1 a 5) por critério e por avaliador são preservadas e usadas nos relatórios (tabela de marcações do Sensei e agregações do Master).

### Status Possíveis

- `APROVADO` — nota final >= aprovado_min (70.0);
- `APROVADO_PONTO_ATENCAO` — nota final **70.0–74.9** (regra de atenção v2.1, funciona mesmo com 1 avaliador) ou regra de discrepância entre avaliadores;
- `REPROVADO` — abaixo do mínimo;
- `AUSENTE` — presença não marcada na folha (nenhuma avaliação de frequências);
- `REVISAO_PENDENTE` — casos especiais.

### Consenso

- Avaliação oficial com **3 avaliadores**; a nota final é a consenso (média) das notas dos avaliadores. Com 3 avaliadores, divergências acionam a regra de revisão (discrepância > 3.0).

## 📊 Relatórios

### Sensei (por dojo/exame)

- Nota final, status, notas por quesito (mini-barras);
- **Tabela de marcações por quesito × avaliador** com o **nome do avaliador** (não o ID) — com 3 avaliadores, 3 colunas;
- **Observações por avaliador** separadas em **Pontos fortes (BOM!)** / **A melhorar** / **Outras**, com autoria;
- Bloco **Notas por Quesito** (ranking) com a coluna **Nova Faixa (se aprovado)** — próxima faixa da ordem configurada em `config/faixas.json`.

### Master (consolidado multi-dojo)

- **Desempenho por Dojo** (média, aprovação, presentes);
- **Notas por Quesito** (ranking por aluno);
- **Análise de Desempenho** — média por quesito, foco do treino, alunos em zona de atenção e destaque do exame;
- **Critérios Marcados por Quesito** (% de alunos por critério, sem coluna de intensidade);
- **Recomendações Sugeridas** por (quesito, critério) com os rótulos **Recomendação:** e **Planejamento Sugerido:** — textos distintos por quesito (ex.: Perda de Equilíbrio no Kihon ≠ no Kata), vindos de `config/recomendacoes.json["por_quesito"]`;
- **Observações dos Avaliadores** com nome e separação por tipo.

## ☁️ Distribuição no Google Drive

Após gerar, o pipeline copia os relatórios para pastas **estáveis** (permissão herdada do pai):

```text
G:\Meu Drive\documentos\KarateAshi_Exames\relatorios\
├── master\                        # acessível apenas aos mestres
│   └── {EXAME}\relatorio_master_{EXAME}.html
└── senseis\
    └── {Sensei}\                  # pasta por sensei responsável (config/dojos.json)
        └── {EXAME}\relatorio_sensei_{EXAME}_{DOJO}.html
```

- A **fronteira de permissão** fica nas pastas estáveis (`master/` e cada `senseis/{Sensei}/`): configure o compartilhamento **uma única vez** no Google Drive; os exames futuros caem dentro delas e herdam o acesso.
- Cada sensei enxerga **apenas** a pasta do seu dojo; os mestres acessam o consolidado.
- O script cria as subpastas automaticamente e faz **cópia** (os originais permanecem em `output/relatorios/`); o Drive precisa estar montado (ex.: `G:` no Windows).

## 🖥️ Como Executar

### Pré-requisitos

- Python 3.9+
- Dependências: `pip install -r requirements.txt`

### Pipeline completo (a partir dos JSONs já lidos)

```powershell
python core/pipeline.py --config config --data data --output output --pasta-omr output/omr
```

### Ingestão OMR (scans)

```powershell
python tools/ingest_folhas.py        # lê os scans e gera os JSONs em output/omr
python tools/importar_cadastro.py data/cadastro/alunos.csv   # cadastro de alunos
```

### Testes

```powershell
pytest
```

## 🧪 Qualidade

- **OMR:** busca local por balões (±3 mm), leitura de QR via pyzbar, normalização A4 3508×2480, limiares calibrados (marcado/vazio), presença ausente → AUSENTE;
- **CI:** GitHub Actions com jobs de validação de config, testes automatizados, OMR e estresse;
- **Regressão:** funções legadas de relatório mantidas por compatibilidade com os testes.

## 📌 Estado Atual e Próximos Passos

- [X] OMR com leitura por busca local e QR (validação com folha em branco e preenchida);
- [X] Pipeline v2.1 (OMR → engine → relatórios HTML → Drive por sensei);
- [X] Relatórios do Sensei com nomes de avaliadores, observações BOM!/A melhorar e Nova Faixa;
- [X] Relatório Master com recomendações por quesito e análise de desempenho;
- [ ] Cadastro dos demais dojos (mínimo 5) com sensei responsável em `config/dojos.json`;
- [ ] Validação do fluxo com os 3 avaliadores oficiais (3 colunas no Sensei e regra de discrepância);
- [ ] Matrizes das faixas marrom e preta (hoje em `placeholder` em `config/faixas.json`).
