"""
Portfolio Risk Management - управление лимитами на позиции и суммарный риск.
"""
from __future__ import annotations
from typing import Optional
from ..config import settings
from .db import get_open_positions


def can_open_new_position() -> tuple[bool, Optional[str]]:
    """
    Проверяет, можно ли открыть новую позицию с учетом портфельных лимитов.

    Returns:
        (can_open, reason): True если можно открывать, иначе False с причиной
    """
    open_positions = get_open_positions()
    current_count = len(open_positions)

    # Проверка лимита на количество позиций
    max_positions = settings.risk.max_open_positions
    if current_count >= max_positions:
        return False, f"Reached max open positions limit: {current_count}/{max_positions}"

    # Проверка суммарного риска портфеля
    total_risk_wsol = sum(float(pos["invested_wsol"] or 0.0) for pos in open_positions)
    max_risk = settings.risk.max_portfolio_risk_wsol

    if total_risk_wsol >= max_risk:
        return False, f"Portfolio risk limit reached: {total_risk_wsol:.4f}/{max_risk} WSOL"

    return True, None


def get_max_position_size(proposed_size_wsol: float) -> tuple[float, Optional[str]]:
    """
    Вычисляет максимальный допустимый размер позиции с учетом портфельных лимитов.

    Args:
        proposed_size_wsol: Предлагаемый размер позиции в WSOL

    Returns:
        (allowed_size, warning): Разрешенный размер и возможное предупреждение
    """
    open_positions = get_open_positions()
    total_risk_wsol = sum(float(pos["invested_wsol"] or 0.0) for pos in open_positions)

    # Проверяем общий портфельный лимит
    max_portfolio_risk = settings.risk.max_portfolio_risk_wsol
    available_risk = max(0.0, max_portfolio_risk - total_risk_wsol)

    # Проверяем лимит на размер одной позиции (процент от портфеля)
    max_position_pct = settings.risk.max_position_size_pct
    max_single_position = max_portfolio_risk * max_position_pct

    # Берем минимум из доступного риска и максимального размера позиции
    max_allowed = min(available_risk, max_single_position)

    if proposed_size_wsol > max_allowed:
        warning = f"Position size reduced from {proposed_size_wsol:.4f} to {max_allowed:.4f} WSOL"
        return max_allowed, warning

    return proposed_size_wsol, None


def get_portfolio_status() -> dict:
    """
    Возвращает текущий статус портфеля.

    Returns:
        dict с информацией о позициях, риске и лимитах
    """
    open_positions = get_open_positions()
    total_invested = sum(float(pos["invested_wsol"] or 0.0) for pos in open_positions)
    total_qty_positions = len(open_positions)

    # Вычисляем текущую стоимость портфеля (примерная, без реквотинга)
    positions_details = []
    for pos in open_positions:
        positions_details.append({
            "symbol": pos["symbol"],
            "contract": pos["contract"],
            "qty": float(pos["qty"] or 0.0),
            "invested_wsol": float(pos["invested_wsol"] or 0.0),
            "opened_at": pos["opened_at"]
        })

    return {
        "open_positions_count": total_qty_positions,
        "max_positions": settings.risk.max_open_positions,
        "positions_utilization_pct": (total_qty_positions / settings.risk.max_open_positions * 100) if settings.risk.max_open_positions > 0 else 0,
        "total_invested_wsol": total_invested,
        "max_portfolio_risk_wsol": settings.risk.max_portfolio_risk_wsol,
        "risk_utilization_pct": (total_invested / settings.risk.max_portfolio_risk_wsol * 100) if settings.risk.max_portfolio_risk_wsol > 0 else 0,
        "available_risk_wsol": max(0.0, settings.risk.max_portfolio_risk_wsol - total_invested),
        "positions": positions_details
    }


def should_scale_down_positions() -> tuple[bool, Optional[str]]:
    """
    Определяет, нужно ли уменьшить размеры позиций из-за портфельных рисков.

    Returns:
        (should_scale, reason): True если нужно масштабировать вниз
    """
    open_positions = get_open_positions()
    total_invested = sum(float(pos["invested_wsol"] or 0.0) for pos in open_positions)

    # Если превышен лимит портфеля на 20% - пора масштабировать
    max_risk = settings.risk.max_portfolio_risk_wsol
    if total_invested > max_risk * 1.2:
        return True, f"Portfolio risk exceeded: {total_invested:.4f}/{max_risk} WSOL"

    # Если слишком много позиций
    if len(open_positions) > settings.risk.max_open_positions * 1.2:
        return True, f"Too many positions: {len(open_positions)}/{settings.risk.max_open_positions}"

    return False, None
