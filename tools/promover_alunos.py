"""tools/promover_alunos.py — Promoção de faixa pós-exame (Karate-Ashi v2col-4.0).

Fecha o ciclo de vida: lê o relatório consolidado do exame, valida e atualiza
data/cadastro/alunos.json, registrando cada promoção no histórico do aluno.

Regras:
  - A faixa nova é SEMPRE a faixa_pretendida do cadastro: o cadastro define o
    alvo; o motor só decide se o aluno chegou lá.
  - Só promove status aprovado.
  - Valida que faixa_pretendida é a PRÓXIMA faixa em config/faixas.json. Pulo de
    faixa é reportado e NÃO promovido (--permitir-pulo libera, se intencional).
  - Idempotente: (aluno_id, exame_id) já no histórico não promove de novo.
  - Faixa terminal (Preta): não promove; registra a conclusão no histórico.

Segurança: DRY-RUN por padrão. Só grava com --aplicar (faz backup .bak antes).

Uso:
    python tools/promover_alunos.py --relatorio output/relatorio_consolidado_EXA-D01-2026-03.json
    python tools/promover_alunos.py --relatorio ... --diff output/promocao_diff.json
    python tools/promover_alunos.py --relatorio ... --aplicar
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import cadastro as cad  # noqa: E402

STATUS_APROVADO = ("aprovado", "aprovada", "aprovado(a)", "apto")
CAMPOS_ID = ("aluno_id", "aluno", "id")
CAMPOS_MEDIA = ("media_final", "media", "nota_final", "nota")
CAMPOS_STATUS = ("status", "resultado", "situacao")

def _primeiro(dicionario: dict, nomes, padrao=None):
    for nome in nomes:
        if dicionario.get(nome) is not None:
            return dicionario[nome]
    return padrao

def extrair_resultados(dados) -> tuple[str, list[dict]]:
    """Normaliza o relatório consolidado para (exame_id, resultados)."""
    if isinstance(dados, list):
        itens, exame_id = dados, ""
    else:
        itens = dados.get("alunos") or dados.get("resultados") or []
        exame_id = _primeiro(dados, ("exame_id", "exame"), "")
    resultados = []
    for item in itens:
        if isinstance(item, dict):
            resultados.append({
                "aluno_id": _primeiro(item, CAMPOS_ID, ""),
                "media": _primeiro(item, CAMPOS_MEDIA),
                "status": _primeiro(item, CAMPOS_STATUS, ""),
                "avaliadores": item.get("avaliadores")
                               or item.get("avaliador_ids") or [],
            })
    return str(exame_id), resultados

def _e_aprovado(status) -> bool:
    return cad.chave(status) in {cad.chave(s) for s in STATUS_APROVADO}

def promover(cadastro: list[dict], resultados: list[dict], ordem: list[str],
             exame_id: str, permitir_pulo: bool = False,
             hoje: str | None = None) -> tuple[list[dict], list[dict]]:
    """Aplica a promoção no cadastro em memória. Devolve (cadastro, diff)."""
    hoje = hoje or date.today().isoformat()
    por_id = {cad.chave(a.get("id")): a for a in cadastro}
    diff: list[dict] = []

    for resultado in resultados:
        aluno_id = str(resultado.get("aluno_id") or "").strip()
        aluno = por_id.get(cad.chave(aluno_id))

        if aluno is None:
            diff.append({"aluno_id": aluno_id, "nome": None, "de": None,
                         "para": None, "media": resultado.get("media"),
                         "acao": "erro",
                         "motivo": "aluno não está no cadastro"})
            continue

        linha = {"aluno_id": aluno.get("id"), "nome": aluno.get("nome"),
                 "de": aluno.get("faixa_atual"), "para": None,
                 "media": resultado.get("media"), "acao": "ignorado",
                 "motivo": ""}

        if not _e_aprovado(resultado.get("status")):
            linha["motivo"] = (f"status '{resultado.get('status')}' não promove "
                               f"(só aprovado)")
            diff.append(linha)
            continue

        if not aluno.get("ativo", True):
            linha["acao"] = "erro"
            linha["motivo"] = "aluno inativo no cadastro"
            diff.append(linha)
            continue

        historico = aluno.setdefault("historico_promocoes", [])

        if any(h.get("exame_id") == exame_id for h in historico):
            linha["acao"] = "ja_promovido"
            linha["motivo"] = f"exame {exame_id} já registrado no histórico"
            diff.append(linha)
            continue

        pretendida = aluno.get("faixa_pretendida")
        if not str(pretendida or "").strip():
            linha["acao"] = "erro"
            linha["motivo"] = "sem faixa_pretendida no cadastro"
            diff.append(linha)
            continue

        if cad.faixa_e_terminal(aluno.get("faixa_atual"), ordem):
            linha["acao"] = "terminal"
            linha["motivo"] = (f"faixa terminal ({aluno.get('faixa_atual')}) — "
                               f"sem promoção")
            historico.append({"tipo": "conclusao", "data": hoje,
                              "exame_id": exame_id,
                              "faixa": aluno.get("faixa_atual"),
                              "media_final": resultado.get("media"),
                              "avaliadores": resultado.get("avaliadores")})
            aluno["ultima_promocao"] = hoje
            diff.append(linha)
            continue

        esperada = cad.proxima_faixa(aluno.get("faixa_atual"), ordem)
        if cad.chave(esperada) != cad.chave(pretendida) and not permitir_pulo:
            linha["acao"] = "erro"
            linha["motivo"] = (f"faixa_pretendida '{pretendida}' não é a próxima "
                               f"na ordem (esperado '{esperada}')")
            diff.append(linha)
            continue

        faixa_anterior = aluno.get("faixa_atual")
        aluno["faixa_atual"] = pretendida
        aluno["faixa_pretendida"] = cad.proxima_faixa(pretendida, ordem)
        aluno["novo"] = False
        aluno["ultima_promocao"] = hoje
        historico.append({
            "tipo": "promocao",
            "data": hoje,
            "exame_id": exame_id,
            "faixa_anterior": faixa_anterior,
            "faixa_nova": pretendida,
            "media_final": resultado.get("media"),
            "avaliadores": resultado.get("avaliadores"),
        })
        linha["para"] = pretendida
        linha["acao"] = "promovido"
        diff.append(linha)

    return cadastro, diff

def _imprimir(diff: list[dict]) -> None:
    print(f"{'ação':14s} {'aluno':7s} {'nome':12s} {'de':9s} {'para':9s} "
          f"{'média':>6s}  motivo")
    print("-" * 110)
    for linha in diff:
        media = linha["media"]
        media_txt = f"{float(media):.1f}" if media is not None else "--"
        print(f"{linha['acao']:14s} {str(linha['aluno_id'] or '--'):7s} "
              f"{str(linha['nome'] or '--')[:12]:12s} "
              f"{str(linha['de'] or '--'):9s} {str(linha['para'] or '--'):9s} "
              f"{media_txt:>6s}  {linha['motivo']}")
    resumo: dict[str, int] = {}
    for linha in diff:
        resumo[linha["acao"]] = resumo.get(linha["acao"], 0) + 1
    print("\nResumo: " + " | ".join(f"{k}={v}" for k, v in sorted(resumo.items())))

def main() -> int:
    ap = argparse.ArgumentParser(description="Promoção de faixa pós-exame")
    ap.add_argument("--relatorio", required=True, type=Path,
                    help="relatório consolidado do exame (.json)")
    ap.add_argument("--cadastro", type=Path,
                    default=Path("data/cadastro/alunos.json"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--diff", type=Path, default=None,
                    help="grava o diff em JSON para revisão")
    ap.add_argument("--permitir-pulo", action="store_true",
                    help="permite promover mesmo pulando faixa")
    ap.add_argument("--aplicar", action="store_true",
                    help="grava no cadastro (padrão: dry-run)")
    args = ap.parse_args()

    ordem = cad.carregar_ordem_faixas(args.config)
    cadastro = cad.carregar_cadastro(args.cadastro)
    exame_id, resultados = extrair_resultados(cad.carregar_json(args.relatorio))

    if not exame_id:
        raise SystemExit("[ERRO] relatório sem 'exame_id' — a idempotência "
                         "depende dele. Corrija o consolidado ou informe via JSON.")

    print(f"Exame: {exame_id} | {len(resultados)} resultado(s) | "
          f"{len(cadastro)} aluno(s) no cadastro\n")
    cadastro, diff = promover(cadastro, resultados, ordem, exame_id,
                              permitir_pulo=args.permitir_pulo)
    _imprimir(diff)

    if args.diff:
        cad.salvar_json(args.diff, {"exame_id": exame_id, "linhas": diff})
        print(f"\nDiff gravado: {args.diff}")

    promovidos = [l for l in diff if l["acao"] == "promovido"]
    if not args.aplicar:
        print(f"\nDRY-RUN: nada foi gravado. {len(promovidos)} promoção(ões) "
              f"seriam aplicadas. Use --aplicar para efetivar.")
        return 0

    if not promovidos:
        print("\nNada a gravar (nenhuma promoção válida).")
        return 0

    backup = Path(str(args.cadastro) + ".bak")
    shutil.copy2(args.cadastro, backup)
    cad.salvar_json(args.cadastro, {"alunos": cadastro})
    print(f"\nCadastro atualizado ({len(promovidos)} promoção(ões)). "
          f"Backup: {backup}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())