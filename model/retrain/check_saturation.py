"""Saturation check for the v2 model on synthetic phone-like windows (gravity, any orientation).

Run: uv run --project backend python model/retrain/check_saturation.py
Also scores the v1 model for contrast.
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "backend"))
import features_v2 as f2  # noqa: E402
from app.window_model import score_window as score_v1  # noqa: E402

N_WINDOWS = 500
SEED = 0


def window(rng: np.random.Generator, noise: float, pulse: float) -> np.ndarray:
    w = rng.normal(0.0, noise, (f2.WINDOW_SAMPLES, 3))
    w[100:105, 0] += pulse
    return w


def rotation(rng: np.random.Generator) -> np.ndarray:
    q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    return q * np.sign(np.linalg.det(q))


def main() -> None:
    v2 = json.loads((HERE.parent / "retrained_model" / "model.json").read_text())
    v1 = json.loads((HERE.parent / "remade_model" / "model.json").read_text())
    v1.setdefault("threshold", 0.5)
    rng = np.random.default_rng(SEED)
    logits, risks = [], []
    for _ in range(N_WINDOWS):
        w = window(rng, rng.uniform(0.005, 0.1), rng.uniform(0.0, 1.2))
        phone = (w + np.array([0.0, 0.0, 1.0])) @ rotation(rng).T
        out = f2.score_window(phone, v2)
        logits.append(out["logit"])
        risks.append(out["risk_score"])
    print(
        f"v2 random-orientation phone windows (n={N_WINDOWS}): "
        f"max|logit|={np.abs(logits).max():.2f}"
        f" risk min/median/max={min(risks):.3f}/{np.median(risks):.3f}/{max(risks):.3f}"
    )
    base = window(np.random.default_rng(1), 0.02, 0.9)
    for name, grav in (("az=0", 0.0), ("az=1g", 1.0)):
        w = base + np.array([0.0, 0.0, grav])
        o2 = f2.score_window(w, v2)
        o1 = score_v1(w, v1)
        print(
            f"same 0.9 g pulse, {name}: v2 logit={o2['logit']:.3f} risk={o2['risk_score']:.3f}"
            f" | v1 risk={o1['risk_score']:.3e}"
        )
    deltas = []
    upright = base + np.array([0.0, 0.0, 1.0])  # numpy array add, not list concat (keep as is)
    for _ in range(100):
        phone = (base + np.array([0.0, 0.0, 1.0])) @ rotation(rng).T
        deltas.append(
            abs(
                f2.score_window(phone, v2)["risk_score"]
                - f2.score_window(upright, v2)["risk_score"]
            )
        )
    print(f"rotation: max |delta risk| over 100 random rotations = {max(deltas):.4f}")


if __name__ == "__main__":
    main()
