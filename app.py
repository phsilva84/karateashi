import os
import json
import zipfile
import tempfile
from io import BytesIO

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from fpdf import FPDF

from core.engine import calcular_resultados, identificar_tendencias

# -------------------------------------------------------------------
# Configuração das pastas de saída
# -------------------------------------------------------------------
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Função auxiliar: ler arquivo .txt com detecção de delimitador
# -------------------------------------------------------------------
def _detect_delimiter(file_path):
    with open(file_path, 'r') as f:
        first_line = f.readline()
        if '\t' in first_line:
            return '\t'
        # Falling back to comma if no tab found
        return ','

def processar_dados(uploaded_file):
    """
    Lê um arquivo .txt (ou .csv) e retorna um DataFrame.
    Suporta delimitadores vírgula e tabulação.
    """
    # Salva temporariamente o arquivo para leitura
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    try:
        delimiter = _detect_delimiter(tmp_path)
        df = pd.read_csv(tmp_path, delimiter=delimiter)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None
    finally:
        os.unlink(tmp_path)  # Remove temporário

    return df

# -------------------------------------------------------------------
# Função principal de processamento (chamada pela UI)
# -------------------------------------------------------------------
def processar_completo(df, nome_base):
    """
    Executa a análise usando as funções do core/engine.py
    e gera os arquivos de saída.
    """
    try:
        # Utiliza as funções da engine (Tabela v1.1)
        resultados = calcular_resultados(df)
        tendencias = identificar_tendencias(df)

        # Combina tudo para o JSON de diagnóstico
        diagnostico = {
            "resultados": resultados,
            "tendencias": tendencias,
            "metadados": {
                "arquivo": nome_base,
                "registros": len(df),
                "colunas": list(df.columns)
            }
        }

        # Salva diagnostico.json
        json_path = os.path.join(OUTPUT_DIR, f"diagnostico_{nome_base}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(diagnostico, f, ensure_ascii=False, indent=2)

        return diagnostico, json_path

    except Exception as e:
        st.error(f"Erro ao processar com a engine: {e}")
        return None, None

# -------------------------------------------------------------------
# Funções auxiliares para geração de PDF/ZIP
# -------------------------------------------------------------------
def gerar_pdf(diagnostico, nome_base):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, text=f"Diagnóstico - {nome_base}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    # Escreve resultados
    pdf.set_font("Arial", size=10)
    resultados = diagnostico.get("resultados", {})
    for chave, valor in resultados.items():
        pdf.cell(0, 8, text=f"{chave}: {valor}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.set_font("Arial", style="B", size=10)
    pdf.cell(0, 8, text="Tendências:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Arial", size=10)
    tendencias = diagnostico.get("tendencias", "")
    pdf.multi_cell(0, 8, text=str(tendencias))

    # Salva em bytes
    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    return pdf_bytes

def gerar_zip(pdf_bytes, json_path):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        zf.writestr("relatorio.pdf", pdf_bytes)
        with open(json_path, 'rb') as jf:
            zf.writestr(os.path.basename(json_path), jf.read())
    buffer.seek(0)
    return buffer

# -------------------------------------------------------------------
# Interface Streamlit
# -------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Analisador de Dados v1.1", layout="wide")
    st.title("Analisador de Dados (Tabela v1.1)")

    uploaded_file = st.file_uploader("Selecione um arquivo .txt ou .csv", type=["txt", "csv"])

    if uploaded_file is not None:
        df = processar_dados(uploaded_file)
        if df is None:
            return

        st.success("Arquivo carregado com sucesso!")
        st.dataframe(df.head())

        if st.button("Processar Dados"):
            nome_base = os.path.splitext(uploaded_file.name)[0]
            diagnostico, json_path = processar_completo(df, nome_base)

            if diagnostico is None:
                return

            st.success("Processamento concluído!")
            st.json(diagnostico)

            # Exibe gráficos simples
            st.subheader("Gráficos")
            numeric_cols = df.select_dtypes(include='number').columns.tolist()
            if numeric_cols:
                col = st.selectbox("Selecione coluna para histograma", numeric_cols)
                fig, ax = plt.subplots()
                df[col].hist(ax=ax, bins=20, edgecolor='black')
                ax.set_title(f"Distribuição de {col}")
                st.pyplot(fig)
            else:
                st.info("Nenhuma coluna numérica disponível para gráficos.")

            # Geração de PDF e ZIP
            pdf_bytes = gerar_pdf(diagnostico, nome_base)
            zip_buffer = gerar_zip(pdf_bytes, json_path)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"diagnostico_{nome_base}.pdf",
                    mime="application/pdf"
                )
            with col2:
                st.download_button(
                    label="📦 Baixar ZIP (PDF + JSON)",
                    data=zip_buffer,
                    file_name=f"diagnostico_{nome_base}.zip",
                    mime="application/zip"
                )

    else:
        st.info("Por favor, faça upload de um arquivo.")

if __name__ == "__main__":
    main()