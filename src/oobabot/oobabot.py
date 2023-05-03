#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import signal
import sys

from oobabot.discord_bot import DiscordBot
from oobabot.fancy_logging import init_logging
from oobabot.ooba_client import OobaClient
from oobabot.settings import Settings


class LocalREPL:
    # local REPL for testing
    def __init__(self, ooba_client):
        self.ooba_client = ooba_client

    def show_prompt(self) -> None:
        print("\n>>> ", end='', flush=True)

    async def start(self) -> None:
        self.show_prompt()
        for user_prompt in sys.stdin:
            async for token in self.ooba_client.request_by_token(
                user_prompt
            ):
                if token:
                    print(token, end='', flush=True)
                else:
                    # end of response
                    print('')
            self.show_prompt()


def main():

    logger = init_logging()
    settings = Settings()

    bot = None

    def handler(_signum, _frame):
        logger.info('Received SIGINT, exiting...')
        if bot:
            # todo: await bot.close()
            bot.log_stats()
        exit(1)

    signal.signal(signal.SIGINT, handler)

    ooba_client = OobaClient(
        settings.base_url,
        request_prefix=settings.request_prefix)

    logger.debug(f'Oobabooga base URL: {settings.base_url}')
    connect_error_msg = asyncio.run(ooba_client.try_connect())
    if connect_error_msg:
        logger.error(
            f'Could not connect to ooba server: [{ooba_client.api_url}]')
        logger.error('Please check the URL and try again.')
        logger.error(f'Reason: {connect_error_msg}')
        sys.exit(1)

    logger.info('Connected to Oobabooga!')

    if ooba_client.request_prefix:
        logger.debug('Request prefix')
        logger.debug('--------------')
        for line in ooba_client.request_prefix.split('\n'):
            logger.debug(f'\t{line}')
    else:
        logger.debug('No request prefix supplied, using defaults')

    if settings.local_repl:
        logger.debug('Using local REPL, not connecting to Discord')
        coroutine = LocalREPL(ooba_client).start()
    else:
        logger.debug('Connecting to Discord... ')
        bot = DiscordBot(ooba_client, wakewords=settings.wakewords)
        coroutine = bot.start(settings.DISCORD_TOKEN_ENV_VAR)

    asyncio.run(coroutine)
