import argparse
import json
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import requests

BASE_URL = "http://localhost:8000/v1"


def generate_synthetic_trip(driver_id: str, api_key: str, trip_type: str = "calm") -> str:
    """Generate a synthetic trip and upload it to the API."""

    # Start trip
    response = requests.post(
        f"{BASE_URL}/trips/start",
        headers={"X-API-Key": api_key},
    )
    response.raise_for_status()
    trip_id = response.json()["trip_id"]
    print(f"Started trip {trip_id} ({trip_type})")

    return trip_id


def register_and_simulate(trip_type: str = "calm") -> str:
    """Register a new driver and simulate a trip."""
    # Register driver
    response = requests.post(f"{BASE_URL}/drivers/register")
    response.raise_for_status()
    data = response.json()
    driver_id = data["driver_id"]
    api_key = data["api_key"]
    print(f"Registered driver: {driver_id}")

    # Give consent
    response = requests.post(
        f"{BASE_URL}/consent",
        headers={"X-API-Key": api_key},
        json={"driver_id": driver_id, "version": "1.0"},
    )
    response.raise_for_status()
    print("Consent recorded")

    # Start trip
    response = requests.post(
        f"{BASE_URL}/trips/start",
        headers={"X-API-Key": api_key},
    )
    response.raise_for_status()
    trip_id = response.json()["trip_id"]
    print(f"Started trip {trip_id} ({trip_type})")

    # Generate trip data
    start_time = int(time.time() * 1000)
    duration_s = random.randint(300, 900)  # 5-15 minutes
    end_time = start_time + duration_s * 1000

    # Base location (Hong Kong)
    base_lat = 22.3193 + random.uniform(-0.05, 0.05)
    base_lon = 114.1694 + random.uniform(-0.05, 0.05)

    chunks = []
    chunk_seq = 0

    for chunk_start in range(start_time, end_time, 60000):  # 60-second chunks
        chunk_end = min(chunk_start + 60000, end_time)
        imu_samples = []
        gps_samples = []

        for t in range(chunk_start, chunk_end, 20):  # 50 Hz IMU
            if trip_type == "aggressive":
                ax = random.uniform(-0.8, 0.8)
                ay = random.uniform(-0.6, 0.6)
            else:
                ax = random.uniform(-0.2, 0.2)
                ay = random.uniform(-0.15, 0.15)

            # Add known harsh events
            if trip_type == "aggressive" and random.random() < 0.001:
                ax = random.uniform(-0.6, -0.4)  # harsh brake
            elif trip_type == "aggressive" and random.random() < 0.001:
                ax = random.uniform(0.4, 0.6)  # harsh accel

            imu_samples.append({
                "t": t,
                "ax": ax,
                "ay": ay,
                "az": 9.8 + random.uniform(-0.1, 0.1),
                "gx": random.uniform(-0.1, 0.1),
                "gy": random.uniform(-0.1, 0.1),
                "gz": random.uniform(-0.1, 0.1),
            })

        for t in range(chunk_start, chunk_end, 1000):  # 1 Hz GPS
            progress = (t - start_time) / (end_time - start_time)
            lat = base_lat + progress * random.uniform(0.01, 0.03)
            lon = base_lon + progress * random.uniform(0.01, 0.03)

            speed = random.uniform(8, 20) if trip_type == "calm" else random.uniform(10, 35)

            gps_samples.append({
                "t": t,
                "lat": lat,
                "lon": lon,
                "speed": speed,
                "heading": random.uniform(0, 360),
                "accuracy": random.uniform(3, 10),
            })

        chunks.append({
            "seq": chunk_seq,
            "imu": imu_samples,
            "gps": gps_samples,
        })
        chunk_seq += 1

    # Upload chunks
    for chunk in chunks:
        response = requests.post(
            f"{BASE_URL}/trips/{trip_id}/chunks",
            headers={"X-API-Key": api_key},
            json=chunk,
        )
        response.raise_for_status()
        print(f"  Uploaded chunk {chunk['seq']}")

    # End trip
    response = requests.post(
        f"{BASE_URL}/trips/{trip_id}/end",
        headers={"X-API-Key": api_key},
    )
    response.raise_for_status()
    print(f"Ended trip {trip_id}, processing started")

    return trip_id


def main():
    parser = argparse.ArgumentParser(description="Simulate trips for DriveScore")
    parser.add_argument("--driver-id", help="Driver ID (if not provided, registers a new driver)")
    parser.add_argument("--api-key", help="Driver API key (required if driver-id is provided)")
    parser.add_argument("--type", choices=["calm", "aggressive"], default="calm", help="Trip type")
    parser.add_argument("--count", type=int, default=1, help="Number of trips")

    args = parser.parse_args()

    for i in range(args.count):
        if args.driver_id and args.api_key:
            trip_id = generate_synthetic_trip(args.driver_id, args.api_key, args.type)
        else:
            trip_id = register_and_simulate(args.type)
        print(f"Trip {i+1}/{args.count} complete: {trip_id}")
        time.sleep(1)


if __name__ == "__main__":
    main()
