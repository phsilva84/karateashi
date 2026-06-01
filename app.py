import streamlit as st
import json
import os
import tempfile
from pathlib import Path
from fpdf import FPDF
from core.engine import calcular_resultados, identificar_tendencias

# Configuração da página
st.set_page_config(page_title="Analisador de Texto", layout="centered")

# Cria o diretório de saída se não existir
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

st.title("📄 Analisador de Texto")
st.markdown("Faça upload de um arquivo `.txt` para análise e geração de relatório.")

uploaded_file = st.file_uploader("Escolha um arquivo .txt", type="txt")

if uploaded_file is not None:
    # Lê o conteúdo do arquivo
    texto = uploaded_file.read().decode("utf-8")

    with st.spinner("Processando..."):
        try:
            # Executa as funções do core
            resultados = calcular_resultados(texto)
            tendencias = identificar_tendencia(resultados)  # ajuste conforme a assinatura real

            # Dicionário consolidado para o JSON
            dados_completos = {
                "nome_arquivo": uploaded_file.name,
                "tamanho": len(texto),
                "resultados": resultados,
                "tendencias": tendencias
            }

            # Salva diagnóstico em JSON
            json_path = OUTPUT_DIR / "diagnostico.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(dados_completos, f, indent=2, ensure_ascii=False)

            # Gera PDF com resumo
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, text="Resumo da Análise", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(10)

            # Adiciona conteúdo ao PDF
            pdf.multi_cell(0, 10, f"Arquivo: {uploaded_file.name}")
            pdf.multi_cell(0, 10, f"Tamanho: {len(texto)} caracteres")
            pdf.ln(5)
            pdf.multi_cell(0, 10, "Resultados:")
            for chave, valor in resultados.items():
                pdf.multi_cell(0, 8, f"  {chave}: {valor}")
            pdf.ln(5)
            pdf.multi_cell(0, 10, "Tendências:")
            pdf.multi_cell(0, 8, str(tendencias))

            pdf_path = OUTPUT_DIR / "resumo.pdf"
            pdf.output(str(pdf_path))

            st.success("Processamento concluído!")

            # Botões de download
            with open(json_path, "rb") as f:
                st.download_button(
                    label="📥 Baixar JSON (diagnóstico)",
                    data=f,
                    file_name="diagnostico.json",
                    mime="application/json"
                )

            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="📥 Baixar PDF (resumo)",
                    data=f,
                    file_name="resumo.pdf",
                    mime="application/pdf"
                )

        except Exception as e:
            st.error(f"Erro ao processar: {e}")

else:
    st.info("Aguardando upload de arquivo ...")