"""
Тесты для Portfolio Risk Management.
"""
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot.utils.portfolio_risk import (
    can_open_new_position, get_max_position_size,
    get_portfolio_status, should_scale_down_positions
)
from bot.config import settings


def test_can_open_position_when_under_limit():
    """Тест что можно открыть позицию если под лимитом."""
    # Мокаем get_open_positions чтобы вернуть 2 позиции
    mock_positions = [
        {"invested_wsol": 0.5},
        {"invested_wsol": 0.3}
    ]

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        can_open, reason = can_open_new_position()
        assert can_open is True
        assert reason is None


def test_cannot_open_position_when_at_max_count():
    """Тест что нельзя открыть позицию когда достигнут лимит количества."""
    # Мокаем 5 позиций (максимум по дефолту)
    mock_positions = [{"invested_wsol": 0.2}] * 5

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        can_open, reason = can_open_new_position()
        assert can_open is False
        assert "max open positions" in reason.lower()


def test_cannot_open_position_when_at_max_risk():
    """Тест что нельзя открыть позицию когда достигнут лимит риска."""
    # Мокаем позиции с общим риском >= max_portfolio_risk_wsol (2.0)
    mock_positions = [
        {"invested_wsol": 1.0},
        {"invested_wsol": 1.0}
    ]

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        can_open, reason = can_open_new_position()
        assert can_open is False
        assert "risk limit" in reason.lower()


def test_get_max_position_size_respects_portfolio_limit():
    """Тест что размер позиции ограничивается портфельным лимитом."""
    # Текущий риск: 1.5 WSOL, макс: 2.0 WSOL, доступно: 0.5 WSOL
    mock_positions = [{"invested_wsol": 1.5}]

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        allowed_size, warning = get_max_position_size(1.0)  # Хотим 1.0 WSOL

        # Должно быть ограничено до 0.5 WSOL
        assert allowed_size <= 0.5
        assert warning is not None


def test_get_max_position_size_respects_single_position_limit():
    """Тест что размер позиции ограничивается лимитом на одну позицию."""
    mock_positions = []  # Нет открытых позиций

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        # max_position_size_pct = 0.3 (30%)
        # max_portfolio_risk = 2.0 WSOL
        # max single position = 2.0 * 0.3 = 0.6 WSOL

        allowed_size, warning = get_max_position_size(1.0)  # Хотим 1.0 WSOL

        # Должно быть ограничено до 0.6 WSOL
        assert allowed_size <= 0.6
        assert warning is not None


def test_get_portfolio_status_returns_correct_metrics():
    """Тест что get_portfolio_status возвращает правильные метрики."""
    mock_positions = [
        {"symbol": "BTC", "contract": "abc123", "qty": 100.0, "invested_wsol": 0.5, "opened_at": "2024-01-01"},
        {"symbol": "ETH", "contract": "def456", "qty": 200.0, "invested_wsol": 0.3, "opened_at": "2024-01-02"}
    ]

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        status = get_portfolio_status()

        assert status["open_positions_count"] == 2
        assert status["total_invested_wsol"] == 0.8
        assert status["max_positions"] == settings.risk.max_open_positions
        assert status["max_portfolio_risk_wsol"] == settings.risk.max_portfolio_risk_wsol
        assert len(status["positions"]) == 2


def test_should_scale_down_when_over_limit():
    """Тест что срабатывает предупреждение о масштабировании."""
    # Превышаем лимит на 25%
    mock_positions = [{"invested_wsol": 0.5}] * 6  # 6 позиций при максимуме 5

    with patch('bot.utils.portfolio_risk.get_open_positions', return_value=mock_positions):
        should_scale, reason = should_scale_down_positions()

        assert should_scale is True
        assert reason is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
