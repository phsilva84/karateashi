"""diagnostico_marcacoes.py — Mostra o que o OMR enxergou em cada folha.

Uso: python tools/diagnostico_marcacoes.py
"""
import json
import sys
from pathlib import Path

# Bootstrap: garante que a raiz do projeto esteja no caminho de busca,
# para o 'core' ser importável mesmo rodando de dentro de tools/.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.omr_reader import processar_imagem  # noqa: E402

pasta = Path("output/scans")
tmp = Path("output/_ingest")
tmp.mkdir(parents=True, exist_ok=True)

for pf in sorted(pasta.glob("*.pdf")):
    print(f"\n=== {pf.name} ===")
    try:
        # 1. Expande o PDF para PNG (como o ingest_folhas faz)
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pf))
        paginas = []
        for i in range(len(pdf)):
            bitmap = pdf[i].render(scale=300 / 72)
            saida = tmp / f"{pf.stem}_p{i + 1}.png"
            bitmap.to_pil().save(saida)
            paginas.append(saida)
        pdf.close()

        # 2. Processa cada página
        for pagina in paginas:
            print(f"  -- página {pagina.name} --")
            try:
                dados = processar_imagem(pagina, Path("config"), faixa="branca")
                for q, av in dados.get("avaliacoes", {}).items():
                    marcados = {k: v for k, v in av.get("frequencias", {}).items() if v > 0}
                    if marcados:
                        print(f"    {q}: {json.dumps(marcados, ensure_ascii=False)}")
                    else:
                        print(f"    {q}: [vazio]")
                avisos = dados.get("avisos_observacoes", [])
                if avisos:
                    print(f"    avisos ({len(avisos)}): {avisos}")
            except ValueError as exc:
                print(f"    FALHOU: {exc}")
    except Exception as exc:
        print(f"  ERRO ao expandir: {exc}")