import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app


def main():
    openapi_schema = app.openapi()

    output_path = "contract/openapi.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(openapi_schema, f, indent=2)

    print(f"OpenAPI schema exported to {output_path}")


if __name__ == "__main__":
    main()
