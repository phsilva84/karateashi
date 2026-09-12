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

Códigos legados (item 4):
- a validação usa a tabela da FAIXA (config/faixas/<faixa>.json), não a
  tabela v1 de config/criterios_por_quesito.json;
- código fora da tabela do quesito NÃO derruba a linha: é retido em
  'codigos_descartados' e o bloco recebe 'dados_legados': true, para o
  relatório alertar. Motivo: código descartado = penalidade que não é
  aplicada = nota maior que a real (erro a favor do aluno);
- se o bloco declarar 'FORMATO: v2.0' e ainda assim tiver código fora da
  tabela, é bug novo -> ValueError, não dado legado.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

log = logging.getLogger("karate-ashi.parser")

QUESITOS = ["kihon", "kata", "bunkai", "kumite"]
FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]

RE_QUESITO = re.compile(r"^(KIHON|KATA|BUNKAI|KUMITE):\s*cod:(.*)$", re.IGNORECASE)
RE_OBS = re.compile(
    r"^Observação\s+(Kihon|Kata|Bunkai|Kumite):\s*(.*)$", re.IGNORECASE
)
RE_FAIXA = re.compile(r"^FAIXA:\s*(.*)$", re.IGNORECASE)

def carregar_criterios(base_cfg: Path, faixa: str) -> dict:
    """Carrega a tabela de critérios da faixa (config/faixas/<faixa>.json).

    Devolve {quesito: {"por_codigo": {codigo: chave}, "total": n}}.
    Levanta ValueError se o arquivo não existir ou for placeholder.
    """
    faixa = str(faixa or "").strip().lower()
    caminho = base_cfg / "faixas" / f"{faixa}.json"
    if not caminho.exists():
        raise ValueError(
            f"faixa '{faixa}' não possui arquivo de configuração "
            f"(config/faixas/{faixa}.json)")
    cfg = json.loads(caminho.read_text(encoding="utf-8"))
    if cfg.get("nao_suportada", False):
        raise ValueError(f"faixa '{faixa}' não suportada nesta versão")

    tabela: dict[str, dict] = {}
    for quesito, dados in cfg["quesitos"].items():
        por_codigo = {int(c["codigo"]): c["chave"]
                      for c in dados.get("criterios", [])}
        tabela[quesito] = {"por_codigo": por_codigo, "total": len(por_codigo)}
    return tabela

def _extrair_codigos(texto: str) -> list[int]:
    """Transforma '1,1,3' em [1,1,3]. Erros viram exceção com mensagem clara."""
    if not texto.strip():
        return []
    try:
        return [int(x) for x in texto.split(",") if x.strip() != ""]
    except ValueError as exc:
        raise ValueError(f"código inválido na linha 'cod:{texto}'") from exc

def _faixa_do_bloco(bloco: str) -> str:
    """Extrai a faixa ATUAL (antes do '->') da linha FAIXA: do bloco."""
    for linha in bloco.strip().splitlines():
        m = RE_FAIXA.match(linha.strip())
        if m:
            return [p.strip() for p in m.group(1).split("->")][0].lower()
    return ""

def _separar_linhas(bloco: str) -> tuple[dict[str, str], list[str]]:
    """Separa metadados (linhas 'CHAVE: valor') das linhas de código/observação.

    Duas passagens são necessárias para conhecer o FORMATO declarado ANTES
    de validar os códigos (legado x bug novo).
    """
    metadados: dict[str, str] = {}
    linhas: list[str] = []
    for linha in (ln.strip() for ln in bloco.strip().splitlines()):
        if not linha:
            continue
        linhas.append(linha)
        if RE_QUESITO.match(linha) or RE_OBS.match(linha):
            continue
        if ":" in linha:
            chave, _, valor = linha.partition(":")
            metadados[chave.strip().lower()] = valor.strip()
    return metadados, linhas

def parse_bloco(bloco: str, criterios: dict[str, dict]) -> dict:
    """Parseia um bloco (avaliador + aluno) e devolve o JSON v2.0.

    'criterios' é a tabela da faixa (ver carregar_criterios).
    """
    metadados, linhas = _separar_linhas(bloco)
    formato = metadados.get("formato", "").strip().lower()

    avaliacoes: dict[str, dict] = {
        q: {"frequencias": {}, "observacao": ""} for q in QUESITOS
    }
    descartados: dict[str, list[int]] = {}

    for linha in linhas:
        m = RE_QUESITO.match(linha)
        if m:
            quesito = m.group(1).lower()
            tabela = criterios.get(quesito)
            if tabela is None:
                raise ValueError(f"quesito sem tabela na faixa: {quesito}")
            validos = tabela["por_codigo"]
            for cod in _extrair_codigos(m.group(2)):
                if cod not in validos:
                    if formato == "v2.0":
                        # Arquivo declara v2.0 e tem código fora da tabela:
                        # é defeito novo, não dado legado.
                        raise ValueError(
                            f"código {cod} fora da tabela do quesito "
                            f"{quesito} em arquivo declarado v2.0")
                    descartados.setdefault(quesito, []).append(cod)
                    log.warning(
                        "código %s fora da tabela de %s (%s válidos) — "
                        "descartado e sinalizado como legado",
                        cod, quesito, sorted(validos),
                    )
                    continue
                chave = validos[cod]
                freq = avaliacoes[quesito]["frequencias"]
                freq[chave] = freq.get(chave, 0) + 1
            continue

        m = RE_OBS.match(linha)
        if m:
            avaliacoes[m.group(1).lower()]["observacao"] = m.group(2)
            continue

    alunoid, _, alunonome = metadados.get("aluno", "|").partition("|")
    faixas = [p.strip() for p in metadados.get("faixa", "").split("->")]
    resultado = {
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
    # Observação única do bloco (sem quesito) — capturada em vez de perdida.
    if metadados.get("observação"):
        resultado["observacao_geral"] = metadados["observação"]
    if descartados:
        resultado["dados_legados"] = True
        resultado["codigos_descartados"] = descartados
    return resultado

def parse_arquivo(caminho_txt: Path, base_cfg: Path) -> list[dict]:
    """Lê o TXT e devolve JSONs v2.0, um por bloco avaliador+aluno.

    A tabela de critérios é carregada por faixa (lida do próprio bloco) e
    cacheada, para não reler o JSON a cada bloco.
    """
    conteudo = caminho_txt.read_text(encoding="utf-8")
    blocos = [b for b in conteudo.split("---") if b.strip()]
    cache: dict[str, dict] = {}
    saida: list[dict] = []

    for bloco in blocos:
        try:
            faixa = _faixa_do_bloco(bloco)
            if faixa not in FAIXAS_SUPORTADAS:
                raise ValueError(f"faixa '{faixa}' não suportada no TXT")
            if faixa not in cache:
                cache[faixa] = carregar_criterios(base_cfg, faixa)
            dados = parse_bloco(bloco, cache[faixa])
            if dados.get("dados_legados"):
                log.warning(
                    "bloco com dados legados (%s): códigos descartados %s — "
                    "nota pode estar incompleta",
                    dados["aluno"].get("id") or dados["aluno"].get("nome"),
                    dados["codigos_descartados"],
                )
            saida.append(dados)
        except ValueError as exc:
            log.error("bloco rejeitado: %s", exc)
    return saida