#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import signal
import sys

import aiohttp

from oobabot import bot_commands
from oobabot import decide_to_respond
from oobabot import discord_bot
from oobabot import fancy_logger
from oobabot import http_client
from oobabot import image_generator
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import response_stats
from oobabot import sd_client
from oobabot import settings
from oobabot import templates


def verify_client(client, service_name, url):
    async def try_setup(client):
        assert client is not None
        async with client:
            await client.setup()

    logger = fancy_logger.get()
    logger.info(f"{service_name} is at {url}")
    try:
        asyncio.run(try_setup(client))
    except (http_client.OobaClientError, aiohttp.ClientConnectionError) as e:
        logger.error(f"Could not connect to {service_name} server: [{url}]")
        logger.error("Please check the URL and try again.")
        logger.error(f"Reason: {e}")
        sys.exit(1)
    logger.info(f"Connected to {service_name}!")


def main():
    logger = fancy_logger.init_logging()

    settings_obj = settings.Settings()
    settings_obj.load()
    if not settings_obj.discord_token:
        msg = (
            f"Please set the '{settings_obj.DISCORD_TOKEN_ENV_VAR}' "
            + "environment variable to your bot's discord token."
        )
        # will exit() after printing
        settings_obj.error(msg)

    aggregate_response_stats = None

    def sigint_handler(_signum, _frame):
        logger.info("Received SIGINT, exiting...")
        if aggregate_response_stats is not None:
            aggregate_response_stats.write_stat_summary_to_log()
        exit(1)

    signal.signal(signal.SIGINT, sigint_handler)

    ########################################################
    # Connect to Oobabooga

    ooba_client_obj = ooba_client.OobaClient(
        settings_obj.base_url, settings_obj.OOBABOOGA_DEFAULT_REQUEST_PARAMS
    )
    verify_client(ooba_client_obj, "Oobabooga", settings_obj.base_url)

    ########################################################
    # Connect to Stable Diffusion, if configured

    stable_diffusion_client = None
    if settings_obj.stable_diffusion_url:
        stable_diffusion_client = sd_client.StableDiffusionClient(
            base_url=settings_obj.stable_diffusion_url,
            negative_prompt=settings_obj.stable_diffusion_negative_prompt,
            negative_prompt_nsfw=settings_obj.stable_diffusion_negative_prompt_nsfw,
            image_width=settings_obj.image_width,
            image_height=settings_obj.image_height,
            steps=settings_obj.diffusion_steps,
            desired_sampler=settings_obj.stable_diffusion_sampler,
        )
        verify_client(
            stable_diffusion_client,
            "Stable Diffusion",
            settings_obj.stable_diffusion_url,
        )

    ########################################################
    # Bot logic

    # decides which messages the bot will respond to
    decide_to_responder = decide_to_respond.DecideToRespond(
        settings_obj.wakewords,
        settings_obj.ignore_dms,
        settings_obj.DECIDE_TO_RESPOND_INTERROBANG_BONUS,
        settings_obj.DECIDE_TO_RESPOND_TIME_VS_RESPONSE_CHANCE,
    )

    # templates used to generate prompts to send to the AI
    # as well as for some UI elements
    template_store = templates.TemplateStore()

    # once we decide to respond, this generates a prompt
    # to send to the AI, given a message history
    prompt_generator_obj = prompt_generator.PromptGenerator(
        ai_name=settings_obj.ai_name,
        persona=settings_obj.persona,
        history_lines=settings_obj.history_lines,
        token_space=settings_obj.OOBABOT_MAX_AI_TOKEN_SPACE,
        template_store=template_store,
        dont_split_responses=settings_obj.dont_split_responses,
    )

    # tracks of the time spent on responding, success rate, etc.
    aggregate_response_stats = response_stats.AggregateResponseStats(
        fn_get_total_tokens=lambda: ooba_client_obj.total_response_tokens
    )

    # generates images, if stable diffusion is configured
    # also includes a UI to regenerate images on demand
    image_generator_obj = None
    if stable_diffusion_client is not None:
        image_generator_obj = image_generator.ImageGenerator(
            stable_diffusion_client=stable_diffusion_client,
            image_words=settings_obj.image_words,
            template_store=template_store,
        )

    # if a bot sees itself repeating a message over and over,
    # it will keep doing so forever.  This attempts to fix that.
    # by looking for repeated responses, and deciding how far
    # back in history the bot can see.
    tracker = repetition_tracker.RepetitionTracker(
        repetition_threshold=settings_obj.REPETITION_TRACKER_THRESHOLD
    )

    bot_commands_obj = bot_commands.BotCommands(
        ai_name=settings_obj.ai_name,
        decide_to_respond=decide_to_responder,
        repetition_tracker=tracker,
        reply_in_thread=settings_obj.reply_in_thread,
        template_store=template_store,
    )

    ########################################################
    # Connect to Discord

    logger.info("Connecting to Discord... ")
    bot = discord_bot.DiscordBot(
        ooba_client_obj,
        decide_to_respond=decide_to_responder,
        prompt_generator=prompt_generator_obj,
        repetition_tracker=tracker,
        response_stats=aggregate_response_stats,
        image_generator=image_generator_obj,
        bot_commands=bot_commands_obj,
        ai_name=settings_obj.ai_name,
        persona=settings_obj.persona,
        ignore_dms=settings_obj.ignore_dms,
        dont_split_responses=settings_obj.dont_split_responses,
        reply_in_thread=settings_obj.reply_in_thread,
        log_all_the_things=settings_obj.log_all_the_things,
    )

    # opens http connections to our services,
    # then connects to Discord
    async def init_then_start():
        try:
            if stable_diffusion_client is not None:
                async with stable_diffusion_client:
                    async with ooba_client_obj:
                        try:
                            await bot.start(settings_obj.discord_token)
                        finally:
                            await bot.close()
            else:
                async with ooba_client_obj:
                    try:
                        await bot.start(settings_obj.discord_token)
                    finally:
                        await bot.close()
        except Exception as e:
            logger.error(f"Error starting bot: {e}")

    asyncio.run(init_then_start())
