"""core/pipeline.py — Orquestrador do processamento v2.0.

Fluxo:
1. varre data/gabaritos/ (imagens) e data/ (TXT fallback);
2. para cada imagem: OMR (core/omr_reader) → JSON intermediário;
3. agrupa JSONs por aluno (QR: aluno_id) e por avaliador;
4. engine (core/engine) calcula notas por faixa;
5. relatórios (core/relatorios) geram as 3 camadas, por Dojo.

Correções v2.0 (revisão da Fase 08):
- A faixa vem do QR Code (dados["aluno"]["faixa_atual"]), não hardcoded.
- Relatórios gerados por Dojo (evita vazar dados entre unidades).
- data/cadastro/ mapeia aluno_id → dojo_id para o roteamento.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from core import engine, relatorios
from core.omr_reader import processar_imagem
from core.parser import parse_arquivo

QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]
FAIXA_FALLBACK = "branca"
DOJO_FALLBACK = "D01"

def processar_gabaritos(pasta: Path, base_cfg: Path) -> list[dict]:
    """Roda o OMR em cada imagem e devolve a lista de JSONs v2.0.

    A faixa é lida do QR Code (dados["aluno"]["faixa_atual"]); se o QR
    não trouxer faixa, usa FAIXA_FALLBACK. Folhas com erro são registradas
    e ignoradas — não derrubam o lote.
    """
    jsons = []
    for img in sorted(pasta.glob("*.jpg")) + sorted(pasta.glob("*.png")):
        try:
            dados = processar_imagem(img, base_cfg)  # faixa vem do QR
            dados["aluno"]["faixa_atual"] = (
                dados["aluno"].get("faixa_atual") or FAIXA_FALLBACK
            )
            jsons.append(dados)
        except ValueError as exc:
            print(f"[ERRO] {img.name}: {exc}")
    return jsons

def carregar_cadastro(pasta: Path) -> dict[str, dict]:
    """Lê data/cadastro/*.json e devolve {aluno_id: registro}.

    O cadastro associa cada aluno ao seu Dojo (dojo_id) — usado para
    rotear os relatórios sem vazar dados entre unidades.
    """
    cadastro: dict[str, dict] = {}
    if not pasta.exists():
        return cadastro
    for arq in sorted(pasta.glob("*.json")):
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[ERRO] cadastro {arq.name}: {exc}")
            continue
        registros = dados if isinstance(dados, list) else dados.get("alunos", [dados])
        for reg in registros:
            aluno_id = reg.get("aluno_id") or reg.get("id")
            if aluno_id:
                cadastro[str(aluno_id)] = reg
    return cadastro

def agrupar_por_aluno(jsons: list[dict]) -> dict[str, list[dict]]:
    """Agrupa os JSONs dos avaliadores por aluno_id."""
    grupos: dict[str, list[dict]] = defaultdict(list)
    for dados in jsons:
        grupos[dados["aluno"]["id"]].append(dados)
    return dict(grupos)

def dojo_do_aluno(aluno_id: str, cadastro: dict[str, dict]) -> str:
    """Devolve o dojo_id do aluno (fallback: DOJO_FALLBACK + aviso)."""
    reg = cadastro.get(aluno_id)
    if not reg:
        print(f"[AVISO] aluno {aluno_id} sem cadastro — usando dojo {DOJO_FALLBACK}")
        return DOJO_FALLBACK
    return reg.get("dojo_id") or DOJO_FALLBACK

def _chamar_relatorio(nome: str, *args) -> str | None:
    """Chama core/relatorios.<nome>(*args) se existir (camadas 2 e 3)."""
    fn = getattr(relatorios, nome, None)
    if fn is None:
        print(f"[AVISO] core/relatorios não expõe {nome}() — camada ignorada")
        return None
    return fn(*args)

def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline Karate-Ashi v2.0")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--output", type=Path, default=Path("output"))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # 1. Entrada: imagens OMR + fallback TXT
    jsons = processar_gabaritos(args.data / "gabaritos", args.config)
    if (args.data / "input.txt").exists():
        jsons += parse_arquivo(args.data / "input.txt", args.config)

    cadastro = carregar_cadastro(args.data / "cadastro")

    # 2. Agrupar por aluno e calcular notas por faixa
    resultados = []
    for aluno_id, avaliacoes in agrupar_por_aluno(jsons).items():
        faixa = avaliacoes[0]["aluno"]["faixa_atual"].lower()
        try:
            resultado = engine.processa_aluno(avaliacoes, args.config, faixa)
        except ValueError as exc:
            print(f"[ERRO] aluno {aluno_id}: {exc}")
            continue
        resultados.append({
            "aluno": avaliacoes[0]["aluno"],
            "dojo_id": dojo_do_aluno(aluno_id, cadastro),
            "resultado": resultado,
        })

    if not resultados:
        print("[ERRO] Nenhum aluno processado — verifique gabaritos e cadastro.")
        return 1

    # 3. Relatórios (3 camadas)
    regras = engine.carregar_json(args.config / "regras_gerais.json")
    recomendacoes = engine.carregar_json(args.config / "recomendacoes.json")

    por_dojo: dict[str, list[dict]] = defaultdict(list)
    for item in resultados:
        por_dojo[item["dojo_id"]].append(item)

    # Camada 1 — individual, por Dojo (distribuído pelo notifications.py)
    for dojo_id, itens in por_dojo.items():
        with open(args.output / f"relatorio_individual_{dojo_id}.txt",
                  "w", encoding="utf-8") as fh:
            for item in itens:
                fh.write(relatorios.relatorio_individual(
                    item["resultado"], regras, recomendacoes, item["aluno"]))
                fh.write("\n\n---\n\n")

    # Consolidado — apenas arquivo local (NÃO é distribuído: evita vazamento)
    with open(args.output / "relatorio_individual.txt", "w", encoding="utf-8") as fh:
        for item in resultados:
            fh.write(relatorios.relatorio_individual(
                item["resultado"], regras, recomendacoes, item["aluno"]))
            fh.write("\n\n---\n\n")

    # Camada 2 — consolidado por Dojo
    for dojo_id, itens in por_dojo.items():
        texto = _chamar_relatorio("relatorio_dojo", itens, regras, recomendacoes)
        if texto:
            (args.output / f"relatorio_dojo_{dojo_id}.txt").write_text(
                texto, encoding="utf-8")

    # Camada 3 — relatório dos Mestres (global, não sai por Dojo)
    texto = _chamar_relatorio("relatorio_master", resultados, regras, recomendacoes)
    if texto:
        (args.output / "relatorio_master.txt").write_text(texto, encoding="utf-8")

    print(f"Processados {len(resultados)} alunos em {len(por_dojo)} dojo(s). "
          f"Relatórios em {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())