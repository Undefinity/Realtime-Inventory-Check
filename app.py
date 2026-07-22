import logging
import os

from inventory_web import create_app
from waitress import serve


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)


app = create_app()


if __name__ == "__main__":
    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "5000"))
    app.logger.info("库存盘点服务启动：监听 http://%s:%s", host, port)
    serve(app, host=host, port=port, threads=4)
