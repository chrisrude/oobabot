# Purpose: Client for generating images using the AUTOMATIC1111
# API.  Takes a prompt and returns image binary data in PNG format.
#

import asyncio
import base64
from typing import Dict

import aiohttp

from oobabot.fancy_logging import get_logger


class StableDiffusionClientError(Exception):
    pass


class StableDiffusionClient:
    # Purpose: Client for a Stable Diffusion API.

    DEFAULT_IMG_WIDTH = 256
    DEFAULT_IMG_HEIGHT = DEFAULT_IMG_WIDTH
    DEFAULT_STEPS = 10
    # DEFAULT_SAMPLER = "DPM++ 2M Karras"
    # CHECKPOINT = "Deliberate-2.0-15236.safetensors [9aba26abdf]"

    # trying to set the checkpoint is a bit of a pain, see
    # https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/3703#issuecomment-1368143965
    # > "to set checkpoint, use options endpoint, pass in key='option name'
    # >  and value='option value', both taken from options dropdown UI element."
    #
    # Name and value turn out to both be the same.
    #
    # valid values on my deployment:
    #  - 'Anything-V3.0.ckpt [812cd9f9d9]'
    #  - 'AOM3A1.safetensors'
    #  - 'Deliberate-2.0-15236.safetensors [9aba26abdf]'
    #  - 'sd-v1-5-inpainting.ckpt'
    #  - 'v1-5-pruned-emaonly.ckpt'
    #
    # since these are going to vary a lot, I'll only set it as a
    # command-line option, but otherwise just print out what it's
    # set to and the options.

    API_URI_PATH = "/sdapi/v1/"

    API_COMMAND_URLS = {
        "get_samplers": API_URI_PATH + "samplers",
        # get_samplers: GET only
        #   returns a list of samplers which we can use
        #   in text2img
        "options": API_URI_PATH + "options",
        # options: GET and POST
        #   retrieves (GET) and sets (POST) global options
        #   for the server.  This is how we set the checkpoint
        #   and also a few privacy-related fields.
        "progress": API_URI_PATH + "progress",
        # progress: GET only
        #   returns the progress of the current image generation
        "txt2img": API_URI_PATH + "txt2img",
        # txt2img: POST only
        #   takes a prompt, generates an image and returns it
    }

    def __init__(
        self,
        base_url: str,
        checkpoint: str | None = None,
        sampler: str | None = None,
        img_width: int = DEFAULT_IMG_WIDTH,
        img_height: int = DEFAULT_IMG_HEIGHT,
        steps: int = DEFAULT_STEPS,
    ):
        self._base_url = base_url
        self._checkpoint = checkpoint
        self._sampler = sampler
        self._img_width = img_width
        self._img_height = img_height
        self._steps = steps
        self._session = None

    # set default negative prompts to make it more difficult
    # to create content against the discord TOS
    # https://discord.com/guidelines

    # use this prompt for "age_restricted" channels
    #  i.e. channel.nsfw is true
    DEFAULT_NEGATIVE_PROMPT_NSFW = (
        "naked children, child sexualization, lolicon, "
        + "suicide, self-harm, "
        + "excessive violence, "
        + "animal harm"
    )

    # use this prompt for non-age-restricted channels
    DEFAULT_NEGATIVE_PROMPT = (
        DEFAULT_NEGATIVE_PROMPT_NSFW + ", sexually explicit content"
    )

    DEFAULT_REQUEST_PARAMS: Dict[str, bool | int | str] = {
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
        options = self.DEFAULT_OPTIONS.copy()
        if self._checkpoint is not None:
            options["checkpoint"] = self._checkpoint

        async with (await self._get_session()).post(url, json=options) as response:
            if response.status != 200:
                raise StableDiffusionClientError(response)
            response = await response.json()

    async def get_samplers(self) -> list[str]:
        get_logger().debug("listing available samplers from Stable Diffusion")
        url = self.API_COMMAND_URLS["get_samplers"]
        async with (await self._get_session()).get(url) as response:
            if response.status != 200:
                raise StableDiffusionClientError(response)
            response = await response.json()
            samplers = [str(sampler["name"]) for sampler in response]
            return samplers

    def generate_image(
        self,
        prompt: str,
        sampler_name: str | None = None,
        negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
        steps: int = DEFAULT_STEPS,
        width: int = DEFAULT_IMG_WIDTH,
        height: int = DEFAULT_IMG_HEIGHT,
    ) -> asyncio.Task[bytes]:
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
        #     OobaClientError, if the request fails.
        request = self.DEFAULT_REQUEST_PARAMS.copy()
        request.update(
            {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "steps": steps,
                "width": width,
                "height": height,
            }
        )
        if sampler_name is not None:
            request["sampler_name"] = sampler_name

        async def do_post() -> bytes:
            get_logger().debug(f"posting image request: {request}")

            async with (await self._get_session()).post(
                self.API_COMMAND_URLS["txt2img"],
                json=request,
            ) as response:
                if response.status != 200:
                    raise StableDiffusionClientError(response)
                json_body = await response.json()
                print("got n images: {}", len(json_body["images"]))
                bytes = base64.b64decode(json_body["images"][0])
                print(
                    "image generated, {} bytes: {}....".format(len(bytes), bytes[:10])
                )
                return bytes

        # works around aiohttp being bad
        async def do_post_with_retry() -> bytes:
            tries = 0
            while True:
                try:
                    return await do_post()
                except aiohttp.ClientOSError as e:
                    if e.__cause__ is not ConnectionResetError:
                        raise e
                    if tries > 2:
                        raise e
                    get_logger().warning(
                        f"Connection reset error: {e}, retrying in 1 second"
                    )
                    await asyncio.sleep(1)
                    tries += 1

        return asyncio.create_task(do_post_with_retry())

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("session not initialized")
        return self._session

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit_per_host=1)
        self._session = aiohttp.ClientSession(
            base_url=self._base_url, connector=connector
        )
        return self

    async def __aexit__(self, *_err):
        if self._session:
            await self._session.close()
        self._session = None

    async def start(self):
        get_logger().info(f"Connecting to stable diffusion at {self._base_url}")
        samplers = await self.get_samplers()
        for sampler in samplers:
            get_logger().debug(f"Sampler available: {sampler}")
        await self.set_options()
