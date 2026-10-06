"""tools/diag_alinhamento.py — por scan e por aluno: dy do QR, da grade,
do prior, fonte escolhida e incidentes de alinhamento (v3.27).

  python tools/diag_alinhamento.py <pasta_scans> --config config
  python tools/diag_alinhamento.py <pasta_scans> --config config --dump v327.json
  python tools/diag_alinhamento.py --diff v324.json v327.json

--diff lista toda célula (scan, aluno, quesito, critério) que mudou entre duas
versões: é a rede contra regressão nas folhas que já estavam certas.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PREFIXOS = ("calibracao_offset", "alinhamento", "alias", "aspecto",
            "omr_reader", "dy_", "presenca:", "ausencia_com_marcas")


def ler_pasta(pasta: Path, cfg: Path) -> dict:
    from core import omr_reader
    saida: dict = {}
    for p in sorted(pasta.glob("*.png")):
        try:
            res = omr_reader.processar_imagem(p, cfg, origem="scanner",
                                              aplicar_offset=True)
        except Exception as e:  # noqa: BLE001
            saida[p.name] = {"erro": str(e)}
            continue
        saida[p.name] = {r["metadados"]["aluno_id"]: {
            "avaliador": r["metadados"]["avaliador_id"],
            "versao": r.get("omr_reader_version", "?"),
            "presenca": r["presenca"],
            "freq": {q: v["frequencias"] for q, v in r["avaliacoes"].items()},
            "inc": [i for i in r["incidentes_auditoria"]
                    if i.startswith(PREFIXOS) or "suspeito" in i
                    or "anel_nao_encontrado" in i],
        } for r in res}
    return saida


def tabela(dados: dict) -> None:
    for scan, alunos in dados.items():
        if "erro" in alunos:
            print(f"{scan}: ERRO {alunos['erro']}")
            continue
        for aid, d in alunos.items():
            print(f"{scan} | {aid} | {d['avaliador']} | {d['presenca']}")
            for i in d["inc"]:
                print(f"    {i}")


def diff(a: dict, b: dict) -> int:
    n = 0
    for scan in sorted(set(a) | set(b)):
        for aid in sorted(set(a.get(scan, {})) | set(b.get(scan, {}))):
            pa = a.get(scan, {}).get(aid, {}).get("presenca")
            pb = b.get(scan, {}).get(aid, {}).get("presenca")
            if pa != pb:
                n += 1
                print(f"{scan} {aid} PRESENCA: {pa} -> {pb}")
            fa = a.get(scan, {}).get(aid, {}).get("freq", {})
            fb = b.get(scan, {}).get(aid, {}).get("freq", {})
            for q in sorted(set(fa) | set(fb)):
                ca, cb = fa.get(q, {}), fb.get(q, {})
                for c in sorted(set(ca) | set(cb)):
                    if ca.get(c, 0) != cb.get(c, 0):
                        n += 1
                        print(f"{scan} {aid} {q}.{c}: "
                              f"{ca.get(c, 0)} -> {cb.get(c, 0)}")
    print(f"{n} celula(s) alterada(s)")
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pasta", nargs="?")
    ap.add_argument("--config", default="config")
    ap.add_argument("--dump")
    ap.add_argument("--diff", nargs=2, metavar=("A.json", "B.json"))
    a = ap.parse_args()
    if a.diff:
        diff(*(json.loads(Path(f).read_text("utf-8")) for f in a.diff))
        return
    if not a.pasta:
        ap.error("informe a pasta de scans (ou --diff)")
    dados = ler_pasta(Path(a.pasta), Path(a.config))
    if a.dump:
        Path(a.dump).write_text(json.dumps(dados, ensure_ascii=False,
                                           indent=1), "utf-8")
    tabela(dados)


if __name__ == "__main__":
    main()