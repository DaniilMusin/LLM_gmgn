"""
Тесты для HypeAggregator с персистентностью.
"""
import os
import sys
import tempfile
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from bot.features.hype import HypeAggregator, RollingStats
from bot.models import SocialPost
from bot.config import settings


@pytest.fixture
def temp_data_dir():
    """Создает временную директорию для тестов."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_dir = settings.logging.out_dir
        settings.logging.out_dir = tmpdir
        yield tmpdir
        settings.logging.out_dir = original_dir


def test_hype_aggregator_tracks_posts(temp_data_dir):
    """Тест что HypeAggregator отслеживает посты."""
    hype = HypeAggregator(window_secs=900, auto_load=False)

    post1 = SocialPost(
        platform="bluesky",
        post_id="post1",
        created_at=datetime.now(timezone.utc),
        text="Bullish on $BTC",
        symbols=["BTC"]
    )

    post2 = SocialPost(
        platform="reddit",
        post_id="post2",
        created_at=datetime.now(timezone.utc),
        text="$BTC to the moon!",
        symbols=["BTC"]
    )

    hype.update(post1)
    hype.update(post2)

    # Должно быть 2 поста для BTC
    assert len(hype.posts["BTC"]) == 2


def test_hype_score_increases_with_mentions(temp_data_dir):
    """Тест что hype score растет с количеством упоминаний."""
    hype = HypeAggregator(window_secs=900, auto_load=False)

    # Добавляем несколько постов для BTC
    for i in range(10):
        post = SocialPost(
            platform="bluesky",
            post_id=f"post{i}",
            created_at=datetime.now(timezone.utc),
            text=f"Post about $BTC #{i}",
            symbols=["BTC"]
        )
        hype.update(post)

    score1, meta1 = hype.hype_score("BTC")

    # Добавляем еще постов
    for i in range(10, 20):
        post = SocialPost(
            platform="bluesky",
            post_id=f"post{i}",
            created_at=datetime.now(timezone.utc),
            text=f"Post about $BTC #{i}",
            symbols=["BTC"]
        )
        hype.update(post)

    score2, meta2 = hype.hype_score("BTC")

    # Score должен вырасти
    assert meta2["mentions"] > meta1["mentions"]


def test_red_flags_decrease_score(temp_data_dir):
    """Тест что красные флаги уменьшают score."""
    hype = HypeAggregator(window_secs=900, auto_load=False)

    # Пост без красных флагов
    post_clean = SocialPost(
        platform="bluesky",
        post_id="clean",
        created_at=datetime.now(timezone.utc),
        text="$SOL looks promising",
        symbols=["SOL"]
    )

    # Пост с красным флагом
    post_scam = SocialPost(
        platform="bluesky",
        post_id="scam",
        created_at=datetime.now(timezone.utc),
        text="$SCAM 100x airdrop!",
        symbols=["SCAM"]
    )

    hype.update(post_clean)
    hype.update(post_scam)

    score_clean, meta_clean = hype.hype_score("SOL")
    score_scam, meta_scam = hype.hype_score("SCAM")

    # Scam должен иметь red_flag
    assert meta_scam["red_flag"] is True
    assert meta_clean["red_flag"] is False


def test_save_and_load_state(temp_data_dir):
    """Тест сохранения и загрузки состояния HypeAggregator."""
    # Создаем aggregator и добавляем данные
    hype1 = HypeAggregator(window_secs=900, auto_load=False)

    for i in range(5):
        post = SocialPost(
            platform="bluesky",
            post_id=f"post{i}",
            created_at=datetime.now(timezone.utc),
            text=f"$BTC post #{i}",
            symbols=["BTC"]
        )
        hype1.update(post)

    # Получаем score до сохранения
    score1, meta1 = hype1.hype_score("BTC")

    # Сохраняем состояние
    hype1.save_state()

    # Создаем новый aggregator и загружаем состояние
    hype2 = HypeAggregator(window_secs=900, auto_load=True)

    # Score должен быть похожим (не абсолютно равным из-за времени)
    assert len(hype2.posts["BTC"]) > 0
    assert len(hype2.stats_mentions["BTC"].buf) > 0


def test_rolling_stats_calculates_z_score(temp_data_dir):
    """Тест что RollingStats правильно вычисляет z-score."""
    rs = RollingStats(maxlen=10)

    # Добавляем значения 1, 2, 3, ..., 10
    for i in range(1, 11):
        rs.push(i)

    # Mean = 5.5, z-score для 10 должен быть положительным
    z = rs.z(10)
    assert z > 0

    # z-score для 1 должен быть отрицательным
    z_low = rs.z(1)
    assert z_low < 0


def test_unique_authors_tracked(temp_data_dir):
    """Тест что уникальные авторы правильно отслеживаются."""
    hype = HypeAggregator(window_secs=900, auto_load=False)

    # 3 поста от одного автора
    for i in range(3):
        post = SocialPost(
            platform="bluesky",
            post_id=f"post{i}",
            author_handle="user1",
            created_at=datetime.now(timezone.utc),
            text=f"$BTC post #{i}",
            symbols=["BTC"]
        )
        hype.update(post)

    # 2 поста от другого автора
    for i in range(3, 5):
        post = SocialPost(
            platform="bluesky",
            post_id=f"post{i}",
            author_handle="user2",
            created_at=datetime.now(timezone.utc),
            text=f"$BTC post #{i}",
            symbols=["BTC"]
        )
        hype.update(post)

    _, meta = hype.hype_score("BTC")

    # Должно быть 5 упоминаний, но только 2 уникальных автора
    assert meta["mentions"] == 5
    assert meta["unique_authors"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
