"""core/notifications.py — Distribuição de relatórios (Telegram + Drive).

- Telegram: envia por chat_id (grupo do Dojo / canal dos Mestres).
- Drive: rclone copy seletivo (só os arquivos do próprio Dojo).
- Idempotência: só envia se o hash MD5 do relatório mudou.
- Validação de chat_id antes do envio (evita erro 400 "chat not found").
- Canais vêm de config/canais.json (nunca hardcoded).

Correções v2.0 (revisão da Fase 08):
- Cópia seletiva por Dojo (não copia a pasta output inteira para todos).
- Estado .ka-notify-state.json é persistido no Drive pelo workflow
  (pull antes, push depois) — idempotência entre execuções.
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
TAMANHO_BLOCO = 4000  # limite da API do Telegram por mensagem

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

_chat_validados: set[str] = set()

def validar_chat(bot_token: str, chat_id: str) -> bool:
    """Confirma que o chat_id existe antes de enviar (evita erro 400).

    O resultado é cacheado por chat_id: a validação roda 1× por chat.
    """
    if chat_id in _chat_validados:
        return True
    url = f"https://api.telegram.org/bot{bot_token}/getChat"
    resp = requests.get(url, params={"chat_id": chat_id}, timeout=15)
    if resp.status_code != 200:
        print(f"[ERRO] chat_id {chat_id} inválido: {resp.text[:120]}")
        return False
    _chat_validados.add(chat_id)
    return True

def enviar_telegram(bot_token: str, chat_id: str, texto: str) -> bool:
    """Envia o texto em blocos de até 4000 chars (limite da API)."""
    if not validar_chat(bot_token, chat_id):
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    ok = True
    for i in range(0, len(texto), TAMANHO_BLOCO):
        bloco = texto[i:i + TAMANHO_BLOCO]
        resp = requests.post(url, json={"chat_id": chat_id, "text": bloco},
                             timeout=30)
        if resp.status_code != 200:
            print(f"[ERRO] Telegram: {resp.text[:200]}")
            ok = False
    return ok

def rclone_copy(origem: Path, destino: str) -> bool:
    proc = subprocess.run(
        ["rclone", "copy", str(origem), destino, "--transfers", "4"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[ERRO] rclone: {proc.stderr[:200]}")
    return proc.returncode == 0

def distribuir(output: Path, canais: dict, bot_token: str, base: Path) -> dict:
    estado = carregar_estado(base / STATE_FILE)

    # Relatórios 1 e 2 → grupo do Dojo + pasta do Dojo (cópia seletiva)
    for dojo_id, canal in canais["dojos"].items():
        for rel in (output / f"relatorio_individual_{dojo_id}.txt",
                    output / f"relatorio_dojo_{dojo_id}.txt"):
            if not rel.exists():
                print(f"[AVISO] {rel.name} não encontrado — pulando")
                continue
            chave = f"{dojo_id}:{rel.name}"
            digest = md5(rel)
            if estado.get(chave) == digest:
                print(f"[IDEMPOTENTE] {rel.name} já distribuído (hash inalterado)")
                continue
            if enviar_telegram(bot_token, canal["telegram_chat_id"],
                               rel.read_text(encoding="utf-8")):
                estado[chave] = digest
            rclone_copy(rel, canal["drive_pasta"])

    # Relatório 3 → canal dos Mestres + pasta Mestres
    rel_master = output / "relatorio_master.txt"
    if rel_master.exists():
        m = canais["mestres"]
        chave = f"mestres:{rel_master.name}"
        digest = md5(rel_master)
        if estado.get(chave) == digest:
            print(f"[IDEMPOTENTE] {rel_master.name} já distribuído (hash inalterado)")
        else:
            if enviar_telegram(bot_token, m["telegram_chat_id"],
                               rel_master.read_text(encoding="utf-8")):
                estado[chave] = digest
            rclone_copy(rel_master, m["drive_pasta"])

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