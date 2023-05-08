#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import signal
import sys

from oobabot.discord_bot import DiscordBot
from oobabot.fancy_logging import init_logging
from oobabot.ooba_client import OobaClient
from oobabot.ooba_client import OobaClientError
from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings


async def ainput(string: str) -> str:
    def prompt():
        sys.stdout.write(string)
        sys.stdout.write(" ")
        sys.stdout.flush()

    await asyncio.get_event_loop().run_in_executor(None, prompt)
    return await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)


class LocalREPL:
    # local REPL for testing
    def __init__(
        self, ooba_client, stable_diffusion_client: StableDiffusionClient | None = None
    ):
        self.ooba_client = ooba_client
        self.stable_diffusion_client = stable_diffusion_client

    def show_prompt(self) -> None:
        print("\n>>> ", end="", flush=True)

    async def start(self) -> None:
        def img_done(img_task):
            print("got image")
            print(img_task.result()[:10])
            bytes = img_task.result()
            with open("out.png", "wb") as binary_file:
                binary_file.write(bytes)

        if self.stable_diffusion_client:
            async with self.stable_diffusion_client:
                await self.stable_diffusion_client.start()
                while True:
                    user_prompt = await ainput(">>> ")
                    if "" == user_prompt.strip():
                        break
                    img_task = self.stable_diffusion_client.generate_image(user_prompt)
                    img_task.add_done_callback(img_done)

        else:
            self.show_prompt()
            for user_prompt in sys.stdin:
                async for token in self.ooba_client.request_by_token(user_prompt):
                    if token:
                        print(token, end="", flush=True)
                    else:
                        # end of response
                        print("")
                self.show_prompt()


def main():
    logger = init_logging()
    settings = Settings()

    bot = None

    def sigint_handler(_signum, _frame):
        logger.info("Received SIGINT, exiting...")
        if bot:
            bot.log_stats()
        exit(1)

    signal.signal(signal.SIGINT, sigint_handler)

    ooba_client = OobaClient(settings.base_url)

    if settings.stable_diffusion_url is not None:
        if settings.local_repl:
            logger.info(
                f"Using Stable Diffusion server at: {settings.stable_diffusion_url}"
            )
            stable_diffusion_client = StableDiffusionClient(
                settings.stable_diffusion_url
            )
            coroutine = LocalREPL(
                ooba_client, stable_diffusion_client=stable_diffusion_client
            ).start()
            asyncio.run(coroutine)
            return

    logger.debug(f"Oobabooga base URL: {settings.base_url}")
    try:
        asyncio.run(ooba_client.try_connect())
    except OobaClientError as e:
        logger.error(f"Could not connect to ooba server: [{ooba_client.api_url}]")
        logger.error("Please check the URL and try again.")
        logger.error(f"Reason: {e}")
        sys.exit(1)

    logger.info("Connected to Oobabooga!")

    stable_diffusion_client = None
    if settings.stable_diffusion_url:
        stable_diffusion_client = StableDiffusionClient(settings.stable_diffusion_url)

    logger.debug("Connecting to Discord... ")
    bot = DiscordBot(
        ooba_client,
        ai_name=settings.ai_name,
        ai_persona=settings.persona,
        wakewords=settings.wakewords,
        log_all_the_things=settings.log_all_the_things,
        stable_diffusion_client=stable_diffusion_client,
    )
    coroutine = bot.start(settings.DISCORD_TOKEN)

    asyncio.run(coroutine)
