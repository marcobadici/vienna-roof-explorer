"""
Regenerates the static map HTML the Flask app serves.

Usage:
    python build_map.py

Run this once before the first `python run.py`, and again any time you
change app/map_builder.py.
"""

from app.config import Config, ensure_runtime_dirs
from app.map_builder import build_map


def main() -> None:
    ensure_runtime_dirs()

    vienna_map = build_map()
    vienna_map.save(Config.MAP_OUTPUT_FILE)

    print("Dynamic map generated successfully:")
    print(Config.MAP_OUTPUT_FILE)
    print()
    print("Now run:")
    print("python run.py")


if __name__ == "__main__":
    main()
