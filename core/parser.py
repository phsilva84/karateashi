"""core/parser.py — Parser do fallback TXT v2.0 (contingência manual).

Formato por bloco (separador ---):
    EXAME: ...
    DOJO: ...
    AVALIADOR: ...
    ALUNO: <id> | <nome>
    FAIXA: <atual> -> <pretendida>
    KIHON: cod:1,1,3
    Observação Kihon: ...
    KATA: cod:2
    Observação Kata: ...
    BUNKAI: cod:7
    Observação Bunkai: ...
    KUMITE: cod:3
    Observação Kumite: ...

Saída: JSON intermediário schema v2.0, um dict por avaliador+aluno.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("karate-ashi.parser")

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]

RE_QUESITO = re.compile(r"^(KIHON|KATA|BUNKAI|KUMITE):\s*cod:(.*)$", re.IGNORECASE)
RE_OBS = re.compile(
    r"^Observação\s+(Kihon|Kata|Bunkai|Kumite):\s*(.*)$", re.IGNORECASE
)

def carregar_criterios(base_cfg: Path) -> dict:
    """Carrega a tabela da Fase 00 e devolve 'max_codigo' por quesito."""
    cfg = json.loads(
        (base_cfg / "criterios_por_quesito.json").read_text(encoding="utf-8")
    )
    return {q: len(cfg["quesitos"][q]["criterios"]) for q in QUESITOS}

def _extrair_codigos(texto: str) -> list[int]:
    """Transforma '1,1,3' em [1,1,3]. Erros viram exceção com mensagem clara."""
    if not texto.strip():
        return []
    try:
        codigos = [int(x) for x in texto.split(",") if x.strip() != ""]
    except ValueError as exc:
        raise ValueError(f"código inválido na linha 'cod:{texto}'") from exc
    return codigos

def _chave_do_codigo(quesito: str, cod: int) -> str | None:
    """Devolve a chave do critério. Valores são FIXOS da especificação v2.0."""
    tabela = {
        "kihon": {1: "base_incorreta", 2: "execucao_tecnica_incorreta",
                  3: "movimento_sem_carga", 4: "falta_foco",
                  5: "perda_equilibrio", 6: "ausencia_kiai"},
        "kata": {1: "embusen_incorreto", 2: "base_incorreta",
                 3: "falta_ritmo", 4: "ausencia_kiai",
                 5: "execucao_tecnica_incorreta", 6: "movimento_sem_carga",
                 7: "falta_foco", 8: "perda_equilibrio"},
        "bunkai": {1: "base_incorreta", 2: "ausencia_kiai",
                   3: "execucao_tecnica_incorreta", 4: "movimento_sem_carga",
                   5: "falta_foco", 6: "perda_equilibrio",
                   7: "distancia_inadequada", 8: "falta_controle"},
        "kumite": {1: "movimento_sem_carga", 2: "falta_foco",
                   3: "perda_equilibrio", 4: "ausencia_kiai",
                   5: "distancia_inadequada", 6: "falta_combatividade",
                   7: "falta_controle"},
    }
    return tabela.get(quesito, {}).get(cod)

def parse_bloco(bloco: str, max_codigos: dict[str, int]) -> dict:
    """Parseia um bloco (avaliador + aluno) e devolve o JSON v2.0."""
    linhas = [ln.strip() for ln in bloco.strip().splitlines() if ln.strip()]
    metadados: dict[str, str] = {}
    avaliacoes: dict[str, dict] = {
        q: {"frequencias": {}, "observacao": ""} for q in QUESITOS
    }

    for linha in linhas:
        m = RE_QUESITO.match(linha)
        if m:
            quesito = m.group(1).lower()
            codigos = _extrair_codigos(m.group(2))
            max_cod = max_codigos[quesito]
            for cod in codigos:
                if not 1 <= cod <= max_cod:
                    log.warning(
                        "código %s fora do intervalo do quesito %s (max %s) — "
                        "linha rejeitada", cod, quesito, max_cod,
                    )
                    continue
                chave = _chave_do_codigo(quesito, cod)
                if chave is None:
                    log.warning(
                        "código %s sem mapeamento no quesito %s — ignorado",
                        cod, quesito,
                    )
                    continue
                freq = avaliacoes[quesito]["frequencias"]
                freq[chave] = freq.get(chave, 0) + 1
            continue

        m = RE_OBS.match(linha)
        if m:
            avaliacoes[m.group(1).lower()]["observacao"] = m.group(2)
            continue

        if ":" in linha:
            chave, _, valor = linha.partition(":")
            metadados[chave.strip().lower()] = valor.strip()

    alunoid, _, alunonome = metadados.get("aluno", "|").partition("|")
    faixas = [parte.strip() for parte in metadados.get("faixa", "").split("->")]
    return {
        "metadados": {
            "versao_schema": "2.0",
            "exame_id": metadados.get("exame", ""),
            "dojo_id": metadados.get("dojo", ""),
            "avaliador_id": metadados.get("avaliador", ""),
        },
        "aluno": {
            "id": alunoid.strip(),
            "nome": alunonome.strip(),
            "faixa_atual": faixas[0] if faixas else "",
            "faixa_pretendida": faixas[1] if len(faixas) > 1 else "",
        },
        "avaliacoes": avaliacoes,
    }

def parse_arquivo(caminho_txt: Path, base_cfg: Path) -> list[dict]:
    """Lê o TXT e devolve uma lista de JSONs (um por bloco avaliador+aluno)."""
    max_codigos = carregar_criterios(base_cfg)
    conteudo = caminho_txt.read_text(encoding="utf-8")
    blocos = [b for b in conteudo.split("---") if b.strip()]
    saida = []
    for bloco in blocos:
        try:
            saida.append(parse_bloco(bloco, max_codigos))
        except ValueError as exc:
            log.error("bloco rejeitado: %s", exc)
    return saida

# core/parser.py — (trecho) Fase 06: usar a linha FAIXA do TXT.

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]

def parse_arquivo(caminho_txt: Path, base_cfg: Path) -> list[dict]:
    """Lê o TXT e devolve JSONs v2.0, cada um com a faixa do bloco."""
    max_codigos = carregar_criterios(base_cfg)  # mantido
    conteudo = caminho_txt.read_text(encoding="utf-8")
    blocos = [b for b in conteudo.split("---") if b.strip()]

    saida = []
    for bloco in blocos:
        try:
            dados = parse_bloco(bloco, max_codigos)
            faixa = dados["aluno"].get("faixa_atual", "").lower()
            if faixa not in FAIXAS_SUPORTADAS:
                raise ValueError(f"faixa '{faixa}' não suportada no TXT")
            saida.append(dados)
        except ValueError as exc:
            log.error("bloco rejeitado: %s", exc)
    return saida