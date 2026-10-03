import os
import pickle
from typing import Any

from app.config import get_settings
from app.window_model import load_window_model

settings = get_settings()


# Flat feature vector order for the real model.
# NOTE for the model team: train on features in this exact order.
FEATURE_ORDER = [
    "distance_km",
    "duration_min",
    "night_driving_share",
    "harsh_brake_per_100km",
    "harsh_accel_per_100km",
    "sharp_corner_per_100km",
    "speeding_per_100km",
    "mean_speed_ms",
    "max_speed_ms",
    "speeding_time_share",
]


def _features_to_vector(features: dict[str, Any]) -> list[float]:
    """Flatten a pipeline feature dict into the FEATURE_ORDER vector."""
    events_per_100km = features.get("events_per_100km", {}) or {}
    flat = dict(features)
    flat["harsh_brake_per_100km"] = events_per_100km.get("harsh_brake", 0.0)
    flat["harsh_accel_per_100km"] = events_per_100km.get("harsh_accel", 0.0)
    flat["sharp_corner_per_100km"] = events_per_100km.get("sharp_corner", 0.0)
    flat["speeding_per_100km"] = events_per_100km.get("speeding", 0.0)
    return [float(flat.get(name, 0.0)) for name in FEATURE_ORDER]


class ModelError(Exception):
    pass


class ModelNotLoadedError(ModelError):
    pass


class ModelPredictionError(ModelError):
    pass


_model = None
_model_version = "placeholder"


def load_model() -> None:
    """Load the model from disk if it exists. Called once at startup."""
    global _model, _model_version
    if settings.model_kind == "window":
        load_window_model()
    if os.path.exists(settings.model_path):
        try:
            with open(settings.model_path, "rb") as f:
                _model = pickle.load(f)
            _model_version = "pkl-model"
        except Exception as e:
            raise ModelNotLoadedError(
                f"Failed to load model from {settings.model_path}: {e}"
            ) from e
    else:
        _model = None
        _model_version = "placeholder"


def predict(features: dict[str, Any]) -> dict[str, Any]:
    """
    Predict driver risk from trip features.

    Args:
        features: Dict of trip features from the pipeline.

    Returns:
        Dict with confidence (0-1) and model_version.
        confidence = probability that the driver is risky.
    """
    global _model, _model_version

    if _model is not None:
        try:
            # Real model path: flat feature vector in FEATURE_ORDER
            X = [_features_to_vector(features)]
            if hasattr(_model, "predict_proba"):
                confidence = float(_model.predict_proba(X)[0][1])
            else:
                confidence = float(_model.predict(X)[0])
            if not 0.0 <= confidence <= 1.0:
                raise ModelPredictionError(f"Model returned invalid confidence: {confidence}")
            return {"confidence": confidence, "model_version": _model_version}
        except ModelPredictionError:
            raise
        except Exception as e:
            raise ModelPredictionError(f"Model prediction failed: {e}") from e

    # Placeholder model: simple linear combination of event rates
    event_rates = features.get("events_per_100km", {})
    harsh_brakes = event_rates.get("harsh_brake", 0)
    harsh_accels = event_rates.get("harsh_accel", 0)
    sharp_corners = event_rates.get("sharp_corner", 0)
    speeding_share = features.get("speeding_time_share", 0)

    # Normalize each to roughly 0-1 range
    brake_score = min(harsh_brakes / 10.0, 1.0)
    accel_score = min(harsh_accels / 10.0, 1.0)
    corner_score = min(sharp_corners / 10.0, 1.0)
    speed_score = min(speeding_share / 0.2, 1.0)

    # Weighted average
    confidence = 0.3 * brake_score + 0.3 * accel_score + 0.2 * corner_score + 0.2 * speed_score

    return {"confidence": round(confidence, 4), "model_version": "placeholder"}


def confidence_to_score(confidence: float) -> int:
    """Convert confidence (0-1) to score (0-100, 100 = safest)."""
    return round(100 * (1 - confidence))


def score_to_tier(score: int) -> str:
    """Map score to tier A-E."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "E"


def tier_to_multiplier(tier: str) -> float:
    """Map tier to premium multiplier."""
    mapping = {
        "A": 0.80,
        "B": 0.90,
        "C": 1.00,
        "D": 1.15,
        "E": 1.30,
    }
    return mapping.get(tier, 1.00)
