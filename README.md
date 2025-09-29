# Solana Hype GMGN Bot — Perplexity‑first (with exit logic)

- Источники (бесплатно): Bluesky Jetstream, Reddit RSS, Google News RSS, CoinDesk/Cointelegraph/Decrypt RSS.
- Рынок: GeckoTerminal + DexScreener.
- LLM: **Perplexity.ai API** c ротацией ключей.
- Исполнение: GMGN (Solana).
- SQLite логирование + Веб‑панель (отдельным шагом) + Telegram.
- **НОВОЕ:** таблица позиций и воркер **exit‑logic**:
  - Time Stop по `max_hold`.
  - Трейлинг‑стоп от HWM (старт 12%, −2% на каждые +5% профита, минимум 8%).
  - Частичная фиксация профита: `+15% → −30%`, `+35% → −30%`.
  - Downgrade (LLM+хайп): частичный/полный выход.
  - Стрессы рынка: спред, падение `txns.h1`, отрицательный `amm_pi`.
  - Kill‑switch: `rug`, `lp_pull`, `honeypot`, `dev_minted_more` → немедленный выход.

## Быстрый старт
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
cp config/config.example.yaml config/config.yaml
cp config/keys.example.yaml config/keys.yaml
python -m bot.main
```
