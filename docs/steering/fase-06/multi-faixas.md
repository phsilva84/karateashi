
FASE 06 — Estrutura Multi-Faixa (Branca a Azul + Placeholders)0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Modelador de Dados — JSON limpo, chaves consistentes, sem redundância; multi-arquivo por faixa.
Analista Pedagógico de Karatê — domínio de Kihon, Kata, Bunkai e Kumite; entende a progressão de faixas.
Dev Python Sênior — refatoração segura, compatibilidade com código existente, testes.
Regras de conduta:
Use SEMPRE a tabela da especificação v2.0 (abaixo). Nunca invente pesos ou critérios.
As 5 faixas (Branca, Amarela, Laranja, Verde, Azul) compartilham a MESMA tabela — os arquivos nascem idênticos.
Roxa, Marrom e Preta entram como placeholders com "nao_suportada": true.
Não reabra decisões aprovadas. Se algo não estiver especificado, PERGUNTE.
Ao final, preencha o checklist de aceite.

1. ObjetivoEstruturar o sistema para múltiplas faixas:
   Criar config/faixas/ com 5 arquivos de faixa (mesma tabela v2.0) + 3 placeholders.
   Criar config/coordenadas/ com um template de layout por faixa (para o OMR e o pré-exame).
   Atualizar core/engine.py, core/parser.py e core/omr_reader.py para receber o parâmetro faixa e carregar a configuração correta.
2. Contexto mínimo do projeto3. Decisões aprovadas (não reabrir)
   As 5 faixas Branca→Azul usam a mesma tabela de critérios (Seção 3 da especificação v2.0). Arquivos idênticos, estrutura pronta para divergir no futuro.
   Layout específico por faixa: cada faixa tem seu config/coordenadas/<faixa></faixa>.json (recalibração OMR por faixa — escolha sua).
   Roxa, Marrom e Preta: placeholders com "nao_suportada": true. Sistema avisa "faixa não suportada nesta versão".
3. Tarefas
   Criar config/faixas/branca.json, amarela.json, laranja.json, verde.json, azul.json (tabela v2.0 idêntica).
   Criar config/faixas/roxa.json, marrom.json, preta.json (placeholders).
   Criar config/coordenadas/branca.json (valores a calibrar) + cópias para as demais faixas.
   Atualizar core/engine.py: processa_aluno recebe faixa.
   Atualizar core/parser.py: usa linha FAIXA do TXT.
   Atualizar core/omr_reader.py: carrega config/coordenadas/<faixa></faixa>.json.
   Criar tests/test_faixas.py e executar.
4. Conteúdo dos arquivosconfig/faixas/branca.json (idêntico para amarela, laranja, verde, azul — trocar só o campo "faixa"):
5. {
   "versao_schema": "2.0.0",
   "faixa": "branca",
   "nao_suportada": false,
   "quesitos": {
   "kihon": {
   "nome": "Kihon", "pontos_base": 25.0,
   "criterios": [
   {"codigo": 1, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
   {"codigo": 2, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
   {"codigo": 3, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
   {"codigo": 4, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
   {"codigo": 5, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
   {"codigo": 6, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5}
   ]
   },
   "kata": {
   "nome": "Kata", "pontos_base": 25.0,
   "criterios": [
   {"codigo": 1, "chave": "embusen_incorreto", "nome": "Embusen Incorreto", "peso": 2.0},
   {"codigo": 2, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
   {"codigo": 3, "chave": "falta_ritmo", "nome": "Falta de Ritmo", "peso": 0.5},
   {"codigo": 4, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
   {"codigo": 5, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
   {"codigo": 6, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
   {"codigo": 7, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
   {"codigo": 8, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0}
   ]
   },
   "bunkai": {
   "nome": "Bunkai", "pontos_base": 25.0,
   "criterios": [
   {"codigo": 1, "chave": "base_incorreta", "nome": "Base Incorreta", "peso": 1.0},
   {"codigo": 2, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
   {"codigo": 3, "chave": "execucao_tecnica_incorreta", "nome": "Execução Técnica Incorreta", "peso": 1.0},
   {"codigo": 4, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
   {"codigo": 5, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
   {"codigo": 6, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
   {"codigo": 7, "chave": "distancia_inadequada", "nome": "Distância Inadequada", "peso": 1.0},
   {"codigo": 8, "chave": "falta_controle", "nome": "Falta de Controle / Risco", "peso": 2.5}
   ]
   },
   "kumite": {
   "nome": "Kumite", "pontos_base": 25.0,
   "criterios": [
   {"codigo": 1, "chave": "movimento_sem_carga", "nome": "Movimento sem Carga/Peso", "peso": 1.0},
   {"codigo": 2, "chave": "falta_foco", "nome": "Falta de Foco", "peso": 1.0},
   {"codigo": 3, "chave": "perda_equilibrio", "nome": "Perda de Equilíbrio", "peso": 1.0},
   {"codigo": 4, "chave": "ausencia_kiai", "nome": "Ausência de Kiai", "peso": 0.5},
   {"codigo": 5, "chave": "distancia_inadequada", "nome": "Distância Inadequada", "peso": 1.0},
   {"codigo": 6, "chave": "falta_combatividade", "nome": "Falta de Combatividade", "peso": 2.0},
   {"codigo": 7, "chave": "falta_controle", "nome": "Falta de Controle / Risco", "peso": 2.5}
   ]
   }
   }
   }

`config/faixas/roxa.json` (idêntico para marrom e preta — trocar o campo `"faixa"`):

{
  "versao_schema": "2.0.0",
  "faixa": "roxa",
  "nao_suportada": true,
  "quesitos": {}
}

`config/coordenadas/branca.json` (cópias para as demais faixas; valores `x, y, w, h` são relativos à imagem ALINHADA pós-perspectiva — **calibrar com folhas reais por faixa**):

{
  "versao_template": "branca_v1",
  "faixa": "branca",
  "pagina": "A4",
  "observacoes": "Valores x,y,w,h relativos à imagem alinhada (pós-perspectiva). Calibrar por faixa na fase de calibração OMR.",
  "kihon": {
    "base_incorreta": {"x": 0, "y": 0, "w": 350, "h": 30},
    "execucao_tecnica_incorreta": {"x": 0, "y": 0, "w": 350, "h": 30},
    "movimento_sem_carga": {"x": 0, "y": 0, "w": 350, "h": 30},
    "falta_foco": {"x": 0, "y": 0, "w": 350, "h": 30},
    "perda_equilibrio": {"x": 0, "y": 0, "w": 350, "h": 30},
    "ausencia_kiai": {"x": 0, "y": 0, "w": 350, "h": 30}
  },
  "kata": {},
  "bunkai": {},
  "kumite": {}
}

**Atualização em **`core/engine.py` (funções novas + mudança em `processa_aluno`):


"""core/engine.py — (trecho) suporte multi-faixa.

processa_aluno passa a receber faixa e carrega config/faixas/<faixa></faixa>.json.
"""
from __future__ import annotations

import json
from pathlib import Path

FAIXAS_SUPORTADAS = ["branca", "amarela", "laranja", "verde", "azul"]

def carregar_faixa(base_cfg: Path, faixa: str) -> dict:
    """Carrega a tabela da faixa. Erro claro se faltar ou não for suportada."""
    caminho = base_cfg / "faixas" / f"{faixa}.json"
    if not caminho.exists():
        raise ValueError(f"faixa '{faixa}' não possui arquivo de configuração")
    cfg = json.loads(caminho.read_text(encoding="utf-8"))
    if cfg.get("nao_suportada", False):
        raise ValueError(f"faixa '{faixa}' não suportada nesta versão "
                         f"(Roxa/Marrom/Preta) — sem processamento")
    return cfg["quesitos"]

def processa_aluno(avaliacoes: list[dict], base_cfg: Path, faixa: str) -> dict:
    """Mesmo fluxo da Fase 01, mas usando a tabela da faixa."""
    quesitos_cfg = carregar_faixa(base_cfg, faixa)
    regras = json.loads((base_cfg / "regras_gerais.json").read_text(encoding="utf-8"))

    resultados = {}
    soma = 0.0
    for quesito in ["kihon", "kata", "bunkai", "kumite"]:
        r = nota_quesito(avaliacoes, quesito,
                         quesitos_cfg[quesito]["criterios"], regras)
        resultados[quesito] = r
        soma += r["nota"]

    nota_final = round(soma, 1)
    return {
        "nota_final": nota_final,
        "status": classificar_status(nota_final, regras),
        "quesitos": resultados,
        "faixa": faixa,
    }


**Atualização em **`core/parser.py` (usar a linha FAIXA):



# No parse_bloco, a chave "faixa" já é capturada dos metadados.

# O parse_arquivo agora devolve também a faixa para o chamador:

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
            if faixa not in ["branca", "amarela", "laranja", "verde", "azul"]:
                raise ValueError(f"faixa '{faixa}' não suportada no TXT")
            saida.append(dados)
        except ValueError as exc:
            log.error("bloco rejeitado: %s", exc)
    return saida


**Atualização em **`core/omr_reader.py` (carregar coordenadas por faixa):

def processar_imagem(caminho_imagem: Path, base_cfg: Path, faixa: str) -> dict:
    """Fluxo completo com layout da faixa."""
    limiares = carregar_json(base_cfg / "omr_thresholds.json")
    coordenadas = carregar_json(base_cfg / "coordenadas" / f"{faixa}.json")
    imagem = cv2.imread(str(caminho_imagem))
    if imagem is None:
        raise ValueError(f"não foi possível abrir a imagem: {caminho_imagem}")
    alinhada = detectar_e_corrigir(imagem)
    payload = decodificar_qr(alinhada)
    if not payload:
        raise ValueError("QR Code não encontrado — folha inválida ou sem QR")
    metadados = parse_payload_qr(payload)
    # A faixa do QR deve bater com a faixa esperada (validação cruzada):
    if metadados.get("faixa", "").lower() != faixa.lower():
        raise ValueError(f"faixa do QR ({metadados.get('faixa')}) difere do "
                         f"layout carregado ({faixa})")
    # Segmentação usando coordenadas[quesito][chave] (restante idêntico à Fase 03)
    ...

`tests/test_faixas.py` (resumo dos casos):


import json
from pathlib import Path
import pytest

@pytest.mark.parametrize("faixa", ["branca", "amarela", "laranja",
                                   "verde", "azul"])
def test_faixas_suportadas_tem_tabela(faixa, base_cfg: Path):
    cfg = json.loads((base_cfg / "faixas" / f"{faixa}.json")
                     .read_text(encoding="utf-8"))
    assert cfg["nao_suportada"] is False
    assert set(cfg["quesitos"]) == {"kihon", "kata", "bunkai", "kumite"}
    assert len(cfg["quesitos"]["kihon"]["criterios"]) == 6
    assert len(cfg["quesitos"]["kata"]["criterios"]) == 8
    assert len(cfg["quesitos"]["bunkai"]["criterios"]) == 8
    assert len(cfg["quesitos"]["kumite"]["criterios"]) == 7

@pytest.mark.parametrize("faixa", ["roxa", "marrom", "preta"])
def test_faixas_placeholder_nao_suportadas(faixa, base_cfg: Path):
    cfg = json.loads((base_cfg / "faixas" / f"{faixa}.json")
                     .read_text(encoding="utf-8"))
    assert cfg["nao_suportada"] is True
    assert cfg["quesitos"] == {}

def test_coordenadas_por_faixa_existem(base_cfg: Path):
    for faixa in ["branca", "amarela", "laranja", "verde", "azul"]:
        assert (base_cfg / "coordenadas" / f"{faixa}.json").exists()



6. Critérios de aceite
   5 arquivos de faixa com a tabela v2.0 idêntica (6/8/8/7 critérios) e nao_suportada: false.
   3 placeholders (roxa/marrom/preta) com nao_suportada: true e quesitos: {}.
   5 templates de coordenadas criados em config/coordenadas/.
   engine.processa_aluno(...) aceita faixa e usa a tabela correta; erro claro para faixa não suportada.
   parser rejeita TXT com faixa fora das 5 suportadas.
   omr_reader carrega coordenadas por faixa e valida cruzada com o QR.
   tests/test_faixas.py passando.
7. Status
   Pendente · [ ] Em execução · [ ] Concluída (data: ___)
