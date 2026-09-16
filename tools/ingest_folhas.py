"""tools/ingest_folhas.py — Ingestão unificada scanner + fotos (v2col-4.0).

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
        paginas = []
        for indice in range(len(pdf)):
            bitmap = pdf[indice].render(scale=300 / 72)   # ~300 dpi
            saida = destino / f"{caminho.stem}_p{indice + 1}.png"
            bitmap.to_pil().save(saida)
            paginas.append(saida)
        return paginas

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
        origem = args.origem
        if origem == "auto":
            origem = _origem_por_pasta(arquivo) or "auto"

        try:
            paginas = _expandir(arquivo, args.tmp)
        except RuntimeError as exc:
            falhas.append((arquivo.name, str(exc)))
            continue

        for pagina in paginas:
            rotulo = arquivo.name if len(paginas) == 1 else pagina.name
            try:
                # Assinatura canônica v2.0: (caminho_imagem, base_cfg, faixa=None).
                # O kwarg espúrio 'origem' foi removido (quebra #5 da auditoria).
                resultado = omr_reader.processar_imagem(
                    pagina, args.config, faixa=args.faixa)
            except ValueError as exc:
                falhas.append((rotulo, str(exc)))
                continue

            destino = args.saida / f"{pagina.stem}.json"
            with open(destino, "w", encoding="utf-8") as fh:
                json.dump(resultado, fh, ensure_ascii=False, indent=2)

            aluno = resultado["aluno"]["id"]
            metadados = resultado["metadados"]
            obs = resultado.get("observacao_montada") or "-"
            # Guarda defensiva: o leitor v2.0 pode não expor 'origem' no resultado.
            origem_final = resultado.get("origem", origem)
            processadas.append((rotulo, aluno, metadados.get("faixa"),
                                origem_final, obs))
            print(f"[OK] {rotulo} | aluno {aluno} | faixa "
                  f"{metadados.get('faixa')} | {origem_final} | "
                  f"obs: {obs[:70]}")

        if args.arquivo:
            args.arquivo.mkdir(parents=True, exist_ok=True)
            shutil.move(str(arquivo), str(args.arquivo / arquivo.name))

    print()
    for rotulo, erro in falhas:
        print(f"[FALHA] {rotulo}: {erro}")
    print(f"\nProcessadas: {len(processadas)} | falhas: {len(falhas)} | "
          f"JSONs em {args.saida}")
    return 0 if not falhas else 1

if __name__ == "__main__":
    raise SystemExit(main())