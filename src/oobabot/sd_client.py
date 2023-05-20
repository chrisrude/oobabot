# -*- coding: utf-8 -*-
"""
Client for generating images using the AUTOMATIC1111
API.  Takes a prompt and returns image binary data in PNG format.
"""

import asyncio
import base64
import time
import typing

import aiohttp

from oobabot import fancy_logger
from oobabot import http_client

# todo: response stats for SD client


class StableDiffusionClient(http_client.SerializedHttpClient):
    """
    Purpose: Client for generating images using the AUTOMATIC1111
    API.  Takes a prompt and returns image binary data in PNG format.
    """

    SERVICE_NAME = "Stable Diffusion"
    STABLE_DIFFUSION_API_URI_PATH: str = "/sdapi/v1/"

    API_COMMAND_URLS = {
        "get_samplers": STABLE_DIFFUSION_API_URI_PATH + "samplers",
        # get_samplers: GET only
        #   returns a list of samplers which we can use
        #   in text2img
        "options": STABLE_DIFFUSION_API_URI_PATH + "options",
        # options: GET and POST
        #   retrieves (GET) and sets (POST) global options
        #   for the server.  This is how we set the checkpoint
        #   and also a few privacy-related fields.
        "progress": STABLE_DIFFUSION_API_URI_PATH + "progress",
        # progress: GET only
        #   returns the progress of the current image generation
        "txt2img": STABLE_DIFFUSION_API_URI_PATH + "txt2img",
        # txt2img: POST only
        #   takes a prompt, generates an image and returns it
    }

    def __init__(
        self,
        settings: typing.Dict[str, typing.Any],
    ):
        super().__init__(self.SERVICE_NAME, settings["stable_diffusion_url"])

        self.extra_prompt_text = settings["extra_prompt_text"]
        self.request_params = settings["request_params"]

        # when we're in a "age restricted" channel, we'll swap
        # the "negative_prompt" in the request_params with this
        # value.  Otherwise we'll use the one already in
        # request_params["negative_prompt"]
        self.negative_prompt_nsfw = self.request_params.pop("negative_prompt_nsfw", "")

    DEFAULT_OPTIONS = {
        #
        # - "enable_pnginfo"
        #   by default, this will store the parameters used to generate the image.
        #   For instance:
        #         Parameters: zombie taylor swift pinup movie posterSteps: 30,
        #           Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 1317257172,
        #           Size: 768x768, Model hash: 9aba26abdf, Model: Deliberate-2.0-15236
        #   We want to disable this, for a few reasons:
        #   - it's a privacy concern, since it's not clear to the user what
        #     is happening
        #   - it will include our negative prompts, which are actually bad
        #     phrases that represent content we DON'T want to generate.  If
        #     we upload these same strings to Discord, they might mistakenly
        #     flag the content as violating their TOS.  Even though the only
        #     reason those strings are used is to prevent that content.
        "enable_pnginfo": False,
        #
        # - "do_not_add_watermark"
        #    Similar to the above, we don't want to add a watermark to the
        #    generated image, just since it looks bad.  Also, it can leak
        #    the version of the SD software we are using, which isn't a good
        #    idea for security reasons.
        "do_not_add_watermark": True,
        #
        # - "samples_format"
        #   this is the format used for all image generation.
        "samples_format": "png",
    }

    async def set_options(self):
        url = self.API_COMMAND_URLS["options"]

        # first, get the current options.  We do this for two
        # reasons;
        #  - show the user exactly what we changed, if anything
        #  - some versions of the API don't support the
        #    "do_not_add_watermark" option, so we need to
        #    check if it's there before we try to set it
        #
        current_options = None
        async with self._get_session().get(url) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            current_options = await response.json()

        options_to_set = {}
        for option_name, option_value in self.DEFAULT_OPTIONS.items():
            if option_name not in current_options:
                continue
            if option_value == current_options[option_name]:
                continue
            options_to_set[option_name] = option_value
            fancy_logger.get().info(
                "Stable Diffusion:  changing option '%s' from to '%s' to '%s'",
                option_name,
                current_options[option_name],
                option_value,
            )

        if not options_to_set:
            fancy_logger.get().debug(
                "Stable Diffusion: Options are already set correctly, no changes made."
            )
            return

        async with self._get_session().post(url, json=options_to_set) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            await response.json()

    async def get_samplers(self) -> typing.List[str]:
        url = self.API_COMMAND_URLS["get_samplers"]
        async with self._get_session().get(url) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            response = await response.json()
            samplers = [str(sampler["name"]) for sampler in response]
            return samplers

    def generate_image(
        self,
        prompt: str,
        is_channel_nsfw: bool = False,
    ) -> "asyncio.Task[bytes]":
        """
        Generate an image from a prompt.
        Args:
            prompt: The prompt to generate an image from.
            is_channel_nsfw: Whether the channel is NSFW.
            this will change the negative prompt.
        Returns:
            The image as bytes.
        Raises:
            OobaHttpClientError, if the request fails.
        """
        request = self.request_params.copy()
        request["prompt"] = prompt
        if is_channel_nsfw:
            request["negative_prompt"] = self.negative_prompt_nsfw

        if self.extra_prompt_text:
            request["prompt"] += ", " + self.extra_prompt_text

        async def do_post() -> bytes:
            fancy_logger.get().debug(
                "Stable Diffusion: Image request (nsfw: %r): %s",
                is_channel_nsfw,
                request["prompt"],
            )
            start_time = time.time()

            async with self._get_session().post(
                self.API_COMMAND_URLS["txt2img"],
                json=request,
            ) as response:
                if response.status != 200:
                    raise http_client.OobaHttpClientError(response)
                duration = time.time() - start_time
                json_body = await response.json()
                image_bytes = base64.b64decode(json_body["images"][0])
                fancy_logger.get().debug(
                    "Stable Diffusion: Image generated, %d bytes in %.2f seconds",
                    len(image_bytes),
                    duration,
                )
                return image_bytes

        # works around aiohttp being bad
        async def do_post_with_retry() -> bytes:
            tries = 0
            while True:
                try:
                    return await do_post()
                except (aiohttp.ClientError, aiohttp.ClientOSError) as err:
                    retry = False
                    if err.__cause__ is ConnectionResetError:
                        retry = True
                    if isinstance(err, aiohttp.ClientOSError) and 104 == err.errno:
                        retry = True
                    if tries > 2:
                        retry = False
                    if not retry:
                        raise

                    fancy_logger.get().warning(
                        "Stable Diffusion: Connection reset error: %s, "
                        + "retrying in 1 second",
                        err,
                    )
                    await asyncio.sleep(1)
                    tries += 1

        return asyncio.create_task(do_post_with_retry())

    async def verify_sampler_available(self):
        """
        Checks that the requested sampler is available on the server.
        If it isn't, logs a warning and sets the sampler to the default.
        """
        samplers = await self.get_samplers()

        desired_sampler = self.request_params.get("sampler")
        if not desired_sampler:
            fancy_logger.get().debug(
                "Stable Diffusion: Using default sampler on SD server"
            )
            return

        if desired_sampler in samplers:
            fancy_logger.get().debug(
                "Stable Diffusion: Using desired sampler '%s'", desired_sampler
            )
            return

        fancy_logger.get().warning(
            "Stable Diffusion: Desired sampler '%s' not available",
            desired_sampler,
        )
        fancy_logger.get().info(
            "Stable Diffusion: Available samplers: %s", ", ".join(samplers)
        )
        self.request_params["sampler"] = ""

    async def _setup(self):
        await self.verify_sampler_available()
        await self.set_options()
        fancy_logger.get().debug(
            "Stable Diffusion: Using negative prompt: %s...",
            str(self.request_params.get("negative_prompt", ""))[:20],
        )
        if self.extra_prompt_text:
            fancy_logger.get().debug(
                "Stable Diffusion: will append to every prompt: '%s'",
                self.extra_prompt_text,
            )
