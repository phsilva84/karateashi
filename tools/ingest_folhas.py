"""tools/ingest_folhas.py — Ingestão unificada scanner + fotos (v2col-4.1).

Segunda camada de entrada: além das FOTOS de celular, o sistema aceita folhas
DIGITALIZADAS (scanner de mesa ou ADF). O objetivo é não depender da qualidade
da foto — o scanner entrega a página plana, sem perspectiva.

Origem (--origem):
  auto    (padrão) — pasta "scanner" → scanner; "foto"/"fotos" → foto;
                     senão a heurística do núcleo (_parece_scanner);
  scanner — força o caminho de digitalização;
  foto    — força o caminho de foto (warp por contorno/âncora).

Formatos: .jpg .jpeg .png .tif .tiff .bmp .webp e .pdf. TIFF e PDF multipágina
são expandidos automaticamente — uma página = uma folha.

Uso:
    python tools/ingest_folhas.py ^
        --entrada "G:/Drives compartilhados/Karate-Ashi Inbox/entrada" ^
        --config config ^
        --saida "G:/Drives compartilhados/Karate-Ashi Arquivo/processados" ^
        --arquivo "G:/Drives compartilhados/Karate-Ashi Arquivo/imagens"
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
    """Decisão 1: a ingestão decide a origem olhando o nome das pastas."""
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
                "Alternativa: exporte as páginas como PNG/TIFF.") from exc
        pdf = pdfium.PdfDocument(str(caminho))
        try:
            paginas = []
            for indice in range(len(pdf)):
                bitmap = pdf[indice].render(scale=300 / 72)   # ~300 dpi
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingestão de folhas (scanner + fotos)")
    ap.add_argument("--entrada", required=True, type=Path,
                    help="pasta de entrada (pode ser o Drive montado)")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--saida", type=Path, default=Path("output/json"))
    ap.add_argument("--arquivo", type=Path, default=None,
                    help="originais vão para cá após processar")
    ap.add_argument("--origem", choices=("auto", "scanner", "foto"), default="auto")
    ap.add_argument("--faixa", default=None,
                    help="força a faixa; sem isso, a faixa vem do QR")
    ap.add_argument("--tmp", type=Path, default=Path("output/_ingest"))
    args = ap.parse_args()

    if not args.entrada.is_dir():
        print(f"[ERRO] entrada não é uma pasta: {args.entrada}")
        return 2
    args.saida.mkdir(parents=True, exist_ok=True)
    args.tmp.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(
        f for f in args.entrada.rglob("*")
        if f.is_file() and f.suffix.casefold() in EXT_VALIDAS
        and args.tmp not in f.parents)

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

            # CORRIGIDO: novo layout tem até 3 alunos por folha — o
            # processar_imagem devolve uma LISTA (um dict por aluno).
            # Garante lista mesmo se algum dia voltar a ser dict único.
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
                      f"{metadados.get('faixa')} | {origem} | "
                      f"obs: {obs[:70]}")

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

    print()
    for rotulo, erro in falhas:
        print(f"[FALHA] {rotulo}: {erro}")
    print(f"\nProcessadas: {len(processadas)} | falhas: {len(falhas)} | "
          f"JSONs em {args.saida}")
    return 0 if not falhas else 1


if __name__ == "__main__":
    raise SystemExit(main())