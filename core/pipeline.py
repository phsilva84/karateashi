"""core/pipeline.py — Integração OMR → engine → relatórios (Karate-Ashi v2.0).

Orquestra: lê os JSONs gerados pelo ingest_folhas (OMR), agrega as folhas por
aluno (múltiplos avaliadores), chama o motor (core.engine.processa_aluno) por
faixa e gera os relatórios visuais (HTML) por exame/finalidade.

Semântica de frequências:
  - NOTAS (modo_presenca=True, padrão): qualquer balão marcado conta como 1
    por critério — um avaliador contribui no máx. 1 ocorrência por critério.
    Comportamento validado pelos testes (interpretação por presença).
  - RELATÓRIOS (modo_presenca=False): o pipeline também grava as frequências
    REAIS (escala 1 a 5) por critério e por avaliador
    (resultado["frequencias_reais"], resultado["frequencias_por_avaliador"]),
    usadas pelo relatório Master (intensidade média) e pela tabela de
    marcações do Sensei.

Presença: folha com presença AUSENTE → aluno AUSENTE, sem avaliar frequências.

Nomes: relatórios usam o nome COMPLETO (data/cadastro/alunos.json). As FOLHAS
usam abreviar_nome() (ex.: "Pedro J. Silva") por causa do espaço limitado.

Nomes de saída (um arquivo por exame — suporta vários exames no ano):
  output/relatorios/relatorio_sensei_{EXAME}_{DOJO}.html   (camada Sensei)
  output/relatorios/relatorio_master_{EXAME}.html          (master consolidado)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Garante que a raiz do projeto esteja no sys.path ao rodar direto
# (python core/pipeline.py) — mesmo padrão do tools/ingest_folhas.py.
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from core import observacoes_automaticas
from core.config import carregar_json
from core.engine import carregar_faixa, processa_aluno
from core.relatorio_html import salvar_html_exame, salvar_html_master


def _indice_posicional(chave: str) -> int | None:
    """Reconhece chaves 'c1'..'cN' do OMR e devolve o índice 0-based."""
    m = re.fullmatch(r"c(\d+)", chave.strip().casefold())
    return int(m.group(1)) - 1 if m else None


def _nome_criterio(criterio, indice: int) -> str:
    """Resolve o nome canônico de um critério da matriz de faixa."""
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


def _quesitos_da_matriz(matriz: dict) -> dict:
    """Extrai o dict de quesitos da matriz de faixa.

    Suporta dois formatos:
      {'quesitos': {...}}   (wrapper — usado nos testes/fixtures)
      {kihon:..., kata:...} (estrutura real de config/faixas/<faixa>.json)
    """
    if isinstance(matriz, dict) and "quesitos" in matriz:
        return matriz["quesitos"]
    return matriz or {}


def converter_frequencias_omr(folha: dict, matriz_faixa: dict,
                              modo_presenca: bool = True) -> dict:
    """Converte as chaves posicionais (c1..cN) do OMR em nomes de critérios.

    A matriz da faixa é a fonte única de interpretação: a posição N da
    leitura óptica corresponde SEMPRE ao critério N da matriz vigente.

    modo_presenca=True (padrão): qualquer balão marcado conta como 1
    (interpretação por presença — um avaliador contribui no máx. 1 por
    critério, independente da contagem bruta do OMR).
    modo_presenca=False: preserva a contagem bruta (cN: N).
    """
    convertidas = {}
    for quesito, bloco in folha.get("avaliacoes", {}).items():
        criterios = (_quesitos_da_matriz(matriz_faixa)
                     .get(quesito, {}).get("criterios", []))
        novo: dict[str, int] = {}
        for chave, contagem in bloco.get("frequencias", {}).items():
            indice = _indice_posicional(chave)
            if indice is not None and indice < len(criterios):
                nome = _nome_criterio(criterios[indice], indice)
            else:
                nome = chave  # já é nome canônico (ou chave desconhecida)
            if modo_presenca:
                novo[nome] = 1
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

    As frequências posicionais do OMR viram nomes de critérios pela matriz
    (modo_presenca: 1 por critério por avaliador); o primeiro avaliador
    carrega o bloco 'aluno' com a faixa normalizada.
    """
    faixa = (faixa_raw or "").strip().lower()
    quesitos = _quesitos_da_matriz(matriz)
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
                for q in quesitos
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


def gerar_obs_automaticas_do_aluno(avaliadores: list[dict], cfg: Path) -> list[dict]:
    """Gera observações automáticas a partir das frequências do OMR.

    Consolida as frequências de todos os avaliadores do aluno (soma por
    critério) e aplica as regras do módulo observacoes_automaticas.
    """
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


def _mapear_avaliador(av: dict, i: int) -> str:
    """Resolve o id do avaliador de uma folha OMR."""
    md = av.get("metadados") or {}
    return (md.get("avaliador") or md.get("avaliador_id")
            or md.get("id_avaliador") or av.get("avaliador") or f"A{i + 1}")


def _frequencias_reais_aluno(avaliadores: list[dict], matriz: dict):
    """Frequências REAIS (escala 1 a 5) por critério — soma e por avaliador."""
    freq_reais: dict[str, dict[str, int]] = {}
    freq_por_av: list[dict] = []
    av_ids: list[str] = []
    for i, av in enumerate(avaliadores):
        conv = converter_frequencias_omr(av, matriz, modo_presenca=False)
        freq_por_av.append(conv)
        av_ids.append(_mapear_avaliador(av, i))
        for q, blocos in conv.items():
            for ch, cont in blocos.items():
                freq_reais.setdefault(q, {})
                freq_reais[q][ch] = freq_reais[q].get(ch, 0) + int(cont)
    return freq_reais, freq_por_av, av_ids


def _observacoes_por_avaliador(avaliadores: list[dict]) -> list[dict]:
    return [
        {
            "avaliador": _mapear_avaliador(av, i),
            "observacao": av.get("observacao_montada") or "",
        }
        for i, av in enumerate(avaliadores)
    ]


def processar_folhas_omr(pasta_omr: Path, cfg: Path) -> list[dict]:
    """Fluxo completo: lê os JSONs do ingest, agrega por aluno e processa.

    Aluno com TODAS as folhas AUSENTE → status AUSENTE (sem avaliar
    frequências). Caso contrário, monta o lote e chama o motor.
    """
    folhas = carregar_jsons_omr(pasta_omr)
    matriz = carregar_faixa(cfg, "branca")  # default; a faixa real vem do QR
    resultados = []
    for aluno_id, avaliadores in agregar_por_aluno(folhas).items():
        faixa = (avaliadores[0].get("metadados", {}).get("faixa")
                 or "branca").strip().lower()
        # Presença: todas as folhas do aluno com presenca=AUSENTE → AUSENTE
        if all((av.get("presenca") or "PRESENTE") == "AUSENTE"
               for av in avaliadores):
            resultados.append({
                "aluno_id": aluno_id,
                "faixa": faixa,
                "status": "AUSENTE",
                "nota_final": 0.0,
                "quesitos": {},
                "origens": [av.get("origem") for av in avaliadores],
                "observacoes_automaticas": [],
                "observacoes_por_avaliador": _observacoes_por_avaliador(avaliadores),
                "frequencias_reais": {},
                "frequencias_por_avaliador": [],
                "avaliadores_ids": [_mapear_avaliador(av, i)
                                    for i, av in enumerate(avaliadores)],
            })
            continue
        lote = montar_lote_engine(aluno_id, faixa, avaliadores, matriz)
        resultado = processa_aluno(lote, cfg, faixa)
        resultado["aluno_id"] = aluno_id
        resultado["origens"] = [av.get("origem") for av in avaliadores]
        # NOVO: observações automáticas derivadas das frequências do OMR
        resultado["observacoes_automaticas"] = gerar_obs_automaticas_do_aluno(
            avaliadores, cfg)
        # NOVO: observações por avaliador (com autoria)
        resultado["observacoes_por_avaliador"] = _observacoes_por_avaliador(avaliadores)
        # NOVO: frequências reais (escala 1 a 5) para os relatórios
        freq_reais, freq_por_av, av_ids = _frequencias_reais_aluno(avaliadores, matriz)
        resultado["frequencias_reais"] = freq_reais
        resultado["frequencias_por_avaliador"] = freq_por_av
        resultado["avaliadores_ids"] = av_ids
        resultados.append(resultado)
    return resultados


# ═══ Metadados do exame + relatórios visuais por finalidade ═════════════════

def _slug(texto: str, padrao: str = "sem_id") -> str:
    """Sanitiza um id (exame/dojo) para uso seguro em nome de arquivo."""
    limpo = re.sub(r"[^A-Za-z0-9._-]+", "-", str(texto or "")).strip("-._")
    return limpo or padrao


def _extrair_metadados_exame(folhas: list[dict]) -> tuple[str, str, str]:
    """Extrai exame_id, dojo_id e avaliador_id dos metadados (QR do exame)."""
    for f in folhas:
        md = f.get("metadados") or {}
        exame = (md.get("exame") or md.get("exame_id")
                 or md.get("id_exame") or "sem_exame")
        dojo = (md.get("dojo") or md.get("dojo_id")
                or md.get("id_dojo") or "sem_dojo")
        av = (md.get("avaliador") or md.get("avaliador_id")
              or md.get("id_avaliador") or "")
        return str(exame), str(dojo), str(av)
    return "sem_exame", "sem_dojo", ""


# --- Cadastro (nomes de alunos e senseis responsáveis) ----------------------

def _carregar_doc_cadastro(cadastro: Path, arquivo: str):
    """Carrega um JSON de cadastro de forma tolerante (ou None)."""
    p = cadastro / arquivo
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _lista_registros(doc) -> list[dict]:
    """Normaliza um doc de cadastro em lista de registros.

    Aceita: lista direta, {alunos/registros/dojos/avaliadores/itens: [...]},
    ou dict de id -> registro.
    """
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for chave in ("alunos", "registros", "dojos", "avaliadores", "itens"):
            v = doc.get(chave)
            if isinstance(v, list):
                return v
        if doc and all(isinstance(v, dict) for v in doc.values()):
            return list(doc.values())
    return []


def _carregar_nomes(cadastro: Path) -> dict[str, str]:
    """Mapa aluno_id -> nome completo (data/cadastro/alunos.json ou .csv)."""
    nomes: dict[str, str] = {}
    doc = _carregar_doc_cadastro(cadastro, "alunos.json")
    if doc is not None:
        for reg in _lista_registros(doc):
            rid = (reg.get("id") or reg.get("aluno_id") or reg.get("codigo") or "")
            nome = (reg.get("nome") or reg.get("nome_completo")
                    or reg.get("name") or "")
            if rid and nome:
                nomes[str(rid)] = str(nome)
    if not nomes:
        csvp = cadastro / "alunos.csv"
        if csvp.exists():
            try:
                with csvp.open(newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        rid = row.get("id") or row.get("aluno_id") or ""
                        nome = row.get("nome") or row.get("nome_completo") or ""
                        if rid and nome:
                            nomes[rid.strip()] = nome.strip()
            except Exception:
                pass
    return nomes


def _carregar_senseis_por_dojo(cfg: Path) -> dict[str, str]:
    """Mapa dojo_id -> sensei responsável (config/dojos.json)."""
    mapa: dict[str, str] = {}
    p = cfg / "dojos.json"
    if not p.exists():
        return mapa
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return mapa
    for reg in _lista_registros(doc):
        did = (reg.get("id") or reg.get("dojo_id") or reg.get("codigo") or "")
        sensei = (reg.get("sensei") or reg.get("sensei_responsavel")
                  or reg.get("responsavel") or "")
        if did and sensei:
            mapa[str(did)] = str(sensei)
    return mapa


def _carregar_avaliadores(cadastro: Path, cfg: Path | None = None) -> dict[str, str]:
    """Mapa avaliador_id -> nome — data/cadastro/avaliadores.json ou config/avaliadores.json."""
    mapa: dict[str, str] = {}
    for base in (cadastro, cfg):
        if base is None:
            continue
        doc = _carregar_doc_cadastro(base, "avaliadores.json")
        if doc is None:
            continue
        for reg in _lista_registros(doc):
            aid = (reg.get("id") or reg.get("avaliador_id") or reg.get("codigo") or "")
            nome = (reg.get("nome") or reg.get("nome_completo") or "")
            if aid and nome:
                mapa[str(aid)] = str(nome)
        if mapa:
            break
    return mapa
def gerar_relatorios_html(resultados: list[dict], regras: dict,
                          recomendacoes: dict, exame_id: str, dojo_id: str,
                          rel_dir: Path, nomes: dict | None = None,
                          sensei_responsavel: str = "",
                          avaliadores_map: dict | None = None) -> list[Path]:
    """Gera os relatórios HTML por finalidade, com o exame no nome do arquivo.

    Nomes (1 arquivo por exame — suporta vários exames no ano):
      relatorio_sensei_{exame}_{dojo}.html   — camada Sensei (individuais)
      relatorio_master_{exame}.html          — master consolidado (multi-dojo)
    """
    rel_dir.mkdir(parents=True, exist_ok=True)
    gerados: list[Path] = []

    ex = _slug(exame_id)
    dj = _slug(dojo_id, "sem_dojo")

    p_sensei = salvar_html_exame(
        resultados, regras, recomendacoes,
        rel_dir / f"relatorio_sensei_{ex}_{dj}.html",
        dojo_id=dojo_id, exame_id=exame_id,
        titulo=f"Relatório do Sensei — Exame {exame_id}",
        nomes=nomes, sensei_responsavel=sensei_responsavel,
        avaliadores_map=avaliadores_map,
    )
    gerados.append(p_sensei)

    dojos = [{"dojo_id": dojo_id, "alunos": resultados}]
    p_master = salvar_html_master(
        dojos, regras, recomendacoes,
        rel_dir / f"relatorio_master_{ex}.html",
        exame_id=exame_id,
        titulo=f"Relatório Master Consolidado — Exame {exame_id}",
        nomes=nomes, avaliadores_map=avaliadores_map,
    )
    gerados.append(p_master)

    print(f"[OK] Relatórios gerados ({len(gerados)}):")
    for p in gerados:
        print(f"     {p}")
    return gerados


def main(argv: list[str] | None = None) -> int:
    """CLI: python core/pipeline.py --config config --data data --output output [--pasta-omr ...]"""
    ap = argparse.ArgumentParser(
        description="Pipeline Karate-Ashi v2.0 (OMR → engine → relatórios)")
    ap.add_argument("--config", type=Path, default=Path("config"),
                    help="pasta de configuração (config/)")
    ap.add_argument("--data", type=Path, default=Path("data"),
                    help="pasta de dados (cadastro/gabaritos)")
    ap.add_argument("--output", type=Path, default=Path("output"),
                    help="pasta de saída (output/)")
    ap.add_argument("--pasta-omr", type=Path, default=None,
                    help="pasta com os JSONs do OMR (padrão: <output>/json)")
    args = ap.parse_args(argv)

    cfg = args.config
    output = args.output
    pasta_omr = args.pasta_omr or (output / "json")
    rel_dir = output / "relatorios"
    cadastro = args.data / "cadastro" if (args.data / "cadastro").is_dir() else args.data

    if not pasta_omr.is_dir():
        print(f"[ERRO] Pasta de JSONs OMR não encontrada: {pasta_omr}")
        return 2

    regras = carregar_json(cfg / "regras_gerais.json")
    recomendacoes = carregar_json(cfg / "recomendacoes.json")

    folhas = carregar_jsons_omr(pasta_omr)
    exame_id, dojo_id, avaliador_id = _extrair_metadados_exame(folhas)
    print(f"[INFO] Exame: {exame_id} | Dojo: {dojo_id} | Folhas: {len(folhas)}")

    # Nomes dos alunos + sensei responsável (config/dojos.json) + avaliadores
    nomes = _carregar_nomes(cadastro)
    senseis = _carregar_senseis_por_dojo(cfg)
    avaliadores = _carregar_avaliadores(cadastro)
    sensei_responsavel = (senseis.get(dojo_id)
                          or avaliadores.get(avaliador_id)
                          or avaliador_id or "")

    resultados = processar_folhas_omr(pasta_omr, cfg)
    print(f"[OK] Alunos processados: {len(resultados)}")

    gerar_relatorios_html(resultados, regras, recomendacoes,
                          exame_id, dojo_id, rel_dir,
                          nomes=nomes, sensei_responsavel=sensei_responsavel,
                          avaliadores_map=avaliadores)
    return 0


if __name__ == "__main__":
    sys.exit(main())