import os

from inventory_web import create_app
from waitress import serve


app = create_app()


if __name__ == "__main__":
    serve(
        app,
        host=os.getenv("WEB_HOST", "0.0.0.0"),
        port=int(os.getenv("WEB_PORT", "5000")),
        threads=4,
    )
