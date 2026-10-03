"""
Synthetic trip generator for exercising the pipeline end to end.

Trips follow a smooth, physically consistent speed/heading profile so the
GPS-derived forward acceleration and gyro-derived lateral acceleration in the
pipeline see realistic values (calm ~0.1 g, harsh events 0.4-0.6 g).
Chunks carry car_connected=True so trips classify as driver trips.
"""

import argparse
import math
import random
import time
from typing import Any

import numpy as np
import requests

BASE_URL = "http://localhost:8000/v1"
IMU_HZ = 50
G = 9.81

PROFILES = {
    # cruise m/s, normal accel m/s^2, harsh brakes per trip, harsh accel m/s^2, corner lateral g
    "calm": {"cruise": 11.0, "accel": 1.2, "harsh_brakes": 0, "launch": 1.2, "corner_g": 0.12},
    "moderate": {"cruise": 13.0, "accel": 1.8, "harsh_brakes": 1, "launch": 2.0, "corner_g": 0.25},
    "aggressive": {
        "cruise": 16.5,
        "accel": 2.5,
        "harsh_brakes": 4,
        "launch": 4.0,
        "corner_g": 0.45,
    },
}


def _speed_profile(duration_s: int, p: dict[str, float]) -> np.ndarray:
    """Per-second speed (m/s): cruise with drift, a stop every ~2 min, optional harsh brakes."""
    v = np.zeros(duration_s)
    speed, target = 0.0, p["cruise"]
    stop_every = 120
    brake_times = set(random.sample(range(60, duration_s - 30), p["harsh_brakes"]))
    hold = 0
    braking_hard = 0
    for s in range(duration_s):
        if s in brake_times:
            braking_hard = 2
        if hold > 0:
            hold -= 1
            speed = 0.0
        elif braking_hard > 0:
            speed = max(0.0, speed - 5.5)  # ~0.56 g harsh brake
            braking_hard -= 1
        else:
            if s % stop_every == stop_every - 15:
                target = 0.0
            if target == 0.0 and speed <= 0.0:
                hold = 20  # waiting at a light
                target = p["cruise"] + random.uniform(-2, 2)
            else:
                rate = p["launch"] if speed < 5 else p["accel"]
                speed = max(0.0, speed + max(-p["accel"], min(rate, target - speed)))
                if target > 0 and random.random() < 0.05:
                    target = p["cruise"] + random.uniform(-2, 2)
        v[s] = speed
    return v


def _yaw_profile(v: np.ndarray, p: dict[str, float]) -> np.ndarray:
    """Per-second yaw rate (rad/s): a 4 s turn roughly every minute while moving."""
    yaw = np.zeros(len(v))
    for start in range(30, len(v) - 5, 60):
        direction = random.choice([-1, 1])
        for s in range(start, start + 4):
            if v[s] > 3:
                yaw[s] = direction * p["corner_g"] * G / v[s]
    return yaw


def _build_chunks(trip_type: str, duration_s: int) -> list[dict[str, Any]]:
    p = PROFILES[trip_type]
    v = _speed_profile(duration_s, p)
    yaw = _yaw_profile(v, p)
    fwd = np.gradient(v)  # m/s^2 per second

    start_ms = int(time.time() * 1000)
    lat, lon = 22.3193 + random.uniform(-0.03, 0.03), 114.1694 + random.uniform(-0.03, 0.03)
    heading = random.uniform(0, 2 * math.pi)

    chunks = []
    for seq, chunk_start in enumerate(range(0, duration_s, 60)):
        imu, gps = [], []
        for s in range(chunk_start, min(chunk_start + 60, duration_s)):
            for k in range(IMU_HZ):
                imu.append(
                    {
                        "t": start_ms + s * 1000 + k * (1000 // IMU_HZ),
                        "ax": yaw[s] * v[s] / G + random.gauss(0, 0.02),
                        "ay": fwd[s] / G + random.gauss(0, 0.02),
                        "az": 1.0 + random.gauss(0, 0.01),
                        "gx": random.gauss(0, 0.01),
                        "gy": random.gauss(0, 0.01),
                        "gz": yaw[s] + random.gauss(0, 0.01),
                    }
                )
            heading += yaw[s]
            lat += v[s] * math.cos(heading) / 111320.0
            lon += v[s] * math.sin(heading) / (111320.0 * math.cos(math.radians(lat)))
            gps.append(
                {
                    "t": start_ms + s * 1000,
                    "lat": lat,
                    "lon": lon,
                    "speed": max(0.0, v[s] + random.gauss(0, 0.2)),
                    "heading": math.degrees(heading) % 360,
                    "accuracy": random.uniform(3, 10),
                }
            )
        chunks.append({"seq": seq, "imu": imu, "gps": gps, "car_connected": True})
    return chunks


def generate_synthetic_trip(api_key: str, trip_type: str = "calm") -> str:
    """Start a trip, upload synthetic chunks, and end it."""
    headers = {"X-API-Key": api_key}
    response = requests.post(f"{BASE_URL}/trips/start", headers=headers)
    response.raise_for_status()
    trip_id = response.json()["trip_id"]
    print(f"Started trip {trip_id} ({trip_type})")

    for chunk in _build_chunks(trip_type, random.randint(300, 900)):
        response = requests.post(f"{BASE_URL}/trips/{trip_id}/chunks", headers=headers, json=chunk)
        response.raise_for_status()
        print(f"  Uploaded chunk {chunk['seq']}")

    response = requests.post(f"{BASE_URL}/trips/{trip_id}/end", headers=headers)
    response.raise_for_status()
    print(f"Ended trip {trip_id}, processing started")
    return trip_id


def register_and_simulate(trip_type: str = "calm") -> str:
    """Register a new driver, give consent, and simulate one trip."""
    response = requests.post(f"{BASE_URL}/drivers/register")
    response.raise_for_status()
    data = response.json()
    api_key = data["api_key"]
    print(f"Registered driver: {data['driver_id']}")

    response = requests.post(
        f"{BASE_URL}/consent",
        headers={"X-API-Key": api_key},
        json={"version": "1.0"},
    )
    response.raise_for_status()
    print("Consent recorded")

    return generate_synthetic_trip(api_key, trip_type)


def main():
    parser = argparse.ArgumentParser(description="Simulate trips for DriveScore")
    parser.add_argument(
        "--api-key", help="Driver API key (if not provided, registers a new driver)"
    )
    parser.add_argument("--type", choices=list(PROFILES), default="calm", help="Trip type")
    parser.add_argument("--count", type=int, default=1, help="Number of trips")

    args = parser.parse_args()

    for i in range(args.count):
        if args.api_key:
            trip_id = generate_synthetic_trip(args.api_key, args.type)
        else:
            trip_id = register_and_simulate(args.type)
        print(f"Trip {i + 1}/{args.count} complete: {trip_id}")
        time.sleep(1)


if __name__ == "__main__":
    main()
