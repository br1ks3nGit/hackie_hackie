import pytest
from app.model import (
    predict,
    confidence_to_score,
    score_to_tier,
    tier_to_multiplier,
    ModelPredictionError,
)


def test_confidence_to_score():
    assert confidence_to_score(0.0) == 100
    assert confidence_to_score(0.5) == 50
    assert confidence_to_score(1.0) == 0


def test_score_to_tier():
    assert score_to_tier(95) == "A"
    assert score_to_tier(80) == "B"
    assert score_to_tier(65) == "C"
    assert score_to_tier(45) == "D"
    assert score_to_tier(30) == "E"


def test_tier_to_multiplier():
    assert tier_to_multiplier("A") == 0.80
    assert tier_to_multiplier("B") == 0.90
    assert tier_to_multiplier("C") == 1.00
    assert tier_to_multiplier("D") == 1.15
    assert tier_to_multiplier("E") == 1.30


def test_predict_placeholder():
    features = {
        "distance_km": 10.0,
        "duration_min": 15.0,
        "night_driving_share": 0.0,
        "events_per_100km": {
            "harsh_brake": 5.0,
            "harsh_accel": 3.0,
            "sharp_corner": 2.0,
            "speeding": 0.0,
        },
        "mean_speed_ms": 15.0,
        "max_speed_ms": 25.0,
        "speeding_time_share": 0.0,
    }

    result = predict(features)
    assert "confidence" in result
    assert "model_version" in result
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["model_version"] == "placeholder"


def test_predict_placeholder_aggressive():
    features = {
        "distance_km": 10.0,
        "duration_min": 15.0,
        "night_driving_share": 0.5,
        "events_per_100km": {
            "harsh_brake": 20.0,
            "harsh_accel": 15.0,
            "sharp_corner": 10.0,
            "speeding": 5.0,
        },
        "mean_speed_ms": 20.0,
        "max_speed_ms": 40.0,
        "speeding_time_share": 0.3,
    }

    result = predict(features)
    assert result["confidence"] > 0.5  # aggressive driving should be risky
