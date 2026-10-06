"""diagnostico_balao.py — Imprime taxa/blob de cada balão de um aluno (Kihon).
Uso:
  python diagnostico_balao.py "<caminho_scan.png>" <avaliador> <aluno>
  ex.: python diagnostico_balao.py "G:/Meu Drive/documentos/KarateAshi_Exames/scans/img20261003_22032837.png" S04 W07
"""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from core import omr_reader as omr  # noqa: E402


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    scan, av, aluno = sys.argv[1], sys.argv[2], sys.argv[3]
    img = omr.carregar_imagem(Path(scan))
    a4 = omr.normalizar_a4(img)
    cinza = omr._cinza(a4)
    escala = omr.A4_W_PX / omr.A4_W_MM
    janela = omr.JANELA_MM * escala

    m = omr._QR_EXAME.search(omr._payload_por_prefixo(img, "AVALIADOR") or "")
    if not m:
        print("QR do exame não encontrado"); sys.exit(1)
    avaliador, exame = m.group(1), m.group(3)   # group(3) = EXAME (corrigido)
    coords = omr._carregar_coordenadas(Path("output/pre_exame"), exame, av)
    if coords is None:
        print(f"coordenadas não encontradas para {exame}_{av}")
        sys.exit(1)
    al = next((a for a in coords["alunos"] if a["id"] == aluno), None)
    if al is None:
        print(f"aluno {aluno} não está no JSON de {avaliador}")
        sys.exit(1)
    for chave, baloes in al["frequencias"].items():
        if "kihon" not in chave:
            continue
        for i, b in enumerate(baloes, 1):
            taxa, blob = omr._densidade_balao(cinza, b, escala, janela)
            est = omr.classificar_checkbox(taxa, blob)
            print(f"{chave} balao {i}: taxa={taxa:.3f} blob={blob:.3f} "
                  f"-> {est.upper()}")


if __name__ == "__main__":
    main()