FASE 04 — Pré-exame: Geração de Folhas PDF com QR Code0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE
Dev Python Sênior — CLI, CSV, integração de bibliotecas.
Designer de Formulário A4 — layout limpo, elementos bem distribuídos, instrução no rodapé.
Analista Pedagógico de Karatê — estrutura do gabarito (4 quesitos, 7 checkboxes, observação).
Regras de conduta: use SEMPRE o padrão de payload definido abaixo; nunca invente campos; se algo não estiver especificado, PERGUNTE antes de assumir; ao final, preencha o checklist.1. Objetivo2. Contexto mínimo do projetoAntes do exame, o Sensei responsável prepara a lista de alunos. O script gera as folhas prontas para imprimir. O QR elimina a leitura de nome manuscrito: o OMR (Fase 03) lê o QR para identificar aluno, avaliador, dojo, exame e faixa. O cadastro inicial fica persistido e não precisa ser refeito nas próximas avaliações.3. Decisões aprovadas (não reabrir)
CSV de entrada com colunas: id,nome,faixa_atual,faixa_pretendida,dojo_id.
Exame ID único por Dojo: EXA-<DOJO_ID>-<ANO></ano>-<EDICAO></edicao> (ex: EXA-D01-2026-02).
Cadastro: merge no alunos.json, novos alunos com "novo": true; não duplicar os existentes.
Folha A4 vertical, 1 aluno por folha; QR no canto superior direito; marcadores fiduciais nos 4 cantos; rodapé com instrução "Como marcar" (preencher totalmente, da esquerda para a direita, contíguo).
Dependências: qrcode[pil], reportlab.
4. Tarefas
 Criar tools/pre_exame.py conforme código de referência (seção 5).
 Criar data/exemplo_alunos_exame.csv com 3 alunos de exemplo.
 Rodar o script com --dry-run e depois gerar um lote de teste.
 Verificar com um leitor de QR que o payload decodificado confere.
 Registrar no Status.
5. Código de referênciadata/exemplo_alunos_exame.csv:

id,nome,faixa_atual,faixa_pretendida,dojo_id
A01,Isabelly Santos,Branca,Amarela,D01
A02,Nicole Souza,Branca,Amarela,D01
A03,Wesley Lima,Amarela,Laranja,D01


`tools/pre_exame.py`:


"""tools/pre_exame.py — Gera folhas PDF com QR Code para o exame.

Uso:
    python tools/pre_exame.py --csv data/alunos_exame.csv 
        --dojo D01 --exame EXA-D01-2026-02 --senseis S01,S02,S03 
        --cadastro data/cadastro/alunos.json --out output/pre_exame/

Fluxo:

1. lê o CSV de alunos;
2. faz merge no cadastro (novos alunos ganham "novo": true);
3. gera um PDF de folhas (uma por avaliador x aluno) com QR Code,
   checkboxes, observações e instrução de marcação.
   """
   from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

QUESITOS = {
    "KIHON": ["Base Incorreta", "Execução Técnica Incorreta",
              "Movimento sem Carga/Peso", "Falta de Foco",
              "Perda de Equilíbrio", "Ausência de Kiai"],
    "KATA": ["Embusen Incorreto", "Base Incorreta", "Falta de Ritmo",
             "Ausência de Kiai", "Execução Técnica Incorreta",
             "Movimento sem Carga/Peso", "Falta de Foco",
             "Perda de Equilíbrio"],
    "BUNKAI": ["Base Incorreta", "Ausência de Kiai",
               "Execução Técnica Incorreta", "Movimento sem Carga/Peso",
               "Falta de Foco", "Perda de Equilíbrio",
               "Distância Inadequada", "Falta de Controle / Risco"],
    "KUMITE": ["Movimento sem Carga/Peso", "Falta de Foco",
               "Perda de Equilíbrio", "Ausência de Kiai",
               "Distância Inadequada", "Falta de Combatividade",
               "Falta de Controle / Risco"],
}

def montar_payload(dojo: str, exame: str, aluno_id: str,
                   sensei_id: str, faixa: str) -> str:
    """KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA — sem acentos, com pipes."""
    return "|".join(["KA", dojo, exame, aluno_id, sensei_id,
                     faixa.upper().replace("Ç", "C").replace("Ã", "A")])

def atualizar_cadastro(csv_path: Path, cadastro_path: Path) -> list[dict]:
    """Faz merge do CSV no alunos.json. Novos alunos entram com novo: true."""
    cadastro = (json.loads(cadastro_path.read_text(encoding="utf-8"))
                if cadastro_path.exists() else {"alunos": []})
    existentes = {a["id"] for a in cadastro["alunos"]}
    novos = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["id"] not in existentes:
                aluno = {**row, "novo": True}
                cadastro["alunos"].append(aluno)
                novos.append(aluno)
    cadastro_path.parent.mkdir(parents=True, exist_ok=True)
    cadastro_path.write_text(json.dumps(cadastro, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return novos

def desenhar_folha(pdf: canvas.Canvas, aluno: dict, sensei_id: str,
                   dojo: str, exame: str, paginas: Path) -> None:
    """Desenha UMA folha A4: cabeçalho, QR, quesitos, observações, rodapé."""
    largura, altura = A4
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(15 * mm, altura - 15 * mm,
                   f"Folha de Avaliação Individual — {aluno['faixa_atual']}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(15 * mm, altura - 22 * mm,
                   f"Aluno: {aluno['nome']} ({aluno['id']})")
    pdf.drawString(15 * mm, altura - 28 * mm,
                   f"Dojo: {dojo}  |  Exame: {exame}  |  Avaliador: {sensei_id}")

    payload = montar_payload(dojo, exame, aluno["id"], sensei_id,
                             aluno["faixa_pretendida"])
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(paginas / f"qr_temp_{aluno['id']}_{sensei_id}.png")

    y_atual = altura - 38 * mm
    for nome_quesito, criterios in QUESITOS.items():
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(15 * mm, y_atual, nome_quesito)
        y_atual -= 6 * mm
        pdf.setFont("Helvetica", 9)
        for cri in criterios:
            pdf.drawString(20 * mm, y_atual, cri)
            for i in range(7):
                x0 = 110 * mm + i * 6.5 * mm
                pdf.rect(x0, y_atual - 2 * mm, 4.5 * mm, 4.5 * mm)
            y_atual -= 5.5 * mm
        y_atual -= 2 * mm
        pdf.drawString(20 * mm, y_atual, "Observação:")
        y_atual -= 6 * mm
        y_atual -= 4 * mm

    # QR no canto superior direito
    pdf.drawImage(str(paginas / f"qr_temp_{aluno['id']}_{sensei_id}.png"),
                  largura - 35 * mm, altura - 35 * mm, 25 * mm, 25 * mm)

    # Rodapé com instrução de marcação
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(15 * mm, 12 * mm,
                   "Como marcar: preencha TOTALMENTE o quadrado (caneta preta "
                   "ou lápis 2B), da esquerda para a direita, sem pular caixas. "
                   "Deixe em branco para zero falhas.")
    pdf.showPage()

def main() -> int:
    ap = argparse.ArgumentParser(description="Pré-exame Karate-Ashi v2.0")
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--dojo", required=True)
    ap.add_argument("--exame", required=True)
    ap.add_argument("--senseis", required=True,
                    help="IDs dos avaliadores separados por vírgula")
    ap.add_argument("--cadastro", type=Path,
                    default=Path("data/cadastro/alunos.json"))
    ap.add_argument("--out", type=Path, default=Path("output/pre_exame"))
    args = ap.parse_args()

    alunos = atualizar_cadastro(args.csv, args.cadastro)
    todos = json.loads(args.cadastro.read_text(encoding="utf-8"))["alunos"]
    ids_alunos = [a["id"] for a in todos if a["dojo_id"] == args.dojo]
    args.out.mkdir(parents=True, exist_ok=True)

    for sensei in [s.strip() for s in args.senseis.split(",")]:
        pdf = canvas.Canvas(str(args.out / f"folhas_{sensei}.pdf"),
                            pagesize=A4)
        for aluno in todos:
            if aluno["id"] in ids_alunos:
                desenhar_folha(pdf, aluno, sensei, args.dojo, args.exame,
                               args.out)
        pdf.save()
    print(f"Pré-exame gerado em {args.out} — novos cadastrados: "
          f"{len(alunos)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())



6. Critérios de aceite
   CSV de exemplo lido sem erro; cadastro atualizado sem duplicar existentes.
   PDF gerado por avaliador com uma folha por aluno.
   Folha A4 contém: 4 quesitos, seus critérios com 7 checkboxes, campo Observação por quesito, cabeçalho e rodapé com instrução.
   Arquivos .png temporários do QR removidos ao final (ou gerados em pasta temp).
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
