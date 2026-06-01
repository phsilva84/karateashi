import streamlit as st
import pandas as pd
from fpdf import FPDF
import zipfile
import io
import os
import json
from datetime import datetime

# Importações da engine – ajuste o caminho conforme necessário
from core.engine import calcular_resultados, identificar_tendencias, parse_exame_file

st.set_page_config(page_title="Sistema de Análise de Exames", layout="wide")
st.title("📊 Interface de Análise de Exames Laboratoriais")

# Garantir que a pasta output exista
os.makedirs("output", exist_ok=True)

uploaded_file = st.file_uploader("📁 Selecione um arquivo .txt de exame", type=["txt"])

if uploaded_file is not None:
    try:
        # Conteúdo bruto do upload (string)
        content = uploaded_file.getvalue().decode("utf-8")
        file_lines = content.splitlines()

        # 1. Parse do arquivo
        df = parse_exame_file(content)  # Espera-se que retorne um DataFrame
        if df is None or df.empty:
            st.error("Arquivo vazio ou formato não reconhecido.")
            st.stop()

        st.success(f"Arquivo processado: {len(df)} amostras encontradas.")

        # 2. Calcular resultados e tendências
        resultados = calcular_resultados(df)
        tendencias = identificar_tendencias(df)

        # 3. Exibir dados
        st.subheader("📋 Dados do Exame")
        st.dataframe(df, use_container_width=True)

        # 4. Gráficos – exemplo simples com bar_chart (variáveis numéricas)
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            st.subheader("📈 Tendências (Bar Chart)")
            st.bar_chart(df[numeric_cols])

        # 5. Salvar diagnóstico.json na output/
        diagnostico = {
            "data_processamento": datetime.now().isoformat(),
            "resultados": resultados,
            "tendencias": tendencias,
            "amostras": df.to_dict(orient="records")
        }
        json_path = os.path.join("output", "diagnostico.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(diagnostico, f, ensure_ascii=False, indent=2)
        st.info(f"📄 Diagnóstico salvo em `{json_path}`")

        # 6. Gerar PDF individual (resumo) e consolidado
        pdf_individual = FPDF()
        pdf_individual.add_page()
        pdf_individual.set_font("Arial", size=12)
        pdf_individual.cell(200, 10, txt="Relatório Individual de Exame", ln=True, align="C")
        pdf_individual.ln(10)
        for key, value in resultados.items():
            pdf_individual.cell(0, 10, txt=f"{key}: {value}", ln=True)

        # PDF consolidado com todos os dados
        pdf_consolidado = FPDF()
        pdf_consolidado.add_page()
        pdf_consolidado.set_font("Arial", size=12)
        pdf_consolidado.cell(200, 10, txt="Relatório Consolidado de Exames", ln=True, align="C")
        pdf_consolidado.ln(10)
        for idx, row in df.iterrows():
            linha = ", ".join([f"{col}: {row[col]}" for col in df.columns])
            pdf_consolidado.cell(0, 10, txt=f"Amostra {idx+1}: {linha}", ln=True)

        # 7. Botões de download
        # PDF Individual
        pdf_ind_bytes = pdf_individual.output(dest="S").encode("latin-1")
        st.download_button(
            label="📥 Baixar PDF Individual",
            data=pdf_ind_bytes,
            file_name="relatorio_individual.pdf",
            mime="application/pdf"
        )

        # PDF Consolidado
        pdf_con_bytes = pdf_consolidado.output(dest="S").encode("latin-1")
        st.download_button(
            label="📥 Baixar PDF Consolidado",
            data=pdf_con_bytes,
            file_name="relatorio_consolidado.pdf",
            mime="application/pdf"
        )

        # ZIP com todos os arquivos gerados (json + pdfs)
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("diagnostico.json", json.dumps(diagnostico, ensure_ascii=False, indent=2))
            zf.writestr("relatorio_individual.pdf", pdf_ind_bytes)
            zf.writestr("relatorio_consolidado.pdf", pdf_con_bytes)
        zip_buffer.seek(0)
        st.download_button(
            label="📦 Baixar ZIP (JSON + PDFs)",
            data=zip_buffer,
            file_name="analise_exames.zip",
            mime="application/zip"
        )

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        # Opcional: exibir traceback detalhado em modo debug
        import traceback
        st.error(traceback.format_exc())