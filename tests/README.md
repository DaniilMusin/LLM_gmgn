# Tests

Базовые unit тесты для критичных компонентов бота.

## Установка зависимостей для тестов

```bash
pip install -e ".[dev]"
```

## Запуск тестов

Запустить все тесты:

```bash
pytest
```

Запустить с покрытием:

```bash
pytest --cov=src/bot --cov-report=html
```

Запустить конкретный тестовый файл:

```bash
pytest tests/test_circuit_breaker.py -v
```

## Покрытые компоненты

- **Circuit Breaker** (`test_circuit_breaker.py`) - тесты защиты от убыточных сделок
- **Portfolio Risk** (`test_portfolio_risk.py`) - тесты портфельных лимитов
- **Hype Aggregator** (`test_hype_aggregator.py`) - тесты агрегации и персистентности хайпа

## TODO

- Integration тесты для GMGN API
- Тесты для exit logic
- Тесты для LLM интеграции
- Тесты для адаптеров источников данных
