"""tools/importar_cadastro.py — Importa alunos de CSV e faz merge idempotente
no data/cadastro/alunos.json (por ID). Cria registros novos com defaults e
atualiza faixas/dojo de IDs existentes sem apagar histórico.

CSV (encoding utf-8-sig; separador auto-detectado: vírgula, ';' ou TAB):
  id,nome,faixa_atual,faixa_pretendida,dojo_id
  W01,Heloisa Brandao Araujo,branca,amarela,D01

Uso:
  python tools/importar_cadastro.py data/cadastro/alunos.csv
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CADASTRO = RAIZ / "data" / "cadastro" / "alunos.json"

CAMPOS_CSV = ["id", "nome", "faixa_atual", "faixa_pretendida", "dojo_id"]
CAMPOS_FAIXA = {"faixa_atual", "faixa_pretendida"}
DEFAULTS = {"novo": False, "ativo": True, "ultima_promocao": None,
            "historico_promocoes": []}


def carregar() -> list[dict]:
    if not CADASTRO.exists():
        return []
    return json.loads(CADASTRO.read_text(encoding="utf-8"))["alunos"]


def salvar(alunos: list[dict]) -> None:
    CADASTRO.write_text(
        json.dumps({"alunos": alunos}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def detectar_delimitador(caminho: Path) -> str:
    """Detecta o separador real do CSV (vírgula, ';' ou TAB)."""
    with open(caminho, encoding="utf-8-sig", newline="") as fh:
        amostra = fh.read(4096)
    try:
        return csv.Sniffer().sniff(amostra, delimiters=",;\t").delimiter
    except csv.Error:
        return ","  # fallback


def importar(linhas: list[dict]) -> tuple[list[str], list[str]]:
    alunos = carregar()
    por_id = {a["id"]: a for a in alunos}
    criados, atualizados = [], []
    for linha in linhas:
        ident = str(linha["id"]).strip()
        if not ident:
            continue
        dados = {}
        for c in CAMPOS_CSV[1:]:
            valor = str(linha[c]).strip() if c in linha and linha[c] else ""
            if valor:
                # faixas normalizadas em caixa baixa (engine usa minúsculas)
                dados[c] = valor.lower() if c in CAMPOS_FAIXA else valor
        if ident in por_id:
            por_id[ident].update(dados)
            atualizados.append(ident)
        else:
            por_id[ident] = {"id": ident, **dados, **DEFAULTS}
            criados.append(ident)
    salvar(list(por_id.values()))
    return criados, atualizados


def validar_cabecalho(colunas: list[str]) -> list[str]:
    return [c for c in CAMPOS_CSV if c not in colunas]


def main() -> int:
    if len(sys.argv) != 2:
        print("uso: python tools/importar_cadastro.py <arquivo.csv>")
        return 2
    arquivo = Path(sys.argv[1])
    delim = detectar_delimitador(arquivo)
    with open(arquivo, encoding="utf-8-sig", newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=delim)
        faltando = validar_cabecalho(leitor.fieldnames or [])
        if faltando:
            print(f"[ERRO] colunas ausentes no CSV: {', '.join(faltando)}")
            return 1
        linhas = list(leitor)
    criados, atualizados = importar(linhas)
    print(f"criados: {len(criados)} | atualizados: {len(atualizados)}")
    print("novos:", ", ".join(criados) or "-")
    print("atualizados:", ", ".join(atualizados) or "-")
    print(f"delimitador detectado: {delim!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())