"""core/pipeline.py — integração OMR → engine (agrega por aluno).

Fluxo:
  JSONs do OMR (output/omr) -> carregar_jsons_omr -> agregar_por_aluno
  -> montar_lote_engine (interpretação de frequência) -> processa_aluno
  -> resultado por aluno (nota, status, obs automáticas, frequências brutas).

Interpretação de frequência (decisão de negócio):
  modo_presenca=True (padrão): qualquer balão marcado conta como 1 ocorrência
  do defeito (aprovação mais leniente). As contagens brutas (1..5) são
  preservadas em 'frequencias_brutas' para planejamento de treinos, sem
  afetar o cálculo da nota.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from core.engine import carregar_faixa, processa_aluno
from core import observacoes_automaticas


def _indice_posicional(chave: str) -> int | None:
    """Reconhece chaves 'c1'..'cN' do OMR e devolve o índice 0-based."""
    m = re.fullmatch(r"c(\d+)", chave.strip().casefold())
    return int(m.group(1)) - 1 if m else None


def _nome_criterio(criterio: dict, indice: int) -> str:
    """Resolve o nome canônico de um critério da matriz de faixa.

    Tenta 'chave' (nome normalizado); sem isso, deriva um slug do 'nome';
    em último caso mantém a posição ('cN').
    """
    if isinstance(criterio, str):
        return criterio
    for campo in ("chave", "nome_normalizado", "slug"):
        if criterio.get(campo):
            return criterio[campo]
    nome = criterio.get("nome")
    if nome:
        acentos = {"ç": "c", "ã": "a", "õ": "o", "á": "a", "é": "e",
                   "í": "i", "ó": "o", "ú": "u", "â": "a", "ê": "e", "ô": "o"}
        return ("".join(acentos.get(c, c) for c in nome.strip().lower())
                .replace(" ", "_").replace("-", "_"))
    return f"c{indice + 1}"


def converter_frequencias_omr(folha: dict, matriz_faixa: dict,
                              modo_presenca: bool = True) -> dict:
    """Converte as chaves posicionais (c1..cN) do OMR em nomes de critérios.

    A matriz da faixa é a fonte única de interpretação: a posição N da
    leitura óptica corresponde SEMPRE ao critério N da matriz vigente.

    modo_presenca=True (padrão): qualquer balão marcado conta como 1
    ocorrência (interpretação B — aprovação mais leniente).
    modo_presenca=False: mantém a contagem bruta (1..5) multiplicando o peso.
    """
    convertidas = {}
    for quesito, bloco in folha.get("avaliacoes", {}).items():
        criterios = (matriz_faixa.get("quesitos", {})
                     .get(quesito, {}).get("criterios", []))
        novo: dict[str, int] = {}
        for chave, contagem in bloco.get("frequencias", {}).items():
            indice = _indice_posicional(chave)
            if indice is not None and indice < len(criterios):
                nome = _nome_criterio(criterios[indice], indice)
            else:
                nome = chave  # já é nome canônico (ou chave desconhecida)
            if modo_presenca:
                novo[nome] = 1 if int(contagem) > 0 else 0
            else:
                novo[nome] = novo.get(nome, 0) + int(contagem)
        convertidas[quesito] = novo
    return convertidas


def carregar_jsons_omr(pasta_omr: Path) -> list[dict]:
    """Lê todos os JSONs de folhas gerados pelo ingest_folhas."""
    if not pasta_omr.is_dir():
        return []
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(pasta_omr.glob("*.json"))
        if p.name != "resumo_ingestao.json"
    ]


def agregar_por_aluno(folhas: list[dict]) -> dict[str, list[dict]]:
    """Agrupa as folhas pelo aluno_id — uma lista de avaliadores por aluno."""
    grupos: dict[str, list[dict]] = {}
    for folha in folhas:
        grupos.setdefault(folha["aluno"]["id"], []).append(folha)
    return grupos


def montar_lote_engine(aluno_id: str, faixa_raw: str,
                       avaliadores: list[dict], matriz: dict) -> list[dict]:
    """Monta a lista de avaliadores no schema que o processa_aluno espera.

    As frequências posicionais do OMR viram nomes de critérios pela matriz;
    o primeiro avaliador carrega o bloco 'aluno' com a faixa normalizada.
    """
    faixa = (faixa_raw or "").strip().lower()
    lote = []
    for i, av in enumerate(avaliadores):
        bloco = {
            "avaliacoes": {
                q: {
                    "frequencias": converter_frequencias_omr(
                        {"avaliacoes": {q: {"frequencias": av.get(
                            "avaliacoes", {}).get(q, {}).get("frequencias", {})}}},
                        matriz,
                    ).get(q, {}),
                    "observacao": av.get("avaliacoes", {}).get(q, {})
                    .get("observacao", ""),
                }
                for q in matriz.get("quesitos", {})
            }
        }
        if av.get("observacao_montada"):
            bloco["observacao_geral"] = av["observacao_montada"]
        if av.get("dados_legados"):
            bloco["dados_legados"] = True
        if av.get("codigos_descartados"):
            bloco["codigos_descartados"] = av["codigos_descartados"]
        if i == 0:
            bloco["aluno"] = {"id": aluno_id, "faixa_atual": faixa}
        lote.append(bloco)
    return lote


def consolidar_frequencias_brutas(avaliadores: list[dict]) -> dict:
    """Soma as frequências brutas (contagens 1..5) de todos os avaliadores.

    Usado para planejamento de treinos: preserva o dado real de intensidade
    por critério, sem afetar o cálculo da nota (que usa presença).
    """
    consolidado: dict[str, dict[str, int]] = {}
    for av in avaliadores:
        for quesito, bloco in av.get("avaliacoes", {}).items():
            for chave, freq in bloco.get("frequencias", {}).items():
                consolidado.setdefault(quesito, {})
                consolidado[quesito][chave] = (
                    consolidado[quesito].get(chave, 0) + int(freq)
                )
    return consolidado


def processar_folhas_omr(pasta_omr: Path, cfg: Path) -> list[dict]:
    """Fluxo completo: lê os JSONs do ingest, agrega por aluno e processa."""
    folhas = carregar_jsons_omr(pasta_omr)
    resultados = []
    for aluno_id, avaliadores in agregar_por_aluno(folhas).items():
        faixa = (avaliadores[0].get("metadados", {}).get("faixa")
                 or "branca").strip().lower()
        # REGRA: presença não marcada -> AUSENTE (não avaliar frequências).
        # Se QUALQUER avaliador marcou ausente, o aluno é AUSENTE.
        if any(av.get("presenca") != "PRESENTE" for av in avaliadores):
            resultados.append({
                "aluno_id": aluno_id,
                "faixa": faixa,
                "status": "AUSENTE",
                "status_bruto": "AUSENTE",
                "nota_final": 0.0,
                "origens": [av.get("origem") for av in avaliadores],
                "quesitos": {},
                "observacoes": [],
                "observacoes_automaticas": [],
                "frequencias_brutas": consolidar_frequencias_brutas(
                    avaliadores),
            })
            continue
        # carregar_faixa devolve o dict interno de QUESITOS (sem a chave
        # "quesitos"); as funções do pipeline esperam o envelope do JSON.
        matriz = {"quesitos": carregar_faixa(cfg, faixa)}
        lote = montar_lote_engine(aluno_id, faixa, avaliadores, matriz)
        resultado = processa_aluno(lote, cfg, faixa)
        resultado["aluno_id"] = aluno_id
        resultado["origens"] = [av.get("origem") for av in avaliadores]
        resultado["observacoes_automaticas"] = gerar_obs_automaticas_do_aluno(
            avaliadores, cfg)
        resultado["frequencias_brutas"] = consolidar_frequencias_brutas(
            avaliadores)
        resultados.append(resultado)
    return resultados


def gerar_obs_automaticas_do_aluno(avaliadores: list[dict], cfg: Path) -> list[dict]:
    """Gera observações automáticas a partir das frequências do OMR.

    Consolida as frequências de todos os avaliadores do aluno (soma por
    critério) e aplica as regras do módulo observacoes_automaticas.
    """
    # Consolida as frequências somando os avaliadores
    consolidado: dict[str, dict[str, int]] = {}
    for av in avaliadores:
        for quesito, bloco in av.get("avaliacoes", {}).items():
            for chave, freq in bloco.get("frequencias", {}).items():
                consolidado.setdefault(quesito, {})
                consolidado[quesito][chave] = (
                    consolidado[quesito].get(chave, 0) + int(freq)
                )
    faixa = (avaliadores[0].get("metadados", {}).get("faixa")
             or "branca").strip().lower()
    # Monta o dict no formato que o módulo espera
    resultado = {
        "avaliacoes": {
            q: {"frequencias": consolidado.get(q, {})}
            for q in consolidado
        },
        "aluno": {"faixa_atual": faixa},
    }
    return observacoes_automaticas.merge_no_json(resultado, cfg)[
        "observacoes_automaticas"
    ]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pipeline Karate-Ashi: OMR -> engine (agrega por aluno)")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--output", type=Path, default=Path("output"))
    ap.add_argument("--omr", type=Path, default=None,
                    help="pasta dos JSONs do OMR (default: <output>/omr)")
    args = ap.parse_args()

    pasta_omr = args.omr or (args.output / "omr")
    resultados = processar_folhas_omr(pasta_omr, args.config)

    if not resultados:
        print(f"[AVISO] Nenhum JSON de OMR encontrado em {pasta_omr}")
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    for r in resultados:
        aluno_id = r.get("aluno_id", "desconhecido")
        caminho = args.output / f"resultado_{aluno_id}.json"
        caminho.write_text(json.dumps(r, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        chaves = ", ".join(sorted(r.keys()))
        print(f"[OK] {aluno_id}: {chaves}")
    print(f"Pipeline concluído: {len(resultados)} aluno(s) em {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())