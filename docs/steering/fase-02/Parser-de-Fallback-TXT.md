
0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTE
   Dev Python Sênior — parsing com re, código defensivo.
   Engenheiro SRE/DevOps — validação rígida de entrada, logs, rejeição com mensagem clara.
   Analista Pedagógico de Karatê — conhece os critérios por quesito.
   Regras de conduta: use SEMPRE os valores deste documento e da Fase 00; se algo não estiver especificado, PERGUNTE antes de assumir; não reabra decisões aprovadas; ao final, preencha o checklist.1. ObjetivoRefatorar o parser de contingência (core/parser.py) para o novo formato TXT v2.0: códigos relativos ao quesito, frequência por repetição de código, 4 observações granulares (uma por quesito) e cabeçalho com exame/dojo/avaliador/aluno/faixa. Saída: JSON intermediário no schema v2.0, um por avaliador.2. Contexto mínimo do projetoO TXT é o canal manual de contingência (quando não há imagem OMR). Antes, o formato usava códigos globais A1–A12 e 1 observação geral. Agora os códigos são relativos ao quesito e cada quesito tem sua observação. O parser valida os códigos contra a tabela da Fase 00 (config/criterios_por_quesito.json) e rejeita códigos fora do intervalo do quesito.3. Decisões aprovadas (não reabrir)
   Mapeamento por quesito (número → critério): conforme config/criterios_por_quesito.json (Kihon 1–6; Kata 1–8; Bunkai 1–8; Kumite 1–7).
   Frequência representada por repetição: cod:1,1,1 = 3 ocorrências do critério 1.
   Tags de observação: Observação Kihon:, Observação Kata:, Observação Bunkai:, Observação Kumite:.
   Código fora do intervalo válido → rejeita a linha e grava aviso no log (não aborta o arquivo inteiro).
   Blocos separados por ---; um bloco = um avaliador avaliando um aluno.
1. Tarefas
   Criar core/parser.py conforme código de referência (seção 5).
   Criar tests/test_parser.py: parse válido, código inválido, observações granulares.
   Criar data/exemplo_fallback_v2.txt com 1 aluno de exemplo (validar parse).
   Executar testes e registrar no Status.
2. Código de referênciaExemplo de arquivo TXT v2.0 (data/exemplo_fallback_v2.txt):




---
EXAME: EXA-D01-2026-02
DOJO: D01
AVALIADOR: S01
ALUNO: A01 | Isabelly Santos
FAIXA: BRANCA -> AMARELA

KIHON: cod:1,1,1,2,4
Observação Kihon: Corrigir largura no Zenkutsu-dachi.
KATA: cod:2,5
Observação Kata: Boa velocidade, ajustar rotação.
BUNKAI: cod:7
Observação Bunkai: Distância muito curta na aplicação.
KUMITE: cod:3
Observação Kumite: Manter guarda alta durante esquivas.
---



`core/parser.py`:


"""core/parser.py — Parser do fallback TXT v2.0 (contingência manual).

Formato por bloco (separador ---):
    EXAME: ...
    DOJO: ...
    AVALIADOR: ...
    ALUNO: <id></id> | <nome></nome>
    FAIXA: <atual></atual> -> <pretendida></pretendida>
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
RE_OBS = re.compile(r"^Observação\s+(Kihon|Kata|Bunkai|Kumite):\s*(.*)$",
                    re.IGNORECASE)

def carregar_criterios(base_cfg: Path) -> dict:
    """Carrega a tabela da Fase 00 e devolve 'max_codigo' por quesito."""
    cfg = json.loads((base_cfg / "criterios_por_quesito.json").read_text(
        encoding="utf-8"))
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

def parse_bloco(bloco: str, max_codigos: dict[str, int]) -> dict:
    """Parseia um bloco (avaliador + aluno) e devolve o JSON v2.0."""
    linhas = [ln.strip() for ln in bloco.strip().splitlines() if ln.strip()]
    metadados: dict[str, str] = {}
    avaliacoes: dict[str, dict] = {q: {"frequencias": {}, "observacao": ""}
                                   for q in QUESITOS}

    for linha in linhas:
        m = RE_QUESITO.match(linha)
        if m:
            quesito = m.group(1).lower()
            codigos = _extrair_codigos(m.group(2))
            max_cod = max_codigos[quesito]
            for cod in codigos:
                if not 1 <= cod <= max_cod:
                    log.warning("código %s fora do intervalo do quesito %s "
                                "(max %s) — linha rejeitada", cod, quesito, max_cod)
                    continue
                chave = _chave_do_codigo(quesito, cod)
                avaliacoes[quesito]["frequencias"][chave] = 
                    avaliacoes[quesito]["frequencias"].get(chave, 0) + 1
            continue
        m = RE_OBS.match(linha)
        if m:
            avaliacoes[m.group(1).lower()]["observacao"] = m.group(2)
            continue
        if ":" in linha:
            chave, _, valor = linha.partition(":")
            metadados[chave.strip().lower()] = valor.strip()

    alunoid, _, alunonome = metadados.get("aluno", "|").partition("|")
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
            "faixa_atual": metadados.get("faixa", "").split("->")[0].strip(),
            "faixa_pretendida": (metadados.get("faixa", "").split("->")[1]
                                 .strip() if "->" in metadados.get("faixa", "")
                                 else ""),
        },
        "avaliacoes": avaliacoes,
    }

def _chave_do_codigo(quesito: str, cod: int) -> str:
    """Devolve a chave do critério. Valores são FIXOS da especificação v2.0."""
    tabela = {
        "kihon":  {1: "base_incorreta", 2: "execucao_tecnica_incorreta",
                   3: "movimento_sem_carga", 4: "falta_foco",
                   5: "perda_equilibrio", 6: "ausencia_kiai"},
        "kata":   {1: "embusen_incorreto", 2: "base_incorreta",
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
    return tabela[quesito][cod]

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


6. Critérios de aceite
   Parse do exemplo_fallback_v2.txt retorna JSON v2.0 com frequencias corretas (ex: cod:1,1,1 → base_incorreta: 3).
   As 4 observações granulares são capturadas nos campos corretos.
   Código inválido (ex: KIHON: cod:7) gera aviso no log e não aborta o arquivo.
   Cabeçalho (exame, dojo, avaliador, aluno, faixa) parseado corretamente.
   tests/test_parser.py criado e passando.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
