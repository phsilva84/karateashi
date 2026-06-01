import streamlit as st
import json
import os
import io
import zipfile
from pathlib import Path
from fpdf import FPDF
from core.engine import calcular_resultados, identificar_tendencias

# Configuração da página
st.set_page_config(page_title="Analisador de Dados", layout="wide")
st.title("📊 Analisador de Dados")
st.markdown("Faça upload de um arquivo para processar e gerar relatórios.")

# Criação da pasta de saída (output/) se não existir
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Upload do arquivo
uploaded_file = st.file_uploader("Escolha um arquivo", type=["csv", "xlsx", "json"])

if uploaded_file is not None:
    # Botão para processar
    if st.button("Processar Arquivo"):
        with st.spinner("Processando..."):
            try:
                # Salvar temporariamente o arquivo para processamento
                file_path = OUTPUT_DIR / uploaded_file.name
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Chamar as funções do core.engine
                resultados = calcular_resultados(file_path)
                tendencias = identificar_tendencias(file_path)

                # Montar diagnóstico
                diagnostico = {
                    "resultados": resultados,
                    "tendencias": tendencias
                }

                # Salvar diagnostico.json na pasta output/
                diagnostico_path = OUTPUT_DIR / "diagnostico.json"
                with open(diagnostico_path, "w") as f:
                    json.dump(diagnostico, f, indent=4, ensure_ascii=False)

                st.success("Diagnóstico salvo em output/diagnostico.json")

                # --- Geração de PDFs usando fpdf2 ---

                # PDF consolidado
                pdf_consolidado = FPDF()
                pdf_consolidado.add_page()
                pdf_consolidado.set_font("Arial", size=12)
                pdf_consolidado.cell(200, 10, text="Relatório Consolidado", new_x="LMARGIN", new_y="NEXT", align="C")

                # Adicionar conteúdo do diagnóstico no PDF consolidado
                for chave, valor in diagnostico.items():
                    pdf_consolidado.set_font("Arial", size=10, style="B")
                    pdf_consolidado.cell(200, 10, text=chave.upper(), new_x="LMARGIN", new_y="NEXT")
                    pdf_consolidado.set_font("Arial", size=10)
                    pdf_consolidado.multi_cell(0, 10, text=str(valor))
                    pdf_consolidado.ln(5)

                # Salvar PDF consolidado em bytes
                pdf_bytes_consolidado = pdf_consolidado.output(dest="S").encode("latin-1")

                # PDFs individuais (um para cada seção do diagnóstico)
                pdfs_individuais = {}
                for secao, dados in diagnostico.items():
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", size=12)
                    pdf.cell(200, 10, text=f"Relatório: {secao}", new_x="LMARGIN", new_y="NEXT", align="C")
                    pdf.set_font("Arial", size=10)
                    pdf.multi_cell(0, 10, text=str(dados))
                    pdf_bytes = pdf.output(dest="S").encode("latin-1")
                    pdfs_individuais[secao] = pdf_bytes

                # --- Criar arquivo ZIP com todos os PDFs ---
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Adicionar PDF consolidado
                    zf.writestr("relatorio_consolidado.pdf", pdf_bytes_consolidado)
                    # Adicionar PDFs individuais
                    for nome, bytes_pdf in pdfs_individuais.items():
                        zf.writestr(f"relatorio_{nome}.pdf", bytes_pdf)

                zip_buffer.seek(0)

                # --- Botões de download ---
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        label="📥 Baixar PDF Consolidado",
                        data=pdf_bytes_consolidado,
                        file_name="relatorio_consolidado.pdf",
                        mime="application/pdf"
                    )
                with col2:
                    st.download_button(
                        label="📦 Baixar ZIP com todos os PDFs",
                        data=zip_buffer,
                        file_name="relatorios.zip",
                        mime="application/zip"
                    )

                # Limpeza do arquivo temporário (opcional)
                file_path.unlink()

            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")

else:
    st.info("Aguardando upload de arquivo.")