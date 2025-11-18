"""
Circuit Breaker для защиты от череды убыточных сделок.

Останавливает торговлю если слишком много убыточных сделок подряд.
"""
from __future__ import annotations
import os, json, threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from ..config import settings

_LOCK = threading.Lock()

def _cb_path():
    out = settings.logging.out_dir
    os.makedirs(out, exist_ok=True)
    return os.path.join(out, "circuit_breaker.json")

def _load_state() -> dict:
    try:
        with open(_cb_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "is_open": False,
            "opened_at": None,
            "cooldown_until": None,
            "recent_trades": [],
            "total_losses": 0,
            "total_wins": 0,
            "manual_override": False
        }

def _save_state(state: dict):
    # BUG FIX #57: Use atomic write to prevent file corruption in critical safety component
    try:
        cb_path = _cb_path()
        temp_path = cb_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(temp_path, cb_path)  # Atomic on POSIX systems
    except Exception:
        pass

def record_trade(profit_loss_wsol: float, contract: str):
    """
    Записывает результат сделки для circuit breaker.

    Args:
        profit_loss_wsol: Профит/убыток в WSOL (положительное = профит, отрицательное = убыток)
        contract: Контракт токена
    """
    with _LOCK:
        state = _load_state()

        # BUG FIX #9: Don't record trades during manual override to avoid unexpected CB opening
        if state.get("manual_override", False):
            # Manual override active - skip recording
            return

        now = datetime.now(timezone.utc).isoformat()
        trade = {
            "timestamp": now,
            "profit_loss": profit_loss_wsol,
            "contract": contract,
            "is_loss": profit_loss_wsol < 0
        }

        # Добавляем сделку
        state["recent_trades"].append(trade)

        # Храним только последние N сделок (настраиваемо через config)
        max_recent = getattr(settings.risk, 'circuit_breaker_window', 20)
        state["recent_trades"] = state["recent_trades"][-max_recent:]

        # Обновляем счетчики
        if profit_loss_wsol < 0:
            state["total_losses"] += 1
        else:
            state["total_wins"] += 1

        # Проверяем условия для открытия circuit breaker
        if not state["is_open"]:
            recent = state["recent_trades"]
            if len(recent) >= getattr(settings.risk, 'circuit_breaker_min_trades', 5):
                # Считаем процент убыточных
                losses = sum(1 for t in recent if t["is_loss"])
                loss_pct = losses / len(recent)

                # Проверяем также абсолютный убыток
                total_pl = sum(t["profit_loss"] for t in recent)
                max_drawdown = abs(getattr(settings.risk, 'circuit_breaker_max_drawdown_wsol', 0.5))

                loss_threshold = getattr(settings.risk, 'circuit_breaker_loss_threshold_pct', 0.7)

                # Открываем circuit breaker если:
                # 1. Процент убыточных > порога ИЛИ
                # 2. Общий убыток превысил максимальный drawdown
                if loss_pct >= loss_threshold or total_pl <= -max_drawdown:
                    state["is_open"] = True
                    state["opened_at"] = now

                    # Cooldown период в часах
                    cooldown_hours = getattr(settings.risk, 'circuit_breaker_cooldown_hours', 4)
                    cooldown_until = datetime.now(timezone.utc) + timedelta(hours=cooldown_hours)
                    state["cooldown_until"] = cooldown_until.isoformat()

        _save_state(state)

def is_circuit_open() -> tuple[bool, Optional[str]]:
    """
    Проверяет, открыт ли circuit breaker.

    Returns:
        (is_open, reason): True если торговля заблокирована, иначе False
    """
    with _LOCK:
        state = _load_state()

        # Если manual override включен - всегда разрешаем торговлю
        if state.get("manual_override", False):
            return False, None

        if not state["is_open"]:
            return False, None

        # Проверяем, не истек ли cooldown
        if state["cooldown_until"]:
            try:
                cooldown_dt = datetime.fromisoformat(state["cooldown_until"])
                if datetime.now(timezone.utc) >= cooldown_dt:
                    # Cooldown истек - закрываем circuit breaker
                    state["is_open"] = False
                    state["cooldown_until"] = None
                    state["opened_at"] = None
                    _save_state(state)
                    return False, None
            except Exception:
                pass

        # Circuit breaker все еще открыт
        recent = state["recent_trades"]
        if recent:
            losses = sum(1 for t in recent if t["is_loss"])
            total_pl = sum(t["profit_loss"] for t in recent)
            reason = f"Circuit breaker OPEN: {losses}/{len(recent)} losses, total P/L: {total_pl:.4f} WSOL"
        else:
            reason = "Circuit breaker OPEN"

        return True, reason

def get_status() -> dict:
    """Возвращает текущий статус circuit breaker."""
    with _LOCK:
        state = _load_state()
        recent = state["recent_trades"]

        status = {
            "is_open": state["is_open"],
            "opened_at": state["opened_at"],
            "cooldown_until": state["cooldown_until"],
            "manual_override": state.get("manual_override", False),
            "total_wins": state["total_wins"],
            "total_losses": state["total_losses"],
            "recent_trades_count": len(recent)
        }

        if recent:
            losses = sum(1 for t in recent if t["is_loss"])
            total_pl = sum(t["profit_loss"] for t in recent)
            status["recent_loss_rate"] = losses / len(recent)
            status["recent_total_pl"] = total_pl

        return status

def reset_circuit_breaker():
    """Сбрасывает circuit breaker (для ручного вмешательства)."""
    with _LOCK:
        state = _load_state()
        state["is_open"] = False
        state["opened_at"] = None
        state["cooldown_until"] = None
        state["manual_override"] = False
        _save_state(state)

def set_manual_override(enabled: bool):
    """
    Устанавливает manual override.

    Args:
        enabled: True чтобы игнорировать circuit breaker и торговать принудительно
    """
    with _LOCK:
        state = _load_state()
        state["manual_override"] = enabled
        _save_state(state)
