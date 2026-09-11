"""tests/test_omr_validador.py — Testes das funções puras do OMR (Fase 03).

Não depende de imagem real: as ROIs são sintéticas (numpy).
Executar: python -m pytest tests/test_omr_validador.py -v
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.omr_reader import (
    classificar_checkbox,
    contar_marcacoes_linha,
    parse_payload_qr,
    validar_folha,
)

LIMIARES = {
    "limiar_vazio_max": 0.20,
    "limiar_suspeito_max": 0.40,
}

def _roi_sintetica(densidade: float, tamanho: int = 100) -> np.ndarray:
    """ROI BGR sintética com a fração pedida de pixels escuros (0,0,0)."""
    total = tamanho * tamanho
    escuros = int(round(total * densidade))
    img = np.full((tamanho, tamanho, 3), 255, dtype=np.uint8)
    img.reshape(-1, 3)[:escuros] = (0, 0, 0)
    return img

# --- classificar_checkbox ------------------------------------------------

class TestClassificarCheckbox:
    def test_vazio_abaixo_do_limiar(self):
        assert classificar_checkbox(_roi_sintetica(0.10), LIMIARES) == "vazio"

    def test_vazio_no_limite_exato(self):
        assert classificar_checkbox(_roi_sintetica(0.20), LIMIARES) == "vazio"

    def test_suspeito_acima_do_vazio(self):
        assert classificar_checkbox(_roi_sintetica(0.30), LIMIARES) == "suspeito"

    def test_suspeito_no_limite_exato(self):
        assert classificar_checkbox(_roi_sintetica(0.40), LIMIARES) == "suspeito"

    def test_marcado_acima_do_suspeito(self):
        assert classificar_checkbox(_roi_sintetica(0.60), LIMIARES) == "marcado"

    def test_marcado_total(self):
        assert classificar_checkbox(_roi_sintetica(1.00), LIMIARES) == "marcado"

# --- contar_marcacoes_linha ----------------------------------------------

class TestContarMarcacoesLinha:
    def test_contiguo_sem_avisos(self):
        classes = ["marcado", "marcado", "marcado",
                   "vazio", "vazio", "vazio", "vazio"]
        res = contar_marcacoes_linha(classes, LIMIARES)
        assert res["frequencia"] == 3
        assert res["avisos"] == []

    def test_nao_contiguo_gera_aviso(self):
        classes = ["marcado", "vazio", "marcado",
                   "vazio", "vazio", "vazio", "vazio"]
        res = contar_marcacoes_linha(classes, LIMIARES)
        assert res["frequencia"] == 2
        assert any("não-contígua" in a for a in res["avisos"])

    def test_suspeito_gera_aviso_de_revisao(self):
        classes = ["suspeito", "vazio", "vazio",
                   "vazio", "vazio", "vazio", "vazio"]
        res = contar_marcacoes_linha(classes, LIMIARES)
        assert res["frequencia"] == 0
        assert any("revisão manual" in a for a in res["avisos"])

    def test_sem_marcacoes(self):
        classes = ["vazio"] * 7
        res = contar_marcacoes_linha(classes, LIMIARES)
        assert res["frequencia"] == 0
        assert res["avisos"] == []

# --- validar_folha --------------------------------------------------------

class TestValidarFolha:
    def test_folha_em_branco_rejeitada(self):
        frequencias = {
            "kihon": {"base_incorreta": {"frequencia": 0, "avisos": []}},
            "kata": {"kata1": {"frequencia": 0, "avisos": []}},
            "bunkai": {"bunkai1": {"frequencia": 0, "avisos": []}},
            "kumite": {"kumite1": {"frequencia": 0, "avisos": []}},
        }
        erros = validar_folha(frequencias)
        assert any("nenhuma marcação" in e for e in erros)

    def test_limite_de_7_estourado(self):
        frequencias = {
            "kihon": {"base_incorreta": {"frequencia": 8, "avisos": []}},
        }
        erros = validar_folha(frequencias)
        assert any("mais de 7 marcações" in e for e in erros)

    def test_folha_valida_sem_erros(self):
        frequencias = {
            "kihon": {"base_incorreta": {"frequencia": 2, "avisos": []}},
            "kata": {"kata1": {"frequencia": 1, "avisos": []}},
            "bunkai": {"bunkai1": {"frequencia": 0, "avisos": []}},
            "kumite": {"kumite1": {"frequencia": 3, "avisos": []}},
        }
        assert validar_folha(frequencias) == []

# --- parse_payload_qr -----------------------------------------------------

class TestParsePayloadQr:
    def test_payload_valido(self):
        payload = "KA|DOJO-01|EXAME-2026-03|ALUNO-042|SENSEI-PAULO|BRANCA"
        meta = parse_payload_qr(payload)
        assert meta["versao_schema"] == "2.0"
        assert meta["dojo_id"] == "DOJO-01"
        assert meta["exame_id"] == "EXAME-2026-03"
        assert meta["aluno_id"] == "ALUNO-042"
        assert meta["avaliador_id"] == "SENSEI-PAULO"
        assert meta["faixa"] == "BRANCA"

    def test_payload_com_espacos(self):
        meta = parse_payload_qr(" KA | DOJO | EXAME | ALUNO | SENSEI | BRANCA ")
        assert meta["dojo_id"] == "DOJO"

    def test_prefixo_invalido(self):
        with pytest.raises(ValueError):
            parse_payload_qr("XX|DOJO|EXAME|ALUNO|SENSEI|B  RANCA")

    def test_numero_de_campos_invalido(self):
        with pytest.raises(ValueError):
            parse_payload_qr("KA|DOJO|EXAME|ALUNO")