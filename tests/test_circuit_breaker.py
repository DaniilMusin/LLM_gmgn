"""
Тесты для Circuit Breaker функционала.
"""
import os
import sys
import tempfile
import pytest

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot.utils.circuit_breaker import (
    record_trade, is_circuit_open, reset_circuit_breaker,
    set_manual_override, get_status, _load_state, _save_state
)
from bot.config import settings


@pytest.fixture
def temp_data_dir():
    """Создает временную директорию для тестов."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = settings.logging.out_dir
        settings.logging.out_dir = tmpdir
        yield tmpdir
        settings.logging.out_dir = original_dir


def test_circuit_breaker_opens_on_losses(temp_data_dir):
    """Тест что circuit breaker открывается при череде убытков."""
    reset_circuit_breaker()

    # Записываем 5 убыточных сделок подряд
    for i in range(5):
        record_trade(-0.1, f"contract_{i}")  # -0.1 WSOL убыток

    # Circuit breaker должен открыться (> 70% убыточных)
    is_open, reason = is_circuit_open()
    assert is_open is True
    assert reason is not None


def test_circuit_breaker_stays_closed_on_wins(temp_data_dir):
    """Тест что circuit breaker не открывается при профитных сделках."""
    reset_circuit_breaker()

    # Записываем 5 прибыльных сделок
    for i in range(5):
        record_trade(0.1, f"contract_{i}")  # +0.1 WSOL профит

    # Circuit breaker должен остаться закрытым
    is_open, reason = is_circuit_open()
    assert is_open is False


def test_circuit_breaker_opens_on_max_drawdown(temp_data_dir):
    """Тест что circuit breaker открывается при превышении max drawdown."""
    reset_circuit_breaker()

    # Делаем несколько небольших сделок чтобы достичь минимума (5 trades)
    record_trade(0.01, "contract_1")
    record_trade(0.01, "contract_2")
    record_trade(0.01, "contract_3")
    record_trade(0.01, "contract_4")

    # И одна большая просадка
    record_trade(-0.6, "contract_5")  # Больше max_drawdown (0.5 WSOL)

    # Circuit breaker должен открыться (total P/L = 0.04 - 0.6 = -0.56 < -0.5)
    is_open, reason = is_circuit_open()
    assert is_open is True


def test_manual_override_allows_trading(temp_data_dir):
    """Тест что manual override позволяет торговать даже при открытом CB."""
    reset_circuit_breaker()

    # Открываем circuit breaker
    for i in range(5):
        record_trade(-0.1, f"contract_{i}")

    # Проверяем что открыт
    assert is_circuit_open()[0] is True

    # Включаем manual override
    set_manual_override(True)

    # Теперь circuit breaker должен быть закрыт
    is_open, _ = is_circuit_open()
    assert is_open is False


def test_get_status_returns_correct_info(temp_data_dir):
    """Тест что get_status возвращает правильную информацию."""
    reset_circuit_breaker()

    # Записываем несколько сделок
    record_trade(0.1, "contract_1")  # Win
    record_trade(-0.05, "contract_2")  # Loss
    record_trade(0.15, "contract_3")  # Win

    status = get_status()

    assert status["total_wins"] == 2
    assert status["total_losses"] == 1
    assert status["recent_trades_count"] == 3
    assert "recent_loss_rate" in status
    assert status["recent_loss_rate"] < 0.5  # 1 из 3 = 33%


def test_reset_clears_circuit_breaker(temp_data_dir):
    """Тест что reset правильно очищает circuit breaker."""
    # Открываем circuit breaker
    for i in range(5):
        record_trade(-0.1, f"contract_{i}")

    assert is_circuit_open()[0] is True

    # Сбрасываем
    reset_circuit_breaker()

    # Должен быть закрыт
    is_open, _ = is_circuit_open()
    assert is_open is False

    # И manual override должен быть выключен
    status = get_status()
    assert status["manual_override"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
