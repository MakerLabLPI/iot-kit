"""python -m gamemaster: one asyncio process running the MQTT game loop
and the web server."""
import asyncio
import logging
import signal

from aiohttp import web

from .config import Config
from .game import Game
from .mqtt import MqttAdapter
from .web import make_app


async def main() -> None:
    cfg = Config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-5s %(message)s",
                        datefmt="%H:%M:%S")
    log = logging.getLogger("main")

    game = Game(cfg)
    mq = MqttAdapter(cfg, game, asyncio.get_running_loop())
    game.say("system", f"game master up — join on {cfg.topic_prefix}/<name>/join, "
                       f"move on {cfg.topic_prefix}/<name>/move")
    mq.start()
    game.start()

    runner = web.AppRunner(make_app(cfg, game), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", cfg.web_port).start()
    log.info("page on http://0.0.0.0:%d/  admin %s", cfg.web_port,
             "enabled" if cfg.admin_password else "disabled (set ADMIN_PASSWORD)")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("shutting down")
    await game.stop()
    mq.stop()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
