"""tools/pre_exame.py — Gera folhas PDF com QR Code (multi-faixa).

Uso:
    python tools/pre_exame.py --csv data/alunos_exame.csv \
        --dojo D01 --exame EXA-D01-2026-02 --senseis S01,S02,S03 \
        --cadastro data/cadastro/alunos.json --out output/pre_exame/

Fluxo:
    1. lê o CSV (alunos com faixa atual e pretendida);
    2. merge idempotente no cadastro (novos com "novo": true; existentes
       têm faixa_atual/faixa_pretendida/dojo_id atualizados a partir do CSV);
    3. para cada avaliador x aluno, desenha a folha usando o layout da faixa
       (critérios de config/faixas/ e coordenadas de config/coordenadas/);
    4. gera o QR Code com o payload padrão e salva o PDF.

Dependências: qrcode[pil], reportlab.
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
import unicodedata
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]
QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
NOME_QUESITO = {"kihon": "Kihon", "kata": "Kata",
                "bunkai": "Bunkai", "kumite": "Kumite"}

# Geometria padrão dos checkboxes — usada apenas se
# config/coordenadas/<faixa>.json ainda não existir. O OMR (Fase 03)
# lê o MESMO arquivo de coordenadas, então folha e leitor são "gêmeos".
CHECKBOX_X0_MM = 110.0
CHECKBOX_PASSO_MM = 6.5
CHECKBOX_LADO_MM = 4.5
CHECKBOX_QTD = 7

# Geometria padrão do campo Observação — mesma fonte usada pelo OMR
# para recortar a área de escrita (Fase 03). Defaults cobrem faixas
# cujo config/coordenadas ainda não tem as chaves obs_*.
OBS_X_MM = 20.0
OBS_LARGURA_MM = 120.0
OBS_ALTURA_MM = 6.0
OBS_PAUTAS = 1

# Tipografia (padrão do projeto: título >= 12pt, dado >= 10pt)
FONTE_TITULO = 13
FONTE_QUESITO = 12
FONTE_DADO = 10
FONTE_RODAPE = 9
LINHA_MM = 5.5  # entrelinha dos critérios (~1,55x para 10pt)

# Rodapé — texto completo. A quebra de linha é calculada em tempo de
# execução (ver desenhar_paragrafo), então nenhum trecho é cortado.
RODAPE_TEXTO = ("Como marcar: preencha TOTALMENTE o quadrado (caneta preta "
                "ou lápis 2B), da esquerda para a direita, sem pular "
                "caixas. Deixe em branco para zero falhas.")
RODAPE_MARGEM_MM = 15.0   # alinhado às demais margens da folha
RODAPE_BASE_MM = 10.0     # y da ÚLTIMA linha do rodapé

def carregar_json(caminho: Path) -> dict:
    with open(caminho, "r", encoding="utf-8") as fh:
        return json.load(fh)

def normalizar_faixa(faixa: str) -> str:
    """Remove acentos e normaliza para uppercase (payload QR sem acentos)."""
    sem_acentos = unicodedata.normalize("NFKD", faixa)
    ascii_only = "".join(c for c in sem_acentos if not unicodedata.combining(c))
    return ascii_only.upper().strip()

def montar_payload(dojo: str, exame: str, aluno_id: str,
                   sensei_id: str, faixa: str) -> str:
    """KA|DOJO|EXAME|ALUNO|SENSEI|FAIXA — sem acentos, com pipes."""
    return "|".join(["KA", dojo, exame, aluno_id, sensei_id,
                     normalizar_faixa(faixa)])

def atualizar_cadastro(csv_path: Path, cadastro_path: Path) -> list[dict]:
    """Merge idempotente do CSV no alunos.json.

    - Alunos novos: adicionados com "novo": true.
    - Alunos existentes: faixa_atual/faixa_pretendida/dojo_id atualizados
      a partir do CSV (fonte de verdade da inscrição no exame).
    """
    cadastro = (json.loads(cadastro_path.read_text(encoding="utf-8"))
                if cadastro_path.exists() else {"alunos": []})
    por_id = {a["id"]: a for a in cadastro["alunos"]}
    novos = []
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            aluno_id = row["id"]
            if aluno_id not in por_id:
                aluno = {**row, "novo": True}
                cadastro["alunos"].append(aluno)
                por_id[aluno_id] = aluno
                novos.append(aluno)
            else:
                for campo in ("faixa_atual", "faixa_pretendida", "dojo_id"):
                    if row.get(campo):
                        por_id[aluno_id][campo] = row[campo]
    cadastro_path.parent.mkdir(parents=True, exist_ok=True)
    cadastro_path.write_text(json.dumps(cadastro, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    return novos

def carregar_coordenadas(config_dir: Path, faixa: str) -> dict:
    """Carrega config/coordenadas/<faixa>.json; fallback para a geometria
    padrão com aviso (o OMR pode divergir se o arquivo não existir)."""
    caminho = config_dir / "coordenadas" / f"{faixa}.json"
    if caminho.exists():
        return carregar_json(caminho)
    print(f"[AVISO] coordenadas não encontradas em {caminho} — "
          f"usando geometria padrão")
    return {}

def quebrar_linhas(texto: str, fonte: str, tamanho: float,
                   largura_max: float) -> list[str]:
    """Divide o texto em linhas que cabem em largura_max.

    Mede com stringWidth (métricas reais da fonte) em vez de contar
    caracteres — é o que garante que nada seja cortado na margem.
    """
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if stringWidth(teste, fonte, tamanho) <= largura_max:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas

def desenhar_paragrafo(pdf: canvas.Canvas, texto: str, x: float, y: float,
                       largura_max: float, fonte: str = "Helvetica",
                       tamanho: float = FONTE_DADO) -> float:
    """Desenha texto com quebra de linha, sem cortar na margem.

    Retorna o y da última linha desenhada (útil para empilhar blocos).
    """
    leading = tamanho * 1.25
    linhas = quebrar_linhas(texto, fonte, tamanho, largura_max)
    for i, linha in enumerate(linhas):
        pdf.setFont(fonte, tamanho)
        pdf.drawString(x, y - i * leading, linha)
    return y - (len(linhas) - 1) * leading

def desenhar_campo_observacao(pdf: canvas.Canvas, x: float, y: float,
                              largura: float, altura: float,
                              pautas: int = 1,
                              label: str = "Observação:") -> float:
    """Desenha a área de escrita da Observação no lugar do texto solto.

    x, y = posição da linha do rótulo (a mesma da palavra 'Observação:').
    Caixa tracejada cinza + pauta(s) interna(s). A escrita do avaliador
    fica contida na caixa — nunca invade os checkboxes — e a caixa dá a
    âncora geométrica que o OMR (Fase 03) usa para recortar o campo.

    Retorna o y da base da caixa (para o chamador continuar o layout).
    """
    topo = y - 2 * mm
    pdf.setFont("Helvetica-Oblique", 6.5)
    pdf.setFillColor(colors.HexColor("#5F6368"))
    pdf.drawString(x, topo, label)
    pdf.setFillColor(colors.black)

    base = topo - altura
    pdf.saveState()
    pdf.setStrokeColor(colors.HexColor("#9AA0A6"))
    pdf.setLineWidth(0.5)
    pdf.setDash(1.5, 2)
    pdf.rect(x, base, largura, altura, stroke=1, fill=0)
    pdf.restoreState()

    if pautas:
        pdf.saveState()
        pdf.setStrokeColor(colors.HexColor("#C8CDD2"))
        pdf.setLineWidth(0.5)
        passo = altura / (pautas + 1)
        for i in range(1, pautas + 1):
            pdf.line(x + 2 * mm, base + i * passo,
                     x + largura - 2 * mm, base + i * passo)
        pdf.restoreState()

    return base

def desenhar_marcadores_fiduciais(pdf: canvas.Canvas,
                                  largura: float, altura: float) -> None:
    """Marcadores de registro em 3 cantos. O QR no canto superior direito
    funciona como 4ª referência de alinhamento para o OMR (Fase 03)."""
    margem = 8 * mm
    tam = 6 * mm
    cantos = ((margem, margem),                   # inferior esquerdo
              (largura - margem, margem),         # inferior direito
              (margem, altura - margem))          # superior esquerdo
    for cx, cy in cantos:
        pdf.setLineWidth(0.8)
        pdf.line(cx - tam, cy, cx + tam, cy)
        pdf.line(cx, cy - tam, cx, cy + tam)
        pdf.setLineWidth(0.4)
        pdf.rect(cx - tam / 2, cy - tam / 2, tam, tam)

def desenhar_folha(pdf: canvas.Canvas, aluno: dict, sensei_id: str,
                   dojo: str, exame: str, faixa_cfg: dict,
                   coordenadas: dict, tmp_dir: Path) -> None:
    """Desenha uma folha A4 do aluno, usando o layout da faixa."""
    largura, altura = A4
    faixa_label = aluno["faixa_atual"].capitalize()

    # Cabeçalho
    pdf.setFont("Helvetica-Bold", FONTE_TITULO)
    pdf.drawString(15 * mm, altura - 15 * mm,
                   f"Folha de Avaliação Individual — Faixa {faixa_label}")
    pdf.setFont("Helvetica", FONTE_DADO)
    pdf.drawString(15 * mm, altura - 22 * mm,
                   f"Aluno: {aluno['nome']} ({aluno['id']})")
    pdf.drawString(15 * mm, altura - 28 * mm,
                   f"Dojo: {dojo} | Exame: {exame} | Avaliador: {sensei_id}")

    # QR Code (canto superior direito)
    payload = montar_payload(dojo, exame, aluno["id"], sensei_id,
                             aluno["faixa_atual"])
    qr = qrcode.QRCode(border=1, box_size=8)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    qr_path = tmp_dir / f"qr_temp_{aluno['id']}_{sensei_id}.png"
    img.save(qr_path)
    pdf.drawImage(str(qr_path), largura - 35 * mm, altura - 35 * mm,
                  25 * mm, 25 * mm)

    # Geometria dos checkboxes — mesma usada pelo OMR (Fase 03)
    chk_x0 = float(coordenadas.get("checkbox_x0_mm", CHECKBOX_X0_MM)) * mm
    chk_passo = float(coordenadas.get("checkbox_passo_mm", CHECKBOX_PASSO_MM)) * mm
    chk_lado = float(coordenadas.get("checkbox_lado_mm", CHECKBOX_LADO_MM)) * mm
    chk_qtd = int(coordenadas.get("checkbox_qtd", CHECKBOX_QTD))

    # Geometria do campo Observação — mesma usada pelo OMR (Fase 03)
    obs_x = float(coordenadas.get("obs_x_mm", OBS_X_MM)) * mm
    obs_largura = float(coordenadas.get("obs_largura_mm", OBS_LARGURA_MM)) * mm
    obs_altura = float(coordenadas.get("obs_altura_mm", OBS_ALTURA_MM)) * mm
    obs_pautas = int(coordenadas.get("obs_pautas", OBS_PAUTAS))

    y_atual = altura - 38 * mm
    for quesito in QUESITOS_ORDEM:
        criterios = faixa_cfg[quesito]["criterios"]
        pdf.setFont("Helvetica-Bold", FONTE_QUESITO)
        pdf.drawString(15 * mm, y_atual, NOME_QUESITO[quesito])
        y_atual -= 6 * mm
        pdf.setFont("Helvetica", FONTE_DADO)
        for cri in criterios:
            pdf.drawString(20 * mm, y_atual, cri["nome"])
            for i in range(chk_qtd):
                x0 = chk_x0 + i * chk_passo
                pdf.rect(x0, y_atual - 2 * mm, chk_lado, chk_lado)
            y_atual -= LINHA_MM * mm
        y_atual -= 2 * mm
        # Campo Observação demarcado (rótulo + caixa tracejada + pauta)
        y_atual = desenhar_campo_observacao(pdf, obs_x, y_atual,
                                            obs_largura, obs_altura,
                                            obs_pautas)
        y_atual -= 2 * mm
        if y_atual < 20 * mm:
            print(f"[AVISO] layout apertado na faixa {faixa_label} "
                  f"(quesito {NOME_QUESITO[quesito]}) — revise "
                  f"config/faixas/{aluno['faixa_atual'].lower()}.json")

    # Rodapé — instrução de marcação (quebra de linha automática: o
    # último trecho não é mais cortado na margem).
    largura_util = largura - 2 * RODAPE_MARGEM_MM * mm
    linhas_rodape = quebrar_linhas(RODAPE_TEXTO, "Helvetica-Oblique",
                                   FONTE_RODAPE, largura_util)
    y_rodape = (RODAPE_BASE_MM * mm
                + (len(linhas_rodape) - 1) * FONTE_RODAPE * 1.25)
    desenhar_paragrafo(pdf, RODAPE_TEXTO, RODAPE_MARGEM_MM * mm, y_rodape,
                       largura_util, fonte="Helvetica-Oblique",
                       tamanho=FONTE_RODAPE)

    desenhar_marcadores_fiduciais(pdf, largura, altura)
    pdf.showPage()

def executar_dry_run(args: argparse.Namespace, faixas_cfg: dict) -> int:
    """Modo --dry-run: mostra o plano sem gravar cadastro nem PDFs."""
    print("=== DRY RUN — nenhum arquivo será gravado ===")
    with open(args.csv, encoding="utf-8") as fh:
        alunos = list(csv.DictReader(fh))
    existentes = set()
    if args.cadastro.exists():
        cadastro = json.loads(args.cadastro.read_text(encoding="utf-8"))
        existentes = {a["id"] for a in cadastro["alunos"]}
    novos = [a for a in alunos if a["id"] not in existentes]
    atualizados = [a for a in alunos if a["id"] in existentes]
    com_folha = [a for a in alunos if a["faixa_atual"].lower() in faixas_cfg]
    sem_folha = [a for a in alunos if a["faixa_atual"].lower() not in faixas_cfg]
    print(f"CSV: {args.csv} ({len(alunos)} alunos)")
    print(f"Dojo: {args.dojo} | Exame: {args.exame} | Senseis: {args.senseis}")
    print(f"Cadastro: {args.cadastro}")
    print(f"Novos (novo: true): {len(novos)} -> "
          f"{', '.join(a['id'] for a in novos) or '-'}")
    print(f"Existentes (faixa atualizada): {len(atualizados)} -> "
          f"{', '.join(a['id'] for a in atualizados) or '-'}")
    for sensei in [s.strip() for s in args.senseis.split(",")]:
        print(f"PDF folhas_{sensei}.pdf: {len(com_folha)} folha(s) "
              f"({', '.join(a['id'] for a in com_folha)})")
    if sem_folha:
        print(f"[AVISO] sem folha (faixa não suportada): "
              f"{', '.join(a['id'] for a in sem_folha)}")
    return 0

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pré-exame Karate-Ashi v2.0 (multi-faixa)")
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--dojo", required=True)
    ap.add_argument("--exame", required=True)
    ap.add_argument("--senseis", required=True,
                    help="IDs dos avaliadores separados por vírgula")
    ap.add_argument("--cadastro", type=Path,
                    default=Path("data/cadastro/alunos.json"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--out", type=Path, default=Path("output/pre_exame"))
    ap.add_argument("--dry-run", action="store_true",
                    help="apenas lista o plano, sem gravar cadastro nem PDFs")
    args = ap.parse_args()

    # Tabelas de critérios por faixa (carregadas uma única vez)
    faixas_cfg = {}
    for faixa in FAIXAS_SUPORTADAS:
        caminho = args.config / "faixas" / f"{faixa}.json"
        if not caminho.exists():
            print(f"[ERRO] critérios não encontrados: {caminho}")
            return 2
        faixas_cfg[faixa] = carregar_json(caminho)["quesitos"]

    # Coordenadas por faixa — compartilhadas com o OMR (Fase 03)
    coordenadas_por_faixa = {
        faixa: carregar_coordenadas(args.config, faixa)
        for faixa in FAIXAS_SUPORTADAS
    }

    if args.dry_run:
        return executar_dry_run(args, faixas_cfg)

    novos = atualizar_cadastro(args.csv, args.cadastro)
    todos = json.loads(args.cadastro.read_text(encoding="utf-8"))["alunos"]
    args.out.mkdir(parents=True, exist_ok=True)

    gerados = 0
    sem_folha = []
    # QR temporários ficam fora do diretório de saída e são removidos
    # automaticamente (critério de aceite: sem qr_temp_*.png ao final).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for sensei in [s.strip() for s in args.senseis.split(",")]:
            pdf = canvas.Canvas(str(args.out / f"folhas_{sensei}.pdf"),
                                pagesize=A4)
            for aluno in todos:
                if aluno["dojo_id"] != args.dojo:
                    continue
                faixa = aluno["faixa_atual"].lower()
                if faixa not in faixas_cfg:
                    print(f"[AVISO] faixa '{faixa}' não suportada — aluno "
                          f"{aluno['id']} sem folha nesta versão")
                    sem_folha.append(aluno["id"])
                    continue
                desenhar_folha(pdf, aluno, sensei, args.dojo, args.exame,
                               faixas_cfg[faixa], coordenadas_por_faixa[faixa],
                               tmp_dir)
                gerados += 1
            pdf.save()

    print(f"Pré-exame gerado em {args.out} | folhas: {gerados} | "
          f"novos cadastrados: {len(novos)}")
    if sem_folha:
        print(f"[AVISO] alunos sem folha (faixa não suportada): "
              f"{', '.join(sem_folha)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())