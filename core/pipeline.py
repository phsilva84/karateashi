"""core/pipeline.py — trecho de integração OMR → engine (adicionar ao módulo)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.engine import carregar_faixa, processa_aluno


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


def converter_frequencias_omr(folha: dict, matriz_faixa: dict) -> dict:
    """Converte as chaves posicionais (c1..cN) do OMR em nomes de critérios.

    A matriz da faixa é a fonte única de interpretação: a posição N da
    leitura óptica corresponde SEMPRE ao critério N da matriz vigente.
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


def processar_folhas_omr(pasta_omr: Path, cfg: Path) -> list[dict]:
    """Fluxo completo: lê os JSONs do ingest, agrega por aluno e processa."""
    folhas = carregar_jsons_omr(pasta_omr)
    matriz = carregar_faixa(cfg, "branca")  # default; a faixa real vem do QR
    resultados = []
    for aluno_id, avaliadores in agregar_por_aluno(folhas).items():
        faixa = (avaliadores[0].get("metadados", {}).get("faixa")
                 or "branca").strip().lower()
        lote = montar_lote_engine(aluno_id, faixa, avaliadores, matriz)
        resultado = processa_aluno(lote, cfg, faixa)
        resultado["aluno_id"] = aluno_id
        resultado["origens"] = [av.get("origem") for av in avaliadores]
        # NOVO: observações automáticas derivadas das frequências do OMR
        resultado["observacoes_automaticas"] = gerar_obs_automaticas_do_aluno(
            avaliadores, cfg)
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