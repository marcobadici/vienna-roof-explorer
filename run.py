"""
Entry point for the Flask server.

Usage:
    python run.py

Make sure you've built the map at least once first:
    python build_map.py
"""

from app import create_app
from app.config import Config


app = create_app()


if __name__ == "__main__":

    print(
        f"Open: http://{Config.HOST}:{Config.PORT}"
    )

    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
    )