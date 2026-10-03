import random
import time
import requests

BASE_URL = "http://localhost:8000/v1"


def register_driver() -> tuple:
    """Register a new driver and return (driver_id, api_key)."""
    response = requests.post(f"{BASE_URL}/drivers/register")
    response.raise_for_status()
    data = response.json()
    return data["driver_id"], data["api_key"]


def give_consent(driver_id: str, api_key: str) -> None:
    """Give consent for a driver."""
    response = requests.post(
        f"{BASE_URL}/consent",
        headers={"X-API-Key": api_key},
        json={"version": "1.0"},
    )
    response.raise_for_status()


def simulate_trip(driver_id: str, api_key: str, trip_type: str) -> None:
    """Simulate a single trip."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/simulate.py",
         "--api-key", api_key,
         "--type", trip_type,
         "--count", "1"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Error simulating trip: {result.stderr}")
    else:
        print(result.stdout)


def main():
    print("Seeding database with 30 drivers...")

    drivers = []
    for i in range(30):
        driver_id, api_key = register_driver()
        give_consent(driver_id, api_key)
        drivers.append((driver_id, api_key))
        print(f"Registered driver {i+1}/30: {driver_id}")

    print("\nSimulating trips...")
    for i, (driver_id, api_key) in enumerate(drivers):
        # Mix of calm, moderate, and aggressive drivers so every tier shows up
        trip_type = "calm" if i < 12 else "moderate" if i < 22 else "aggressive"
        num_trips = random.randint(3, 8)

        for j in range(num_trips):
            print(f"Driver {i+1}/30, trip {j+1}/{num_trips} ({trip_type})")
            simulate_trip(driver_id, api_key, trip_type)
            time.sleep(0.5)

    print("\nSeeding complete!")


if __name__ == "__main__":
    main()
