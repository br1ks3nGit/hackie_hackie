import os
import pickle
from typing import Dict, Any, Optional
from app.config import get_settings

settings = get_settings()


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
    if os.path.exists(settings.model_path):
        try:
            with open(settings.model_path, "rb") as f:
                _model = pickle.load(f)
            _model_version = "pkl-model"
        except Exception as e:
            raise ModelNotLoadedError(f"Failed to load model from {settings.model_path}: {e}")
    else:
        _model = None
        _model_version = "placeholder"


def predict(features: Dict[str, Any]) -> Dict[str, Any]:
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
            # Real model path
            prediction = _model.predict([list(features.values())])[0]
            confidence = float(prediction)
            if not 0.0 <= confidence <= 1.0:
                raise ModelPredictionError(f"Model returned invalid confidence: {confidence}")
            return {"confidence": confidence, "model_version": _model_version}
        except Exception as e:
            raise ModelPredictionError(f"Model prediction failed: {e}")

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
    confidence = (
        0.3 * brake_score +
        0.3 * accel_score +
        0.2 * corner_score +
        0.2 * speed_score
    )

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
