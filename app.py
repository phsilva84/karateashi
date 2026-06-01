import streamlit as st
import pandas as pd
import io
import zipfile
from fpdf import FPDF
from pathlib import Path

# ------------------------------------------------------------
# Funções auxiliares (simulam a lógica Karate-Ashi v5.2)
# ------------------------------------------------------------
def processar_dados(uploaded_file):
    """Lê o arquivo .txt e retorna um DataFrame com dados dos alunos."""
    # Formato esperado: primeira linha = cabeçalho (Nome,quesito1,quesito2,...)
    # Demais linhas = dados de cada aluno
    df = pd.read_csv(uploaded_file, sep=',', encoding='utf-8')
    # Renomeia primeira coluna para 'Aluno' se necessário
    if df.columns[0] != 'Aluno':
        df.rename(columns={df.columns[0]: 'Aluno'}, inplace=True)
    return df

def calcular_medias(df):
    """Calcula média por aluno e por quesito."""
    medias_alunos = df.set_index('Aluno').mean(axis=1).reset_index()
    medias_alunos.columns = ['Aluno', 'Média']
    medias_quesitos = df.drop(columns=['Aluno']).mean().reset_index()
    medias_quesitos.columns = ['Quesito', 'Média']
    return medias_alunos, medias_quesitos

def gerar_pdf_individual(aluno, medias_por_quesito, df_aluno):
    """Gera um PDF individual para o aluno."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Relatório Individual - {aluno}", ln=True, align='C')
    pdf.ln(10)
    for idx, row in df_aluno.iterrows():
        pdf.cell(200, 10, txt=f"{row['Quesito']}: {row['Nota']}", ln=True)
    pdf.ln(5)
    pdf.cell(200, 10, txt=f"Média Geral: {medias_por_quesito[aluno]:.2f}", ln=True)
    return pdf.output(dest='S').encode('latin1')  # retorna bytes

def gerar_pdfs_zip(df_original, medias_alunos):
    """Gera um ZIP contendo PDFs individuais de todos os alunos."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for aluno in df_original['Aluno']:
            df_aluno = df_original[df_original['Aluno'] == aluno].melt(
                id_vars=['Aluno'], var_name='Quesito', value_name='Nota'
            )
            pdf_bytes = gerar_pdf_individual(aluno, medias_alunos.set_index('Aluno')['Média'].to_dict(), df_aluno)
            zf.writestr(f"{aluno}.pdf", pdf_bytes)
    zip_buffer.seek(0)
    return zip_buffer.read()

def gerar_relatorio_consolidado(df_original, medias_alunos, medias_quesitos):
    """Gera PDF consolidado com todas as médias."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16, style='B')
    pdf.cell(200, 10, txt="Relatório Consolidado - Karate-Ashi", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Médias dos Alunos:", ln=True)
    for _, row in medias_alunos.iterrows():
        pdf.cell(200, 10, txt=f"{row['Aluno']}: {row['Média']:.2f}", ln=True)
    pdf.ln(10)
    pdf.cell(200, 10, txt="Médias por Quesito:", ln=True)
    for _, row in medias_quesitos.iterrows():
        pdf.cell(200, 10, txt=f"{row['Quesito']}: {row['Média']:.2f}", ln=True)
    return pdf.output(dest='S').encode('latin1')

def diagnosticar_dojo(medias_quesitos, limite=7.0):
    """Identifica quesitos com média abaixo do limite (falhas recorrentes)."""
    falhas = medias_quesitos[medias_quesitos['Média'] < limite]
    return falhas

# ------------------------------------------------------------
# Aplicação Streamlit
# ------------------------------------------------------------
def main():
    st.set_page_config(page_title="Karate-Ashi v5.2", layout="wide")
    st.title("🥋 Karate-Ashi v5.2 - Processamento e Análise")

    uploaded_file = st.file_uploader("Faça o upload do arquivo .txt com os dados", type="txt")

    if uploaded_file is not None:
        # Processar dados
        try:
            df = processar_dados(uploaded_file)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo. Certifique-se de que é um CSV separado por vírgulas. Detalhes: {e}")
            return

        st.success("Arquivo carregado e processado com sucesso!")
        st.subheader("Dados brutos")
        st.dataframe(df)

        # Calcular médias
        medias_alunos, medias_quesitos = calcular_medias(df)

        # Tabela interativa com médias dos alunos
        st.subheader("📊 Médias dos Alunos")
        st.dataframe(medias_alunos)

        # Gráfico de barras com desempenho por quesito
        st.subheader("📈 Desempenho por Quesito")
        chart_data = medias_quesitos.set_index('Quesito')
        st.bar_chart(chart_data, use_container_width=True)

        # Diagnóstico do Dojo
        st.subheader("🔍 Diagnóstico do Dojo (Falhas Recorrentes)")
        falhas = diagnosticar_dojo(medias_quesitos, limite=7.0)
        if falhas.empty:
            st.info("Nenhuma falha recorrente detectada (todos os quesitos acima de 7.0).")
        else:
            st.error(f"Foram encontradas {len(falhas)} falhas recorrentes:")
            st.dataframe(falhas)
            # Mostrar visualmente com bar chart
            st.bar_chart(falhas.set_index('Quesito'), use_container_width=True)

        # Botões de download
        col1, col2 = st.columns(2)
        with col1:
            # ZIP de PDFs individuais
            zip_bytes = gerar_pdfs_zip(df, medias_alunos)
            st.download_button(
                label="📥 Baixar ZIP com PDFs Individuais",
                data=zip_bytes,
                file_name="individual_pdfs.zip",
                mime="application/zip"
            )
        with col2:
            # PDF Consolidado
            pdf_bytes = gerar_relatorio_consolidado(df, medias_alunos, medias_quesitos)
            st.download_button(
                label="📄 Baixar Relatório Consolidado (PDF)",
                data=pdf_bytes,
                file_name="relatorio_consolidado.pdf",
                mime="application/pdf"
            )

if __name__ == "__main__":
    main()