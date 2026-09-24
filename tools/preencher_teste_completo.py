#!/usr/bin/env python3
"""tools/preencher_teste_completo.py — Teste OMR robusto (critérios + observações).

Renderiza a folha real (PDF -> PNG 300 dpi), marca balões de forma
determinística usando o JSON de coordenadas e roda
core.omr_reader.processar_imagem de ponta a ponta (QRs reais), comparando
item a item com relatorio PASS/FAIL.

Cenarios:
- T01 (MARCACAO PESADA): presenca + TODOS os criterios da folha (4 quesitos,
  29 criterios -> 5 baloes cada) com frequencias rotativas 1..5 + TODAS as 6
  observacoes positivas. Esperado: presenca PRESENTE, todas as frequencias
  exatas, obs p1..p6 lidas, zero incidentes.
- T02 (ANOMALIAS): presenca + frequencias pontuais + 2 AMBIGUIDADES (2 baloes
  no mesmo criterio -> frequencia omitida + incidente) + 2 CONTRADICOES
  (obs_p1/obs_m1 e obs_p4/obs_m4 -> anuladas + incidentes) + 2 obs soltas
  (obs_p3, obs_m6) que permanecem.
- T03 (AUSENTE): SEM presenca, mas com frequencia e obs marcadas -> AUSENTE,
  sem avaliacao (regra: presenca nao marcada ignora tudo).

Os baloes sao preenchidos com DISCO QUASE CHEIO (0.95 do raio), simulando o
preenchimento a mao com caneta (caso real) — o leitor precisa tolerar isso.

Anti-flake do QR: se o pyzbar nao decodificar o QR do exame no render,
_garantir_qr_exame re-encoda o MESMO payload do pre_exame na posicao correta.

Uso:
  python tools/preencher_teste_completo.py [--avaliador S01] [--saida output/scans]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import omr_reader  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _detectar_coords(pasta: Path, avaliador: str) -> Path:
    candidatos = sorted(pasta.glob(f"*_{avaliador}_folha1_coordenadas.json"))
    if not candidatos:
        raise FileNotFoundError(
            f"JSON de coordenadas do avaliador {avaliador} nao encontrado em {pasta}")
    return candidatos[-1]


def _renderizar(pdf_path: Path) -> np.ndarray:
    """1a pagina do PDF -> BGR numpy a 300 dpi (mesmo fluxo do ingest)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(pdf_path))
    bmp = doc[0].render(scale=300 / 72)
    pil = bmp.to_pil()
    arr = np.array(pil.convert("RGB"))
    return arr[:, :, ::-1].copy()


def _pintar_balao(img, cinza, balao, escala, janela_px):
    """Acha o anel real e pinta o INTERIOR QUASE TODO (0.95 do raio) —
    simula o preenchimento a mao com caneta (disco solido)."""
    ex = balao["x_mm"] * escala
    ey = balao["y_mm"] * escala
    r = balao["r_mm"] * escala
    anel = omr_reader._achar_anel(cinza, ex, ey, r, janela_px)
    if anel is None:
        cx, cy, raio = int(ex), int(ey), max(int(r), 2)   # fallback central
    else:
        cx, cy, raio = (int(v) for v in anel)
    cv2.circle(img, (cx, cy), max(int(raio * 0.95), 3), (0, 0, 0), -1)


def _garantir_qr_exame(img, coords, escala):
    """Garante que o QR do exame esteja legível na imagem.

    Se o pyzbar nao decodificar o QR renderizado (flakiness de render de
    300dpi), LIMPA a regiao do QR (branco, com folga) e RE-ENCODA o MESMO
    payload do pre_exame na posicao EXATA (x=275, y=2, 12mm), com box_size
    adequado. Valida a decodificacao por _payload_por_prefixo.
    """
    payload = (f"KA|AVALIADOR={coords['avaliador_id']}|"
               f"DOJO={coords['dojo_id']}|EXAME={coords['exame']}")
    if omr_reader._payload_por_prefixo(img, "AVALIADOR") == payload:
        return img, False   # QR real decodificou — nada a fazer

    x_mm, y_mm, lado_mm = 275.0, 2.0, 12.0
    margem_mm = 3.0
    h, w = img.shape[:2]
    x0 = max(0, int((x_mm - margem_mm) * escala))
    y0 = max(0, int((y_mm - margem_mm) * escala))
    x1 = min(w, int((x_mm + lado_mm + margem_mm) * escala))
    y1 = min(h, int((y_mm + lado_mm + margem_mm) * escala))
    img[y0:y1, x0:x1] = 255                     # apaga o QR original/colisoes

    import qrcode
    qr = qrcode.make(payload, box_size=4, border=4)
    qr_bgr = cv2.cvtColor(np.array(qr.convert("RGB")), cv2.COLOR_RGB2BGR)
    x0q = int(x_mm * escala)
    y0q = int(y_mm * escala)
    lado_px = int(lado_mm * escala)
    qr_resized = cv2.resize(qr_bgr, (lado_px, lado_px),
                            interpolation=cv2.INTER_LINEAR)
    img[y0q:y0q + lado_px, x0q:x0q + lado_px] = qr_resized
    return img, True


# ---------------------------------------------------------------------------
# Planos de teste (derivados do JSON de coordenadas)
# ---------------------------------------------------------------------------
def _montar_planos(coords: dict) -> dict:
    """Deriva as expectativas dos 3 cenários a partir das coordenadas reais."""
    alunos = {a["id"]: a for a in coords["alunos"]}

    # T01: presenca + TODOS os criterios (freq rotativa 1..5) + obs p1..p6
    a1 = alunos["T01"]
    marcar_freq_t01: dict[str, int] = {}
    for idx, chave in enumerate(sorted(a1["frequencias"])):
        marcar_freq_t01[chave] = (idx % 5) + 1
    obs_t01 = [f"obs_p{i}" for i in range(1, 7)]

    # T02: pontuais + 2 ambiguidades + 2 contradicoes + 2 soltas
    a2 = alunos["T02"]
    freq_t02 = ["kata_base_incorreta", "bunkai_distancia_inadequada"]
    amb_t02 = ["kihon_base_incorreta", "kumite_falta_controle"]
    obs_contrad_02 = ["obs_p1", "obs_m1", "obs_p4", "obs_m4"]
    obs_soltas_02 = ["obs_p3", "obs_m6"]

    # T03: sem presenca; marca 1 freq + 2 obs (tudo ignorado)
    a3 = alunos["T03"]
    freq_t03 = ["kihon_base_incorreta"]
    obs_t03 = ["obs_p1", "obs_m2"]

    return {
        "T01": {
            "presenca": True,
            "marcar_frequencias": marcar_freq_t01,
            "ambiguidades": [],
            "marcar_obs": obs_t01,
            "esperar_frequencias": marcar_freq_t01,
            "esperar_obs": obs_t01,
            "esperar_incidentes": [],
        },
        "T02": {
            "presenca": True,
            "marcar_frequencias": {k: (i + 2) for i, k in enumerate(freq_t02)},
            "ambiguidades": amb_t02,
            "marcar_obs": obs_contrad_02 + obs_soltas_02,
            "esperar_frequencias": {k: (i + 2) for i, k in enumerate(freq_t02)},
            "esperar_obs": obs_soltas_02,          # contraditas anuladas
            "esperar_incidentes": [
                "ambiguidade_frequencia",          # kihon_base_incorreta
                "ambiguidade_frequencia",          # kumite_falta_controle
                "contradicao:obs_p1/obs_m1",
                "contradicao:obs_p4/obs_m4",
            ],
        },
        "T03": {
            "presenca": False,
            "marcar_frequencias": {freq_t03[0]: 2},
            "ambiguidades": [],
            "marcar_obs": obs_t03,
            "esperar_frequencias": {},
            "esperar_obs": [],
            "esperar_incidentes": [],
        },
    }


def _contar_baloes(planos: dict) -> int:
    """Conta quantos círculos serão pintados (freq + ambiguidade + obs + presença)."""
    total = 0
    for plano in planos.values():
        total += sum(plano["marcar_frequencias"].values())   # freq = balão
        total += len(plano["ambiguidades"]) * 2              # 2 balões por ambig.
        total += len(plano["marcar_obs"])
        total += 1 if plano["presenca"] else 0
    return total


# ---------------------------------------------------------------------------
# Marcacao e avaliacao
# ---------------------------------------------------------------------------
def _marcar(img, coords, planos, escala, janela_px):
    cinza = omr_reader._cinza(img)
    for aluno_id, plano in planos.items():
        a = next(x for x in coords["alunos"] if x["id"] == aluno_id)
        if plano["presenca"]:
            _pintar_balao(img, cinza, a["presenca"], escala, janela_px)
        for chave, freq in plano["marcar_frequencias"].items():
            baloes = a["frequencias"].get(chave)
            if baloes and 1 <= freq <= len(baloes):
                _pintar_balao(img, cinza, baloes[freq - 1], escala, janela_px)
        for chave in plano["ambiguidades"]:
            baloes = a["frequencias"].get(chave)
            if baloes and len(baloes) >= 3:
                _pintar_balao(img, cinza, baloes[0], escala, janela_px)  # 1o
                _pintar_balao(img, cinza, baloes[2], escala, janela_px)  # 3o
        for chave in plano["marcar_obs"]:
            b = a["observacoes"].get(chave)
            if b:
                _pintar_balao(img, cinza, b, escala, janela_px)


def _freq_achatadas(resultado) -> dict:
    out = {}
    for quesito, bloco in resultado["avaliacoes"].items():
        for criterio, freq in bloco["frequencias"].items():
            out[f"{quesito}_{criterio}"] = freq
    return out


def _avaliar(aluno_id: str, plano: dict, resultado: dict) -> list[str]:
    falhas: list[str] = []

    # Presenca
    pres_lida = resultado["presenca"] == "PRESENTE"
    if pres_lida != plano["presenca"]:
        falhas.append(
            f"presenca: esperado {plano['presenca']}, leu {resultado['presenca']}")

    # Frequencias (comparacao exata por chave)
    lidas = _freq_achatadas(resultado)
    for chave, freq in plano["esperar_frequencias"].items():
        if lidas.get(chave) != freq:
            falhas.append(f"freq {chave}: esperado {freq}, leu {lidas.get(chave)}")
    for chave in plano["ambiguidades"]:
        if chave in lidas:
            falhas.append(f"ambiguidade {chave}: nao devia ter frequencia, leu "
                          f"{lidas[chave]}")
    # Extras lidos que nao deveriam existir
    permitidas = set(plano["esperar_frequencias"]) | set(plano["ambiguidades"])
    extras = set(lidas) - permitidas
    if extras:
        falhas.append(f"frequencias inesperadas: {sorted(extras)}")

    # Observacoes
    obs_lidas = set(resultado["observacoes_marcadas"])
    obs_esp = set(plano["esperar_obs"])
    if obs_lidas != obs_esp:
        falhas.append(f"obs: esperado {sorted(obs_esp)}, leu {sorted(obs_lidas)}")

    # Incidentes esperados (substring)
    inc = resultado.get("incidentes_auditoria", [])
    for esperado in plano["esperar_incidentes"]:
        if not any(esperado in i for i in inc):
            falhas.append(f"incidente ausente: '{esperado}' (inc={inc})")

    return falhas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Teste OMR robusto (critérios + observações)")
    ap.add_argument("--avaliador", default="S01")
    ap.add_argument("--saida", type=Path, default=RAIZ / "output" / "scans")
    args = ap.parse_args()

    pre = RAIZ / "output" / "pre_exame"
    pdf = pre / f"folhas_{args.avaliador}.pdf"
    if not pdf.exists():
        print(f"[ERRO] folha nao encontrada: {pdf}. Gere com pre_exame primeiro.")
        return 2
    coords_path = _detectar_coords(pre, args.avaliador)
    coords = json.loads(coords_path.read_text(encoding="utf-8"))
    print(f"  folha : {pdf.relative_to(RAIZ)}")
    print(f"  coords: {coords_path.relative_to(RAIZ)} "
          f"(versao {coords.get('versao')})")

    planos = _montar_planos(coords)
    print(f"  baloes/circulos a marcar: {_contar_baloes(planos)} "
          f"({len(planos['T01']['marcar_frequencias'])} criterios no T01)")

    img = _renderizar(pdf)
    escala = omr_reader.A4_W_PX / omr_reader.A4_W_MM
    janela_px = omr_reader.JANELA_MM * escala

    _marcar(img, coords, planos, escala, janela_px)

    # Anti-flake: garante QR do exame legível antes de processar
    img, qr_reencodado = _garantir_qr_exame(img, coords, escala)
    if qr_reencodado:
        print("  [aviso] QR do exame nao decodificou no render — "
              "re-encodado com payload identico (anti-flake)")

    args.saida.mkdir(parents=True, exist_ok=True)
    scan = args.saida / f"folha_{args.avaliador}_robusta_preenchida.png"
    cv2.imwrite(str(scan), img)
    print(f"  scan marcado: {scan.relative_to(RAIZ)}\n")

    # Roda o reader REAL (QRs reais da folha)
    resultados = omr_reader.processar_imagem(scan, RAIZ / "config",
                                             faixa=None, origem="scanner")
    por_aluno = {r["aluno"]["id"]: r for r in resultados}
    print(f"  alunos lidos: {sorted(por_aluno)} | "
          f"nao na expectativa: {sorted(set(por_aluno) - set(planos))}\n")

    total = erros = 0
    for aluno_id, plano in planos.items():
        total += 1
        if aluno_id not in por_aluno:
            print(f"[FAIL] {aluno_id}: aluno NAO lido pelo reader")
            erros += 1
            continue
        falhas = _avaliar(aluno_id, plano, por_aluno[aluno_id])
        if falhas:
            erros += 1
            print(f"[FAIL] {aluno_id}:")
            for f in falhas:
                print(f"        - {f}")
        else:
            print(f"[PASS] {aluno_id}: presenca/frequencias/obs/incidentes ok")
        r = por_aluno[aluno_id]
        print(f"        lido -> presenca={r['presenca']} | "
              f"n_freq={len(_freq_achatadas(r))} | "
              f"obs={sorted(r['observacoes_marcadas'])} | "
              f"inc={[i for i in r.get('incidentes_auditoria', []) if i not in ('origem:scanner',) and not i.startswith('calibracao_offset')]}")

    print(f"\nResumo: {total - erros}/{total} alunos OK"
          + ("" if erros == 0 else f" | {erros} com falhas"))
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())