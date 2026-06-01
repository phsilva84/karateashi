
# 🥋 Karate-Ashi v5.2 - Sistema de Avaliação Técnica

Este projeto automatiza o processamento de exames de Karatê, aplicando a **Tabela de Descontos v1.1**. Ele transforma dados brutos de avaliação em diagnósticos técnicos precisos e relatórios profissionais.

## 🚀 Arquitetura e Tecnologias

- **Engine:** Python 3.10+
- **Processamento:** Pandas (Deduplicação e Análise de Tendências)
- **Interface:** Streamlit (Dashboard Interativo)
- **Documentação:** ReportLab / FPDF2 (Geração de PDFs e ZIPs)

## 📁 Estrutura do Repositório

- `app.py`: Interface web interativa.
- `requirements.txt`: Dependências do projeto.
- `core/`: Lógica de cálculo e regras de negócio.
- `data/`: Amostras de arquivos .txt para teste.

## 🛠️ Como Executar

1. Instale as dependências: `pip install -r requirements.txt`
2. Execute o dashboard: `streamlit run app.py`
3. Faça o upload do arquivo de exame e baixe os relatórios.

## 📊 Regras de Negócio (v1.1)

- Base de 25.0 pontos por quesito (Kihon, Kata, Bunkai, Kumite).
- Teto de -10.0 para o código A10 no Kumite.
- Diagnóstico consolidado sem repetições de descrições.

---

*Desenvolvido para o Dojo Karate-Ashi.*
