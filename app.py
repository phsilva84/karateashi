import streamlit as st
from engine import process_document, extract_data  # assume these exist
from fpdf import FPDF
import json
import io

st.set_page_config(page_title="Document Processor", layout="wide")

st.title("📄 Document Upload & Processing")

if "results" not in st.session_state:
    st.session_state.results = None

uploaded_file = st.file_uploader(
    "Choose a file", type=["pdf", "docx", "txt", "png", "jpg"]
)

if uploaded_file is not None:
    with st.spinner("Processing..."):
        try:
            extracted = process_document(uploaded_file)
            data = extract_data(extracted)
            st.session_state.results = data
            st.success("Processing complete!")
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

if st.session_state.results:
    data = st.session_state.results

    st.subheader("Extracted Data")
    st.json(data)

    col1, col2 = st.columns(2)

    # Generate PDF
    with col1:
        if st.button("Generate PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            for key, value in data.items():
                pdf.cell(0, 10, f"{key}: {value}", ln=True)
            pdf_output = io.BytesIO()
            pdf.output(pdf_output)
            pdf_output.seek(0)
            st.download_button(
                label="Download PDF",
                data=pdf_output,
                file_name="results.pdf",
                mime="application/pdf",
            )

    # Generate JSON
    with col2:
        if st.button("Generate JSON"):
            json_output = json.dumps(data, indent=4, ensure_ascii=False)
            st.download_button(
                label="Download JSON",
                data=json_output,
                file_name="results.json",
                mime="application/json",
            )