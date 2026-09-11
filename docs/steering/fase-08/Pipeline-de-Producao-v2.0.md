
FASE 08 — Pipeline de Produção v2.0 (Integração Final)0. PERSONA E ESPECIALIDADES — ASSUMIR AUTOMATICAMENTEVocê atua como uma equipe de 3 especialistas:
Engenheiro SRE/DevOps — GitHub Actions, rclone, secrets, idempotência, observabilidade, jobs com dependências.
Dev Python Sênior — orquestração de módulos, subprocess, requests, tratamento de erros.
Analista Pedagógico de Karatê — roteamento correto dos relatórios (Individual/Dojo → grupo do Dojo; Master → canal dos Mestres).
Regras de conduta:
Use SEMPRE os módulos já criados nas Fases 01–06 (core/engine.py, core/parser.py, core/omr_reader.py, core/relatorios.py, config/). Não reimplemente lógica existente.
Segredos (token do bot, credenciais rclone) vão exclusivamente em secrets do GitHub Actions — nunca no código nem no manifesto.
Canais de Telegram e pastas do Drive vêm de config/canais.json — nunca hardcoded.
Idempotência por hash MD5 é obrigatória: rodar o pipeline 2× não pode duplicar envios.
Ao final, preencha o checklist de aceite com o resultado real da execução.

1. ObjetivoCriar o pipeline de produção v2.0 que executa o fluxo completo do exame de forma automatizada:
2. 

rclone pull (gabaritos + cadastros do Drive)
        ↓
core/pipeline.py: OMR → JSON → engine (por faixa) → relatórios (3 camadas)
        ↓
core/notifications.py: Telegram (grupo do Dojo / canal dos Mestres) + rclone push (Drive)

Inclui: validação de chat_id do Telegram (corrige o erro histórico "chat not found" da v1.1), idempotência MD5 por relatório, multi-dojo e separação de acesso (Sensei vs. Mestres).2. Contexto mínimo do projetoO repositório já tem o pipeline de produção antigo (pipeline.yml, v1.1 — parse TXT + envio único). As Fases 00–06 entregaram os módulos v2.0; a Fase 07 entregou o pipeline de testes (testes.yml). Falta o pipeline de produção atualizado para o novo fluxo, que é o que esta fase entrega.3. Decisões aprovadas (não reabrir)
3 jobs encadeados: sincronizar-entrada → processar-exame → distribuir.
rclone: pull de data/gabaritos/ e data/cadastro/; push de relatórios por pasta (Dojo e Mestres).
Telegram: Relatórios 1 e 2 → grupo do Dojo; Relatório 3 → canal privado dos Mestres. Chat_id validado antes do envio (getChat).
Idempotência: hash MD5 por relatório + estado em .ka-notify-state.json; só envia se o hash mudou.
Multi-dojo: config/canais.json mapeia dojo_id → chat_id e pasta do Drive; mestres → canal e pasta restrita.
Disparo: agendamento (schedule) + manual (workflow_dispatch).
Secrets: TELEGRAM_BOT_TOKEN e RCLONE_CONF configurados no repositório.
4. Tarefas
 Criar .github/workflows/pipeline.yml (código na seção 5).
 Criar core/pipeline.py (orquestrador OMR → engine → relatórios).
 Criar core/notifications.py (Telegram + Drive + idempotência + validação de chat).
 Criar config/canais.json (modelo com placeholders).
 Adicionar requests ao requirements.txt.
 Configurar secrets TELEGRAM_BOT_TOKEN e RCLONE_CONF no repositório.
 Rodar workflow_dispatch com dados de teste e validar o fluxo completo.
 Registrar no Status (seção 7).
5. Código de referência.github/workflows/pipeline.yml:



name: Pipeline Karate-Ashi v2.0

on:
  schedule:
    - cron: "0 22 * * *"   # ajustar conforme a rotina de exames do Dojo
  workflow_dispatch:        # execução manual (testes e exames especiais)

jobs:
  sincronizar-entrada:
    name: Sincronizar Gabaritos e Cadastros (rclone)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configurar rclone
        run: |
          mkdir -p ~/.config/rclone
          echo "${{ secrets.RCLONE_CONF }}" > ~/.config/rclone/rclone.conf

      - name: Pull gabaritos e cadastros do Drive
        run: |
          rclone copy "gdrive:KarateAshi/gabaritos" data/gabaritos/ --transfers 8
          rclone copy "gdrive:KarateAshi/cadastro" data/cadastro/ --transfers 8

      - name: Upload artefato de entrada
        uses: actions/upload-artifact@v4
        with:
          name: dados-entrada
          path: |
            data/gabaritos/
            data/cadastro/
          if-no-files-found: warn

  processar-exame:
    name: Processar Exame (OMR → Engine → Relatórios)
    runs-on: ubuntu-latest
    needs: sincronizar-entrada
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Baixar dados de entrada
        uses: actions/download-artifact@v4
        with:
          name: dados-entrada

      - name: Executar pipeline de processamento
        run: python core/pipeline.py --config config --data data --output output

      - name: Upload relatórios gerados
        uses: actions/upload-artifact@v4
        with:
          name: relatorios
          path: output/
          if-no-files-found: error

  distribuir:
    name: Distribuir Relatórios (Telegram + Drive)
    runs-on: ubuntu-latest
    needs: processar-exame
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Instalar dependências
        run: pip install -r requirements.txt

      - name: Baixar relatórios
        uses: actions/download-artifact@v4
        with:
          name: relatorios

      - name: Configurar rclone
        run: |
          mkdir -p ~/.config/rclone
          echo "${{ secrets.RCLONE_CONF }}" > ~/.config/rclone/rclone.conf

      - name: Enviar Telegram e sincronizar Drive
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
        run: python core/notifications.py --output output --config config


`config/canais.json` (modelo — preencher com os valores reais):

{
  "dojos": {
    "D01": {
      "nome": "Dojo Central",
      "telegram_chat_id": "-1000000000000",
      "drive_pasta": "KarateAshi/Dojo01"
    }
  },
  "mestres": {
    "telegram_chat_id": "-1000000000001",
    "drive_pasta": "KarateAshi/Mestres"
  }
}


`core/pipeline.py`:



"""core/pipeline.py — Orquestrador do processamento v2.0.

Fluxo:

1. varre data/gabaritos/ (imagens) e data/ (TXT fallback);
2. para cada imagem: OMR (core/omr_reader) → JSON intermediário;
3. agrupa JSONs por aluno (QR: aluno_id) e por avaliador;
4. engine (core/engine) calcula notas por faixa;
5. relatórios (core/relatorios) geram as 3 camadas.
   """
   from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from core import engine, relatorios
from core.omr_reader import processar_imagem
from core.parser import parse_arquivo

QUESITOS_ORDEM = ["kihon", "kata", "bunkai", "kumite"]

def processar_gabaritos(pasta: Path, base_cfg: Path) -> list[dict]:
    """Roda o OMR em cada imagem e devolve a lista de JSONs v2.0.

    A faixa é lida do QR Code; se a faixa não for suportada, o erro é
    registrado e a folha é ignorada (não derruba o lote).
    """
    jsons = []
    for img in sorted(pasta.glob("*.jpg")) + sorted(pasta.glob("*.png")):
        try:
            dados = processar_imagem(img, base_cfg, "branca")
            jsons.append(dados)
        except ValueError as exc:
            print(f"[ERRO] {img.name}: {exc}")
    return jsons

def agrupar_por_aluno(jsons: list[dict]) -> dict[str, list[dict]]:
    """Agrupa os JSONs dos avaliadores por aluno_id."""
    grupos: dict[str, list[dict]] = defaultdict(list)
    for dados in jsons:
        grupos[dados["aluno"]["id"]].append(dados)
    return dict(grupos)

def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline Karate-Ashi v2.0")
    ap.add_argument("--config", type=Path, default=Path("config"))
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--output", type=Path, default=Path("output"))
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    # 1. Entrada: imagens OMR + fallback TXT
    jsons = processar_gabaritos(args.data / "gabaritos", args.config)
    if (args.data / "input.txt").exists():
        jsons += parse_arquivo(args.data / "input.txt", args.config)

    # 2. Agrupar por aluno e calcular notas por faixa
    resultados = []
    for aluno_id, avaliacoes in agrupar_por_aluno(jsons).items():
        faixa = avaliacoes[0]["aluno"]["faixa_atual"].lower()
        try:
            resultado = engine.processa_aluno(avaliacoes, args.config, faixa)
        except ValueError as exc:
            print(f"[ERRO] aluno {aluno_id}: {exc}")
            continue
        resultados.append({"aluno": avaliacoes[0]["aluno"],
                           "resultado": resultado})

    # 3. Relatórios (camada 1 — individual)
    regras = engine.carregar_json(args.config / "regras_gerais.json")
    recomendacoes = engine.carregar_json(args.config / "recomendacoes.json")
    with open(args.output / "relatorio_individual.txt", "w",
              encoding="utf-8") as fh:
        for item in resultados:
            fh.write(relatorios.relatorio_individual(
                item["resultado"], regras, recomendacoes, item["aluno"]))
            fh.write("\n\n---\n\n")

    print(f"Processados {len(resultados)} alunos. Relatórios em {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


`core/notifications.py`:



"""core/notifications.py — Distribuição de relatórios (Telegram + Drive).

- Telegram: envia por chat_id (grupo do Dojo / canal dos Mestres).
- Drive: rclone copy para a pasta do Dojo / pasta Mestres.
- Idempotência: só envia se o hash MD5 do relatório mudou.
- Validação de chat_id antes do envio (evita erro 400 "chat not found").
- Canais vêm de config/canais.json (nunca hardcoded).
  """
  from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import requests

STATE_FILE = ".ka-notify-state.json"

def md5(arquivo: Path) -> str:
    h = hashlib.md5()
    h.update(arquivo.read_bytes())
    return h.hexdigest()

def carregar_estado(caminho: Path) -> dict:
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {}

def salvar_estado(caminho: Path, estado: dict) -> None:
    caminho.write_text(json.dumps(estado, indent=2, ensure_ascii=False),
                       encoding="utf-8")

def validar_chat(bot_token: str, chat_id: str) -> bool:
    """Confirma que o chat_id existe antes de enviar (evita erro 400)."""
    url = f"https://api.telegram.org/bot{bot_token}/getChat"
    resp = requests.get(url, params={"chat_id": chat_id}, timeout=15)
    if resp.status_code != 200:
        print(f"[ERRO] chat_id {chat_id} inválido: {resp.text[:120]}")
        return False
    return True

def enviar_telegram(bot_token: str, chat_id: str, texto: str) -> bool:
    if not validar_chat(bot_token, chat_id):
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": texto},
                         timeout=30)
    return resp.status_code == 200

def rclone_copy(origem: Path, destino: str) -> bool:
    proc = subprocess.run(
        ["rclone", "copy", str(origem), destino, "--transfers", "4"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERRO] rclone: {proc.stderr[:200]}")
    return proc.returncode == 0

def distribuir(output: Path, canais: dict, bot_token: str,
               base: Path) -> dict:
    estado = carregar_estado(base / STATE_FILE)
    rel_individual = output / "relatorio_individual.txt"
    rel_dojo = output / "relatorio_dojo.txt"
    rel_master = output / "relatorio_master.txt"

    # Relatórios 1 e 2 → grupo do Dojo + pasta do Dojo
    for dojo_id, canal in canais["dojos"].items():
        for rel in (rel_individual, rel_dojo):
            if not rel.exists():
                continue
            chave = f"{dojo_id}:{rel.name}"
            digest = md5(rel)
            if estado.get(chave) == digest:
                continue  # idempotência: já enviado
            if enviar_telegram(bot_token, canal["telegram_chat_id"],
                               rel.read_text(encoding="utf-8")):
                estado[chave] = digest
        rclone_copy(output, canal["drive_pasta"])

    # Relatório 3 → canal dos Mestres + pasta Mestres
    if rel_master.exists():
        m = canais["mestres"]
        chave = f"mestres:{rel_master.name}"
        digest = md5(rel_master)
        if estado.get(chave) != digest:
            if enviar_telegram(bot_token, m["telegram_chat_id"],
                               rel_master.read_text(encoding="utf-8")):
                estado[chave] = digest
        rclone_copy(output / rel_master.name, m["drive_pasta"])

    salvar_estado(base / STATE_FILE, estado)
    return estado

def main() -> int:
    ap = argparse.ArgumentParser(description="Distribuição Karate-Ashi v2.0")
    ap.add_argument("--output", type=Path, default=Path("output"))
    ap.add_argument("--config", type=Path, default=Path("config"))
    args = ap.parse_args()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("ERRO: TELEGRAM_BOT_TOKEN não definido")
        return 1

    canais = json.loads((args.config / "canais.json").read_text(encoding="utf-8"))
    distribuir(args.output, canais, bot_token, args.config.parent)
    print("Distribuição concluída (idempotente).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


Ajuste no requirements.txt (adicionar):requests>=2.316. Critérios de aceite
 pipeline.yml com os 3 jobs encadeados (sincronizar-entrada → processar-exame → distribuir).
 core/pipeline.py processa um lote de teste (imagens OMR e/ou TXT) e gera output/relatorio_individual.txt.
 core/notifications.py valida chat_id antes de enviar (chat inválido → log claro, sem crash).
 Idempotência comprovada: rodar notifications.py 2× com os mesmos relatórios não reenvia Telegram.
 config/canais.json criado com placeholders e comentário de preenchimento.
 Secrets TELEGRAM_BOT_TOKEN e RCLONE_CONF configurados no repositório.
 workflow_dispatch executa o fluxo completo de ponta a ponta com dados de teste.
 requests adicionado ao requirements.txt.
7. Status
 Pendente · [ ] Em execução · [ ] Concluída (data: ___)
Resumindo
Fase 08 entrega o pipeline de produção v2.0: 3 jobs encadeados (rclone → processamento → distribuição).
core/pipeline.py orquestra OMR → engine → relatórios; core/notifications.py faz Telegram + Drive com idempotência MD5 e validação de chat_id (corrige o bug histórico da v1.1).
Canais e pastas vêm de config/canais.json — multi-dojo e separação Sensei/Mestres sem hardcode.
Ordem final das fases: 00 → 01 → 02 → 03 → 06 → 04 → 05 → 07 → 08.
