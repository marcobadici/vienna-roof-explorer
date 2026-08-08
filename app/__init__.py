from flask import Flask

from .config import Config


def create_app() -> Flask:
    """
    Create and configure the Flask application.
    """

    app = Flask(__name__)

    # Load project configuration
    app.config.from_object(Config)

    # Import here to avoid circular imports
    from .routes import bp

    # Register application routes
    app.register_blueprint(bp)

    return app