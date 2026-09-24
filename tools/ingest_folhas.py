#!/usr/bin/env python3
"""tools/ingest_folhas.py — Ingestão unificada scanner + fotos (v2col-4.1 revisado).

Segunda camada de entrada: além das FOTOS de celular, o sistema aceita folhas
DIGITALIZADAS (scanner de mesa ou ADF). O objetivo é não depender da qualidade
da foto — o scanner entrega a página plana, sem perspectiva.

Origem (--origem):
  auto    (padrão) — pasta "scanner" → scanner; "foto"/"fotos" → foto;
                     senão a heurística do núcleo (_parece_scanner);
  scanner — força o caminho de digitalização;
  foto    — força o caminho de foto (warp por contorno/âncora).

Formato: .jpg .jpeg .png .tif .tiff .bmp .webp e .pdf. TIFF e PDF multipágina
são expandidos automaticamente — uma página = uma folha.

Saídas:
  - um JSON por aluno (schema v2.0) em --saida:
      {pagina.stem}_{aluno_id}.json
  - resumo_ingestao.json (auditoria do lote — o pipeline ignora este arquivo)

Pré-requisito:
  - core/omr_reader v3.14 exige o JSON de coordenadas gerado junto com a
    folha (output/pre_exame/{exame}_{avaliador}_folha*_coordenadas.json).
    Gere as folhas com tools/pre_exame.py ANTES de ingerir os scans.

Uso:
    python tools/ingest_folhas.py ^
        --entrada "G:/Drives compartilhados/Karate-Ashi Inbox/entrada" ^
        --config config ^
        --saida "G:/Drives compartilhados/Karate-Ashi Arquivo/processados" ^
        --arquivo "G:/Drives compartilhados/Karate-Ashi Arquivo/imagens" ^
        --origem auto ^
        --faixa branca
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import omr_reader  # noqa: E402

EXT_IMAGEM = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
EXT_PDF = {".pdf"}
EXT_VALIDAS = EXT_IMAGEM | EXT_PDF
PASTAS_SCANNER = {"scanner", "digitalizado", "digitalizadas", "scan"}
PASTAS_FOTO = {"foto", "fotos", "photo", "photos", "celular"}


def _origem_por_pasta(caminho: Path) -> str | None:
    """Decide a origem olhando o nome das pastas do caminho (Decisão 1)."""
    nomes = {p.casefold() for p in caminho.parts}
    if nomes & PASTAS_SCANNER:
        return "scanner"
    if nomes & PASTAS_FOTO:
        return "foto"
    return None


def _expandir(caminho: Path, destino: Path) -> list[Path]:
    """Devolve as páginas do arquivo (único, ou extraídas de TIFF/PDF)."""
    ext = caminho.suffix.casefold()

    if ext in {".tif", ".tiff"}:
        try:
            from PIL import Image, ImageSequence
        except ImportError:
            return [caminho]
        try:
            with Image.open(caminho) as im:
                if getattr(im, "n_frames", 1) <= 1:
                    return [caminho]
                paginas = []
                for i, quadro in enumerate(ImageSequence.Iterator(im), start=1):
                    saida = destino / f"{caminho.stem}_p{i}.png"
                    quadro.convert("RGB").save(saida)
                    paginas.append(saida)
                return paginas
        except Exception:  # noqa: BLE001 — TIFF exótico: segue como arquivo único
            return [caminho]

    if ext in EXT_PDF:
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise RuntimeError(
                "PDF exige a biblioteca 'pypdfium2' (pip install pypdfium2). "
                "Alternativa: exporte as páginas como PNG/TIFF."
            ) from exc
        pdf = pdfium.PdfDocument(str(caminho))
        try:
            paginas = []
            for indice in range(len(pdf)):
                bitmap = pdf[indice].render(scale=300 / 72)  # ~300 dpi
                saida = destino / f"{caminho.stem}_p{indice + 1}.png"
                imagem = bitmap.to_pil()
                try:
                    imagem.save(saida)
                finally:
                    imagem.close()
                paginas.append(saida)
            return paginas
        finally:
            # Fecha o documento PDF e libera o arquivo no disco.
            # Sem isso, o Windows mantém o arquivo aberto e o move falha
            # com PermissionError [WinError 32].
            pdf.close()

    return [caminho]


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Ingestão de folhas (scanner + fotos) — Karate-Ashi v2col-4.1")
    ap.add_argument("--entrada", required=True, type=Path,
                    help="pasta com os scans/fotos (lida recursivamente)")
    ap.add_argument("--config", type=Path, default=RAIZ / "config",
                    help="pasta config/ (default: <repo>/config)")
    ap.add_argument("--saida", type=Path, default=RAIZ / "output" / "omr",
                    help="pasta para os JSONs por aluno (default: output/omr)")
    ap.add_argument("--arquivo", type=Path, default=None,
                    help="pasta para arquivar os originais após processar (opcional)")
    ap.add_argument("--tmp", type=Path, default=RAIZ / "output" / "tmp_ingest",
                    help="pasta temporária para páginas expandidas de TIFF/PDF")
    ap.add_argument("--origem", choices=("auto", "scanner", "foto"),
                    default="auto",
                    help="scanner = pula warp; foto = warp por contorno/âncora")
    ap.add_argument("--faixa", default=None,
                    help="força a faixa; sem isso, vem do QR do aluno")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.entrada.is_dir():
        print(f"[ERRO] entrada não é uma pasta: {args.entrada}")
        return 2
    if not args.config.is_dir():
        print(f"[ERRO] --config não é uma pasta: {args.config}")
        return 2

    args.saida.mkdir(parents=True, exist_ok=True)
    args.tmp.mkdir(parents=True, exist_ok=True)

    # Pastas de saída/arquivo também não podem ser varridas como entrada
    # (idempotência: nunca reprocessar os próprios artefatos).
    excluidas = [args.tmp, args.saida]
    if args.arquivo:
        excluidas.append(args.arquivo)

    arquivos = sorted(
        f for f in args.entrada.rglob("*")
        if f.is_file() and f.suffix.casefold() in EXT_VALIDAS
        and not any(d in f.parents for d in excluidas))
    if not arquivos:
        print(f"[AVISO] nenhuma imagem/PDF em {args.entrada}")
        return 3

    processadas, falhas = [], []
    for arquivo in arquivos:
        # Decisão 1: resolve a origem UMA vez por arquivo (não por página).
        origem = args.origem
        if origem == "auto":
            origem = _origem_por_pasta(arquivo) or "auto"

        try:
            paginas = _expandir(arquivo, args.tmp)
        except RuntimeError as exc:
            falhas.append((arquivo.name, str(exc)))
            continue

        paginas_ok = True
        for pagina in paginas:
            rotulo = arquivo.name if len(paginas) == 1 else pagina.name
            try:
                # Assinatura canônica v2.0 + origem (v3.5):
                # 'scanner' pula o warp (folha já plana) — corrige QR do
                # aluno não lido e balões desalinhados no scan.
                resultados = omr_reader.processar_imagem(
                    pagina, args.config, faixa=args.faixa, origem=origem)
            except ValueError as exc:
                falhas.append((rotulo, str(exc)))
                paginas_ok = False
                continue

            # Novo layout: até 3 alunos por folha — o processar_imagem
            # devolve uma LISTA (um dict por aluno).
            if not isinstance(resultados, list):
                resultados = [resultados]

            for resultado in resultados:
                # Decisão 1: a INGESTÃO grava o metadado 'origem' no JSON.
                # O núcleo não precisa saber — ele só lê a imagem.
                resultado["origem"] = origem

                aluno_id = (resultado.get("aluno") or {}).get("id") or "desconhecido"
                destino = args.saida / f"{pagina.stem}_{aluno_id}.json"
                with open(destino, "w", encoding="utf-8") as fh:
                    json.dump(resultado, fh, ensure_ascii=False, indent=2)

                metadados = resultado.get("metadados") or {}
                obs = resultado.get("observacao_montada") or "-"
                processadas.append((rotulo, aluno_id,
                                    metadados.get("faixa"), origem, obs))
                print(f"[OK] {rotulo} | aluno {aluno_id} | faixa "
                      f"{metadados.get('faixa')} | {origem} | obs: {obs[:70]}")

        # Decisão 2: arquiva o original SÓ se todas as páginas processaram.
        # Se alguma página falhou, o arquivo fica na entrada para reprocessar.
        if args.arquivo and paginas_ok:
            args.arquivo.mkdir(parents=True, exist_ok=True)
            destino_arquivo = args.arquivo / arquivo.name
            try:
                shutil.move(str(arquivo), str(destino_arquivo))
            except OSError:
                # Lock transitório (Windows/antivírus): espera e tenta de novo.
                time.sleep(1)
                try:
                    shutil.move(str(arquivo), str(destino_arquivo))
                except OSError as exc:
                    # Não derruba o lote: o arquivo fica na entrada e será
                    # reprocessado na próxima rodada (idempotente).
                    print(f"[AVISO] {arquivo.name}: processado, mas não "
                          f"arquivado ({exc}). Será reprocessado na próxima "
                          f"rodada.")

    # Resumo do lote — auditoria; o pipeline ignora este arquivo
    # (core/pipeline.carregar_jsons_omr exclui resumo_ingestao.json).
    resumo = {
        "versao_ingest": "v2col-4.1-revisado",
        "gerado_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_processadas": len(processadas),
        "total_falhas": len(falhas),
        "processadas": [
            {"arquivo": rotulo, "aluno": aluno_id, "faixa": faixa,
             "origem": origem, "obs": obs}
            for rotulo, aluno_id, faixa, origem, obs in processadas
        ],
        "falhas": [{"arquivo": r, "erro": e} for r, e in falhas],
    }
    (args.saida / "resumo_ingestao.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for rotulo, erro in falhas:
        print(f"[FALHA] {rotulo}: {erro}")
    print(f"\nProcessadas: {len(processadas)} | falhas: {len(falhas)} | "
          f"JSONs em {args.saida}")
    return 0 if not falhas else 1


if __name__ == "__main__":
    raise SystemExit(main())