"""core/observacoes.py — Captura digital da Observação do avaliador.

Por que não ler a folha: o OMR classifica densidade de pixels em checkboxes.
Escrita livre é ICR (reconhecimento de manuscrito), outra classe de problema,
com acurácia baixa em português. A rota oficial é a observação nascer digital,
no fim da prova; a folha impressa continua sendo o apoio visual do avaliador.

Formato por avaliador (data/observacoes/<exame>/<avaliador>.csv):

    aluno_id,nome,kihon,kata,bunkai,kumite
    A01,Isabelly,Chutes firmes.,,,
    A02,Nicole,,Boa concentração,,

Só as células preenchidas entram. A coluna 'nome' é apenas para leitura humana.

Codificação: os CSVs são lidos e escritos com utf-8-sig. O Excel grava com
BOM; sem isso, a primeira coluna vira '\ufeffaluno_id' e nenhum aluno casa.
Os JSONs continuam utf-8 puro (quem os escreve é o próprio Python).

Integração (Fase 03 -> Fase 05):
    from core import observacoes
    resultado = processar_imagem(...)          # JSON do OMR
    observacoes.merge_no_json(resultado)       # preenche avaliacoes[q]["observacao"]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

log = logging.getLogger("karate-ashi.observacoes")

QUESITOS = ("kihon", "kata", "bunkai", "kumite")
BASE_PADRAO = Path("data/observacoes")

def _limpar(texto: Any) -> str:
    """Remove espaços/quebras redundantes; devolve '' para vazio."""
    return " ".join(str(texto or "").split()).strip()

def pasta_exame(exame: str, base: Path = BASE_PADRAO) -> Path:
    return Path(base) / exame

def gerar_templates(exame: str, avaliadores: List[str], alunos: List[dict],
                    base: Path = BASE_PADRAO,
                    sobrescrever: bool = False) -> List[Path]:
    """Cria um CSV em branco por avaliador, já com aluno_id e nome.

    Nunca sobrescreve por padrão: se o arquivo já existe, ele é preservado
    (evita apagar observações já digitadas por engano).

    Escrita com utf-8-sig: o Excel detecta UTF-8 e exibe os acentos
    corretamente ao abrir o template.
    """
    destino = pasta_exame(exame, base)
    destino.mkdir(parents=True, exist_ok=True)
    gerados: List[Path] = []
    for avaliador in avaliadores:
        caminho = destino / f"{avaliador}.csv"
        if caminho.exists() and not sobrescrever:
            log.warning("template já existe, preservado: %s", caminho)
            continue
        with caminho.open("w", encoding="utf-8-sig", newline="") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(("aluno_id", "nome") + QUESITOS)
            for aluno in alunos:
                escritor.writerow([aluno.get("id", ""), aluno.get("nome", "")]
                                  + [""] * len(QUESITOS))
        gerados.append(caminho)
    return gerados

def carregar(exame: str, avaliador: str,
             base: Path = BASE_PADRAO) -> Dict[str, Dict[str, str]]:
    """Lê o CSV de um avaliador -> {aluno_id: {quesito: texto}}.

    Devolve {} se o arquivo não existir (ausência é normal, não erro).

    Leitura com utf-8-sig: remove o BOM do Excel se existir e também lê
    arquivos sem BOM — é estritamente mais seguro que utf-8 puro.
    """
    caminho = pasta_exame(exame, base) / f"{avaliador}.csv"
    if not caminho.exists():
        return {}
    por_aluno: Dict[str, Dict[str, str]] = {}
    with caminho.open(encoding="utf-8-sig", newline="") as fh:
        for linha in csv.DictReader(fh):
            aluno_id = _limpar(linha.get("aluno_id"))
            if not aluno_id:
                continue
            preenchidos = {q: _limpar(linha.get(q)) for q in QUESITOS}
            preenchidos = {q: t for q, t in preenchidos.items() if t}
            if preenchidos:
                por_aluno[aluno_id] = preenchidos
    return por_aluno

def merge_no_json(resultado: dict, base: Path = BASE_PADRAO,
                  avaliador: str | None = None,
                  exame: str | None = None) -> dict:
    """Preenche avaliacoes[quesito]['observacao'] no JSON v2.0 do OMR.

    O avaliador e o exame vêm dos metadados lidos do QR; podem ser
    sobrescritos por parâmetro quando o JSON vier de outra origem.
    """
    metadados = resultado.get("metadados", {})
    avaliador = avaliador or metadados.get("avaliador_id", "")
    exame = exame or metadados.get("exame_id", "")
    aluno_id = resultado.get("aluno", {}).get("id", "")

    textos = carregar(exame, avaliador, base).get(aluno_id, {})
    avaliacoes = resultado.get("avaliacoes", {})
    for quesito in QUESITOS:
        if quesito in avaliacoes:
            avaliacoes[quesito]["observacao"] = textos.get(quesito, "")
    if textos:
        log.info("observações aplicadas: %s/%s (%d quesito(s))",
                 exame, aluno_id, len(textos))
    return resultado

def consolidar(exame: str, avaliadores: List[str],
               base: Path = BASE_PADRAO) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Agrupa por aluno -> quesito -> avaliador, para a Fase 05."""
    consolidado: Dict[str, Dict[str, Dict[str, str]]] = {}
    for avaliador in avaliadores:
        for aluno_id, por_quesito in carregar(exame, avaliador, base).items():
            destino = consolidado.setdefault(
                aluno_id, {q: {} for q in QUESITOS})
            for quesito, texto in por_quesito.items():
                destino[quesito][avaliador] = texto
    return consolidado

def exportar_recortes(alinhada, coordenadas: dict, destino,
                      quesito: str | None = None,
                      prefixo: str = "") -> Path:
    """(Plano B) Recorta a caixa de Observação de um quesito para
    conferência humana.

    Usa a ROI 'observacao_<quesito>' gravada pelo pre_exame. Sem a ROI
    calibrada, falha com mensagem clara — o recorte não é determinístico.
    """
    chave = f"observacao_{quesito}" if quesito else "observacao"
    roi = coordenadas.get(chave)
    if not roi:
        raise ValueError(
            f"coordenadas sem a entrada '{chave}' — gere as folhas com "
            f"tools/pre_exame.py antes de usar o recorte (Plano B)")
    import cv2  # dependência opcional: só carrega se este caminho for usado
    x, y, w, h = (int(roi[k]) for k in ("x", "y", "w", "h"))
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / f"obs_{prefixo or 'aluno'}_{quesito or 'geral'}.png"
    cv2.imwrite(str(caminho), alinhada[y:y + h, x:x + w])
    return caminho

def _carregar_alunos(caminho: Path, dojo: str | None) -> List[dict]:
    cadastro = json.loads(Path(caminho).read_text(encoding="utf-8"))
    alunos = cadastro.get("alunos", [])
    if dojo:
        alunos = [a for a in alunos if a.get("dojo_id") == dojo]
    return alunos

def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Observações do exame — captura digital (Karate-Ashi v2.0)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="gera um CSV em branco por avaliador")
    t.add_argument("--exame", required=True)
    t.add_argument("--avaliadores", required=True)
    t.add_argument("--cadastro", type=Path,
                   default=Path("data/cadastro/alunos.json"))
    t.add_argument("--dojo")
    t.add_argument("--base", type=Path, default=BASE_PADRAO)
    t.add_argument("--sobrescrever", action="store_true")

    c = sub.add_parser("consolidar", help="lista as observações por aluno")
    c.add_argument("--exame", required=True)
    c.add_argument("--avaliadores", required=True)
    c.add_argument("--base", type=Path, default=BASE_PADRAO)

    args = parser.parse_args(argv)

    if args.cmd == "template":
        alunos = _carregar_alunos(args.cadastro, args.dojo)
        if not alunos:
            print(f"[ERRO] nenhum aluno em {args.cadastro}"
                  + (f" para o dojo {args.dojo}" if args.dojo else ""))
            return 2
        avaliadores = [a.strip() for a in args.avaliadores.split(",") if a.strip()]
        gerados = gerar_templates(args.exame, avaliadores, alunos,
                                  args.base, args.sobrescrever)
        print(f"Templates em {pasta_exame(args.exame, args.base)} | "
              f"gerados: {len(gerados)} | alunos por arquivo: {len(alunos)}")
        for caminho in gerados:
            print(f"  - {caminho}")
        return 0

    if args.cmd == "consolidar":
        avaliadores = [a.strip() for a in args.avaliadores.split(",") if a.strip()]
        dados = consolidar(args.exame, avaliadores, args.base)
        if not dados:
            print(f"[AVISO] nenhuma observação encontrada para {args.exame}")
            return 0
        for aluno_id, por_quesito in sorted(dados.items()):
            print(f"{aluno_id}:")
            for quesito, textos in por_quesito.items():
                for avaliador, texto in sorted(textos.items()):
                    print(f"  {quesito:6s} [{avaliador}] {texto}")
        return 0

    return 1

if __name__ == "__main__":
    raise SystemExit(main())