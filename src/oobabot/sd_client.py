# Purpose: Client for generating images using the AUTOMATIC1111
# API.  Takes a prompt and returns image binary data in PNG format.
#

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
    LOG_PREFIX = SERVICE_NAME + ": "
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
        base_url: str,
        negative_prompt: str,
        negative_prompt_nsfw: str,
        image_width: int,
        image_height: int,
        steps: int,
        desired_sampler: typing.Optional[str] = None,
    ):
        super().__init__(self.SERVICE_NAME, base_url)

        self.negative_prompt = negative_prompt
        self.negative_prompt_nsfw = negative_prompt_nsfw

        self._sampler = None
        self.desired_sampler = desired_sampler

        self.image_width = image_width
        self.image_height = image_height

        self._steps = steps

    # set default negative prompts to make it more difficult
    # to create content against the discord TOS
    # https://discord.com/guidelines

    DEFAULT_REQUEST_PARAMS: typing.Dict[str, typing.Union[bool, int, str]] = {
        # default values are commented out
        #
        # "do_not_save_samples": False,
        #    This is a privacy concern for the users of the service.
        #    We don't want to save the generated images anyway, since they
        #    are going to be on Discord.  Also, we don't want to use the
        #    disk space.
        "do_not_save_samples": True,
        #
        # "do_not_save_grid": False,
        #    Sames as above.
        "do_not_save_grid": True,
    }

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
        async with self.get_session().get(url) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            current_options = await response.json()

        # now, set the options
        options_to_set = {}
        for k, v in self.DEFAULT_OPTIONS.items():
            if k not in current_options:
                continue
            if v == current_options[k]:
                continue
            options_to_set[k] = v
            fancy_logger.get().info(
                self.LOG_PREFIX
                + f" changing option '{k}' from to "
                + f"'{current_options[k]}' to '{v}'"
            )

        if not options_to_set:
            fancy_logger.get().debug(
                self.LOG_PREFIX + "Options are already set correctly, no changes made."
            )
            return

        async with self.get_session().post(url, json=options_to_set) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            await response.json()

    async def get_samplers(self) -> typing.List[str]:
        url = self.API_COMMAND_URLS["get_samplers"]
        async with self.get_session().get(url) as response:
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
        # Purpose: Generate an image from a prompt.
        # Args:
        #     prompt: The prompt to generate an image from.
        #     negative_prompt: The negative prompt to use.
        #     sampler_name: The sampler to use.
        #     steps: The number of steps to use.
        #     width: The width of the image.
        #     height: The height of the image.
        # Returns:
        #     The image as bytes.
        # Raises:
        #     OobaHttpClientError, if the request fails.
        request = self.DEFAULT_REQUEST_PARAMS.copy()
        negative_prompt = self.negative_prompt
        if is_channel_nsfw:
            negative_prompt = self.negative_prompt_nsfw
        request.update(
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": self._steps,
                "width": self.image_width,
                "height": self.image_height,
            }
        )
        if self._sampler is not None:
            request["sampler_name"] = self._sampler

        async def do_post() -> bytes:
            fancy_logger.get().debug(
                self.LOG_PREFIX
                + f"Image request (nsfw: {is_channel_nsfw}): {request['prompt']}"
            )
            start_time = time.time()

            async with self.get_session().post(
                self.API_COMMAND_URLS["txt2img"],
                json=request,
            ) as response:
                if response.status != 200:
                    raise http_client.OobaHttpClientError(response)
                duration = time.time() - start_time
                json_body = await response.json()
                bytes = base64.b64decode(json_body["images"][0])
                fancy_logger.get().debug(
                    self.LOG_PREFIX
                    + "Image generated, {} bytes in {:.2f} seconds".format(
                        len(bytes), duration
                    )
                )
                return bytes

        # works around aiohttp being bad
        async def do_post_with_retry() -> bytes:
            tries = 0
            while True:
                try:
                    return await do_post()
                except aiohttp.ClientOSError as err:
                    if err.__cause__ is not ConnectionResetError:
                        raise err
                    if tries > 2:
                        raise err
                    fancy_logger.get().warning(
                        self.LOG_PREFIX
                        + "Connection reset error: %s, retrying in 1 second",
                        err,
                    )
                    await asyncio.sleep(1)
                    tries += 1

        return asyncio.create_task(do_post_with_retry())

    async def set_sampler(self):
        """Sets the sampler to use, if it is available."""
        samplers = await self.get_samplers()
        if self.desired_sampler is not None:
            if self.desired_sampler in samplers:
                fancy_logger.get().debug(
                    self.LOG_PREFIX + "Using desired sampler '%s'", self.desired_sampler
                )
                self._sampler = self.desired_sampler
            else:
                fancy_logger.get().warn(
                    self.LOG_PREFIX + "Desired sampler '%s' not available",
                    self.desired_sampler,
                )
                self._sampler = None
        if self._sampler is None:
            fancy_logger.get().debug(
                self.LOG_PREFIX + "Using default sampler on SD server"
            )
            fancy_logger.get().debug(
                self.LOG_PREFIX + "Available samplers: %s", ", ".join(samplers)
            )
            self._sampler = None

    async def _setup(self):
        await self.set_sampler()
        await self.set_options()
        fancy_logger.get().debug(
            self.LOG_PREFIX
            + "Using negative prompt: "
            + self.negative_prompt[:20]
            + "..."
        )
