# -*- coding: utf-8 -*-
"""
Client for generating images using the AUTOMATIC1111
API.  Takes a prompt and returns image binary data in PNG format.
"""

import asyncio
import base64
import re
import time
import typing

import aiohttp

from oobabot import fancy_logger
from oobabot import http_client

# todo: response stats for SD client


def _find_substring_in_dict(
    desired_val: str, search_list: typing.List
) -> typing.Optional[str]:
    desired_val = desired_val.lower()
    for value in search_list:
        if value.lower() in desired_val:
            return value
    return None


class StableDiffusionClient(http_client.SerializedHttpClient):
    """
    Purpose: Client for generating images using the AUTOMATIC1111
    API.  Takes a prompt and returns image binary data in PNG format.
    """

    SERVICE_NAME = "Stable Diffusion"
    STABLE_DIFFUSION_API_URI_PATH: str = "/sdapi/v1/"

    SAMPLER_KEY = "sampler_name"
    SAMPLER_KEY_ALIAS = "sampler"

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
        "sd-models": STABLE_DIFFUSION_API_URI_PATH + "sd-models",
        # sd-models: GET only
        # [
        #   {
        #     "title": "Anything-V3.0.ckpt [812cd9f9d9]",
        #     "model_name": "Anything-V3.0",
        #     "hash": "812cd9f9d9",
        #     "sha256": "812cd9f9d9a0cb62aaad605173fd64dea1....",
        #     "filename": "...long..path.../models/Stable-diffusion/Anything-V3.0.ckpt",
        #     "config": null
        #   },
        # ...
        # ]
    }

    def __init__(
        self,
        settings: typing.Dict[str, typing.Any],
        magic_model_key: str,
    ):
        super().__init__(self.SERVICE_NAME, settings["stable_diffusion_url"])

        self.extra_prompt_text = settings["extra_prompt_text"]
        self.request_params = settings["request_params"]

        # lower-case all keys in request_params
        self.request_params = {k.lower(): v for k, v in self.request_params.items()}
        self.sd_models = []
        self.sd_samplers = []

        self.user_override_params = {}
        # ensure that each customizable param is in the request_params
        for param in settings["user_override_params"]:
            param = param.lower()
            if param not in self.request_params:
                fancy_logger.get().warning(
                    "Stable Diffusion:  customizable param '%s' not in request_params."
                    + "  Ignoring setting.",
                    param,
                )
                continue
            # store the type of the param, so we can validate user input later
            self.user_override_params[param] = type(self.request_params[param])

        self.magic_model_key = magic_model_key.lower()

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

    async def _call_and_extract_field(
        self, command: str, field: str
    ) -> typing.List[str]:
        url = self.API_COMMAND_URLS[command]
        async with self._get_session().get(url) as response:
            if response.status != 200:
                raise http_client.OobaHttpClientError(response)
            response = await response.json()
            values = [str(value[field]) for value in response]
            return values

    async def get_samplers(self) -> typing.List[str]:
        return await self._call_and_extract_field("get_samplers", "name")

    async def get_models(self) -> typing.List[str]:
        return await self._call_and_extract_field("sd-models", "model_name")

    SD_DELIMITER = "="

    def _find_model(self, desired_model: str) -> typing.Optional[str]:
        return _find_substring_in_dict(desired_model, self.sd_models)

    def _find_sampler(self, desired_sampler: str) -> typing.Optional[str]:
        return _find_substring_in_dict(desired_sampler, self.sd_samplers)

    def _to_key_value_pair(
        self, word: str
    ) -> typing.Optional[typing.Tuple[str, typing.Any]]:
        if self.SD_DELIMITER not in word:
            return None

        keyword_pair = word.split(self.SD_DELIMITER, 1)
        if len(keyword_pair) < 2:
            return None
        key, val = keyword_pair

        # lowercase the key, so we can match it against the
        # user_override_params dict
        key = key.lower()

        # magical alias for "negative_prompt"
        if key == "np":
            key = "negative_prompt"

        if key == self.SAMPLER_KEY_ALIAS:
            key = self.SAMPLER_KEY

        if key not in self.user_override_params:
            return None

        # try to remove any quotes around the value
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]

        try:
            val_type = self.user_override_params[key]
            if val_type == bool:
                if val.lower in ("true", "yes", "y"):
                    val = True
                elif val.lower in ("false", "no", "n"):
                    val = False
            elif val_type == int:
                val = int(val)
            elif val_type == float:
                val = float(val)
        except ValueError:
            return None

        return (key, val)

    def update_model_and_sampler(self, params: typing.Dict[str, typing.Any]):
        """
        Model and Sampler are special since we have a list of known acceptable
        values.  If the user specifies a value that is not in the list, we
        ignore it.  If the user specifies a value that is in the list, we
        override the default.

        Also, "sampler" is an alias for "sampler_name", and "model" is an
        alias for what should appear in "override_settings.sd_model_checkpoint".

        Finally, we allow the user to specify a substring of the model or
        sampler name, and we will match the first one we find.  This is
        useful for when the user doesn't know the exact name of the model
        or sampler, but knows a substring of it.
        """
        desired_model = params.pop(self.magic_model_key, None)
        if desired_model is not None:
            model = self._find_model(desired_model)
            if model is not None:
                if "override_settings" not in params:
                    params["override_settings"] = {}
                params["override_settings"]["sd_model_checkpoint"] = model
                fancy_logger.get().debug(
                    "Stable Diffusion: per user request, setting model to '%s'", model
                )
            else:
                fancy_logger.get().debug(
                    "Stable Diffusion: unavailable model requested.  "
                    + "If newly added, restart oobabot: '%s'",
                    desired_model,
                )

        # the proper key is "sampler_name", but we also allow
        # "sampler" for convenience.  Move the value, if any, over now.
        desired_sampler = params.pop(self.SAMPLER_KEY_ALIAS, None)
        if desired_sampler is not None:
            params[self.SAMPLER_KEY] = desired_sampler

        desired_sampler = params.pop(self.SAMPLER_KEY, None)
        if desired_sampler is not None:
            sampler = self._find_sampler(desired_sampler)
            if sampler is not None:
                params[self.SAMPLER_KEY] = sampler
            else:
                fancy_logger.get().debug(
                    "Stable Diffusion: unavailable sampler requested.  "
                    + "If newly added, restart oobabot: '%s'",
                    desired_sampler,
                )

    # this is intended to split the prompt into words, but
    # also to handle quoted strings.  For instance, if the
    # prompt is:
    #   "zombie taylor swift" pinup movie poster
    # then we want to split it into:
    #   ["zombie taylor swift", "pinup", "movie", "poster"]
    #
    SD_PARAM_SPLIT_REGEX = re.compile(r'(?:".*?"|\S)+')

    def update_params(self, prompt: str, params: typing.Dict[str, typing.Any]) -> str:
        """
        Updates the request parameters included in the given prompt,
        and then returns the remaining prompt.
        """
        remaining_prompt = ""
        for word in self.SD_PARAM_SPLIT_REGEX.findall(prompt):
            key_val_pair = self._to_key_value_pair(word)
            if key_val_pair is None:
                remaining_prompt += word + " "
                continue
            key, val = key_val_pair

            fancy_logger.get().debug(
                "Stable Diffusion: per user request, setting '%s' to '%s'", key, val
            )
            params[key] = val

        self.update_model_and_sampler(params)

        return remaining_prompt.strip()

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

        if is_channel_nsfw:
            request["negative_prompt"] = self.negative_prompt_nsfw

        # extract any allowed user overrides from the prompt
        # and add them to the request dict.  The remaining
        # prompt is returned.
        request["prompt"] = self.update_params(prompt, request)

        if self.extra_prompt_text:
            request["prompt"] += ", " + self.extra_prompt_text

        async def do_post() -> bytes:
            fancy_logger.get().debug(
                "Stable Diffusion: Image request (nsfw: %r): %s",
                is_channel_nsfw,
                request,
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

    async def _setup(self):
        await self.set_options()
        self.sd_models = await self.get_models()
        self.sd_samplers = await self.get_samplers()
        fancy_logger.get().info(
            "Stable Diffusion: Available models: %s", ", ".join(self.sd_models)
        )
        # log a warning if the default model is not available
        desired_model = self.request_params.get(self.magic_model_key, None)
        if desired_model:
            model = self._find_model(desired_model)
            if model is None:
                fancy_logger.get().warning(
                    "Stable Diffusion: Desired default model '%s' not available.",
                    desired_model,
                )
            else:
                fancy_logger.get().debug(
                    "Stable Diffusion: Using default model '%s'", desired_model
                )

        fancy_logger.get().info(
            "Stable Diffusion: Available samplers: %s", ", ".join(self.sd_samplers)
        )
        # log a warning if the default sampler is not available
        desired_sampler = self.request_params.get(
            self.SAMPLER_KEY_ALIAS, self.request_params.get(self.SAMPLER_KEY, None)
        )
        if desired_sampler:
            sampler = self._find_sampler(desired_sampler)
            if sampler is None:
                fancy_logger.get().warning(
                    "Stable Diffusion: Desired default sampler '%s' not available.",
                    desired_sampler,
                )
            else:
                fancy_logger.get().debug(
                    "Stable Diffusion: Using default sampler '%s'", desired_sampler
                )

        fancy_logger.get().debug(
            "Stable Diffusion: Using negative prompt: %s...",
            str(self.request_params.get("negative_prompt", ""))[:20],
        )
        if self.extra_prompt_text:
            fancy_logger.get().debug(
                "Stable Diffusion: Bot will append to every prompt: '%s'",
                self.extra_prompt_text,
            )
        if 0 == len(self.user_override_params):
            fancy_logger.get().debug(
                "Stable Diffusion: Users cannot override any SD params"
            )
        else:
            fancy_logger.get().debug(
                "Stable Diffusion: Users may override: %s",
                ", ".join(self.user_override_params.keys()),
            )
