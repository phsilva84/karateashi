# 🥋 Sistema Karate-Ashi v1.1.8

Sistema de Processamento, Análise Técnica e Observabilidade Pedagógica para Exames de Karatê.

## 🚀 Visão Geral

O Karate-Ashi é um motor de processamento de dados desenvolvido em Python para transformar avaliações brutas de Senseis em relatórios estratégicos. O sistema adota princípios de **SRE (Site Reliability Engineering)**, garantindo idempotência, integridade de dados e uma interface de saída otimizada para dispositivos móveis via Telegram.

## 🛠️ Arquitetura Técnica

- **Linguagem:** Python 3.10+
- **Parser:** Baseado em Expressões Regulares (Regex) com controle de estado para múltiplos avaliadores.
- **CI/CD:** GitHub Actions para automação de pipeline.
- **Cloud Storage:** Sincronização via Rclone com Google Drive (Idempotência garantida).
- **Notificação:** Integração com Telegram Bot API (Envio de documentos TXT).
- **Encoding:** Saída em `utf-8-sig` para compatibilidade total com Excel e Google Sheets.

## 🔄 Fluxo de Funcionamento (Pipeline)

1. **Ingestão:** O usuário faz o upload do arquivo `exame-dojo-DATA.txt` na pasta `data/`.
2. **Trigger:** O GitHub Actions detecta o push e inicia o pipeline.
3. **Sincronização (Idempotência):** O `rclone` baixa os relatórios existentes do Google Drive para a pasta `output/`.
4. **Processamento (Engine):**
   - O `parser.py` lê o arquivo, identifica Senseis, Alunos e Observações.
   - O `calculator.py` processa as notas individuais e gera as métricas de grupo (N/Total).
   - Se um relatório Master para aquela data já existir em `output/`, o motor dá **SKIP** no arquivo para evitar reprocessamento.
5. **Geração de Artefatos:**
   - `relatorio_consolidado_*.json`: Dados estruturados para histórico e BI.
   - `relatorio_master_dojo_*.txt`: Relatório formatado para leitura humana (Telegram).
6. **Distribuição:**
   - O `rclone` sobe os novos relatórios para o Google Drive.
   - O script de notificação envia o Relatório Master para o grupo do Telegram.
7. **Finalização:** O arquivo original é movido para `data/processed/`.

## 📏 Lógica de Cálculo e Regras de Negócio

### 1. Composição de Nota

O exame é dividido em 4 categorias, cada uma valendo **25.0 pontos**:

- **Kihon** | **Kata** | **Bunkai** | **Kumite**
- **Nota Máxima:** 100.0 | **Meta de Aprovação:** >= 70.0

### 2. Lógica de Quórum e Consenso

O sistema é projetado para lidar com variabilidade no número de avaliadores:

- **Quórum de 1 Avaliador:** A nota final do aluno é a nota absoluta atribuída por ele.
- **Quórum de 2 ou 3 Avaliadores:** A nota final é a **média aritmética** das notas de todos os avaliadores ativos para aquele aluno.
- **Consenso Pedagógico (Regra de Ouro):** Uma Recomendação Pedagógica de grupo só é gerada se **100% dos avaliadores** que avaliaram o aluno concordarem com a mesma falha (mesmo código) para aquele aluno específico. Isso evita que uma percepção isolada de um Sensei distorça o diagnóstico coletivo do Dojo.

### 3. Regra Crítica A10 (Teto de Segurança)

Se o código **A10 (Falta de Controle)** for apontado em qualquer categoria, a nota daquela categoria é automaticamente limitada ao teto de **10.0**, independente de outros acertos. Esta regra prioriza a integridade física dos praticantes.

## 📋 Tabela de Recomendações Pedagógicas (v1.5)

As recomendações são direcionadas ao **Sensei**, transformando erros em planos de ação.

|     Cód     | Falha Detectada       | Peso | Threshold | Recomendação ao Sensei                                             |
| :-----------: | :-------------------- | :--: | :-------: | :------------------------------------------------------------------- |
| **A1** | Base Incorreta        | 1.0 |    30%    | Priorizar exercícios de fixação de base e distribuição de peso. |
| **A2** | Execução Técnica   | 1.0 |    30%    | Revisar trajetórias e rotação de quadril/punho.                   |
| **A3** | Movimento sem Carga   | 1.0 |    30%    | Trabalhar explosão final e ativação abdominal em grupo.           |
| **A4** | Ausência de Kiai     | 0.5 |    30%    | Cobrar intensidade na expiração e uso do Kiai.                     |
| **A5** | Embusen Incorreto     | 2.0 |    30%    | Revisar trajeto dos Katas (Embusen) e pontos de retorno.             |
| **A6** | Falta de Foco         | 1.0 |    30%    | Implementar treinos de atenção visual e olhar fixo.                |
| **A7** | Perda de Equilíbrio  | 1.0 |    30%    | Focar em fortalecimento de pernas e estabilidade.                    |
| **A8** | Falta de Ritmo        | 0.5 |    30%    | Treinar cadência, alternando velocidade e controle.                 |
| **A9** | Defesa Incompleta     | 1.0 |    30%    | Reforçar cobertura total e preparo do contra-ataque.                |
| **A10** | Falta de Controle     | 2.5 |    30%    | Monitorar rigorosamente a potência e segurança.                    |
| **A11** | Distância Inadequada | 1.0 |    30%    | Praticar noção de distância relativa no Kumite.                   |
| **A12** | Rigidez Muscular      | 0.5 |    30%    | Introduzir rotinas de soltura e respiração diafragmática.         |

## 📊 Padrão de Observabilidade (Relatórios)

- **Zero Emojis:** Texto puro para evitar erros de encoding no Telegram.
- **Espaçamento SRE:** Linhas duplas entre alunos para legibilidade mobile.
- **Tradução In-line:** Exibe `[A1 - Base Incorreta] 5x` no bloco do aluno.
- **Comparativo de Meta:** Exibe `[Meta: 70.0]` ao lado da nota individual.
- **Destaques Hierárquicos:** Classificação em EXCELÊNCIA (100%), DESTAQUE (85%+) e FORÇA (75%+).
