# -*- coding: utf-8 -*-
"""
Generates images from Stable Diffusion
"""

import asyncio
import io
import re
import typing

import discord

from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import http_client
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import sd_client
from oobabot import templates


async def image_task_to_file(image_task: "asyncio.Task[bytes]", image_request: str):
    await image_task
    img_bytes = image_task.result()
    file_of_bytes = io.BytesIO(img_bytes)
    file = discord.File(file_of_bytes)
    file.filename = "photo.png"
    file.description = f"image generated from '{image_request}'"
    return file


class StableDiffusionImageView(discord.ui.View):
    """
    A View that displays buttons to regenerate an image
    from Stable Diffusion with a new seed, or to lock
    in the current image.
    """

    LABEL_ACCEPT = "Accept"
    LABEL_DELETE = "Delete"

    # these two phrases (along with exactly two periods)
    # in "Drawing.." were chosen because they render at
    # the exact same width as each other.  If they don't,
    # the buttons will shift to the left and right as the
    # labels are swapped.
    LABEL_TRY_AGAIN = "Try Again"
    LABEL_DRAWING = "Drawing.."

    def __init__(
        self,
        stable_diffusion_client: sd_client.StableDiffusionClient,
        is_channel_nsfw: bool,
        image_prompt: str,
        requesting_user_id: int,
        requesting_user_name: str,
        template_store: templates.TemplateStore,
    ):
        super().__init__(timeout=120.0)

        self.template_store = template_store

        # only the user who requested generation of the image
        # can have it replaced
        self.requesting_user_id = requesting_user_id
        self.requesting_user_name = requesting_user_name
        self.image_prompt = image_prompt
        self.photo_accepted = False

        #####################################################
        # "Try Again" button
        #
        btn_try_again = discord.ui.Button(
            label=self.LABEL_TRY_AGAIN,
            style=discord.ButtonStyle.blurple,
            row=1,
        )
        self.image_message = None

        async def on_try_again(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return

            try:
                btn_try_again.label = self.LABEL_DRAWING

                # we disable all three buttons because otherwise
                # the lock_in and delete buttons will flicker
                # when we disable the try_again button.  And it
                # doesn't make much sense for them to work anyway
                # when the button is being regenerated.
                btn_try_again.disabled = True
                btn_lock_in.disabled = True
                btn_delete.disabled = True

                await interaction.response.defer()
                await self.get_image_message().edit(view=self)

                # generate a new image
                regen_task = stable_diffusion_client.generate_image(
                    image_prompt, is_channel_nsfw
                )
                regen_file = await image_task_to_file(regen_task, image_prompt)

                btn_try_again.label = self.LABEL_TRY_AGAIN
                btn_try_again.disabled = False
                btn_lock_in.disabled = False
                btn_delete.disabled = False

                await self.get_image_message().edit(attachments=[regen_file], view=self)
            except (http_client.OobaHttpClientError, discord.DiscordException) as err:
                fancy_logger.get().error(
                    "Could not regenerate image: %s", err, exc_info=True
                )

        btn_try_again.callback = on_try_again

        #####################################################
        # "Accept" button
        #
        btn_lock_in = discord.ui.Button(
            label=self.LABEL_ACCEPT,
            style=discord.ButtonStyle.success,
            row=1,
        )

        async def on_lock_in(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return
            await interaction.response.defer()
            await self.detach_view_keep_img()

        btn_lock_in.callback = on_lock_in

        #####################################################
        # "Delete" button
        #
        btn_delete = discord.ui.Button(
            label=self.LABEL_DELETE,
            style=discord.ButtonStyle.danger,
            row=1,
        )

        async def on_delete(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return
            await interaction.response.defer()
            await self.delete_image()

        btn_delete.callback = on_delete

        super().add_item(btn_try_again).add_item(btn_lock_in).add_item(btn_delete)

    def set_image_message(self, image_message: discord.Message):
        self.image_message = image_message

    def get_image_message(self) -> discord.Message:
        if self.image_message is None:
            raise ValueError("image_message is None")
        return self.image_message

    async def delete_image(self):
        await self.detach_view_delete_img(self.get_detach_message())

    async def detach_view_delete_img(self, detach_msg: str):
        await self.get_image_message().edit(
            content=detach_msg,
            view=None,
            attachments=[],
        )

    async def detach_view_keep_img(self):
        self.photo_accepted = True
        await self.get_image_message().edit(
            content=None,
            view=None,
        )

    async def on_timeout(self):
        if not self.photo_accepted:
            await self.delete_image()

    async def diy_interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Only allow the requesting user to interact with this view.
        """
        if interaction.user.id == self.requesting_user_id:
            return True
        error_message = self._get_message(templates.Templates.IMAGE_UNAUTHORIZED)
        await interaction.response.send_message(
            content=error_message,
            ephemeral=True,
        )
        return False

    def get_image_message_text(self) -> str:
        return self._get_message(templates.Templates.IMAGE_CONFIRMATION)

    def get_detach_message(self) -> str:
        return self._get_message(templates.Templates.IMAGE_DETACH)

    def _get_message(self, message_type: templates.Templates) -> str:
        return self.template_store.format(
            message_type,
            {
                templates.TemplateToken.USER_NAME: self.requesting_user_name,
                templates.TemplateToken.IMAGE_PROMPT: self.image_prompt,
            },
        )


class ImageGenerator:
    """
    Generates images from a given prompt, and posts that image as a
    message to a given channel.
    """

    # if a potential image prompt is shorter than this, we will
    # conclude that it is not an image prompt.
    MIN_IMAGE_PROMPT_LENGTH = 3

    def __init__(
        self,
        ooba_client: ooba_client.OobaClient,
        persona_settings: typing.Dict[str, typing.Any],
        prompt_generator: prompt_generator.PromptGenerator,
        sd_settings: typing.Dict[str, typing.Any],
        stable_diffusion_client: sd_client.StableDiffusionClient,
        template_store: templates.TemplateStore,
    ):
        self.ai_name = persona_settings.get("ai_name", "")
        self.ooba_client = ooba_client
        self.image_words = sd_settings.get("image_words", [])
        self.prompt_generator = prompt_generator
        self.stable_diffusion_client = stable_diffusion_client
        self.template_store = template_store
        self.use_ai_generated_keywords = sd_settings.get("use_ai_generated_keywords")

        self.image_patterns = [
            re.compile(
                r"^.*\b" + image_word + r"\b[\s]*(of|with)?[\s]*[:]?(.*)$",
                re.IGNORECASE,
            )
            for image_word in self.image_words
        ]

    def on_ready(self):
        """
        Called when the bot is connected to Discord.
        """
        if self.use_ai_generated_keywords:
            fancy_logger.get().debug(
                "Stable Diffusion: image prompts generated with AI preprocessing"
            )
        else:
            fancy_logger.get().debug(
                "Stable Diffusion: image prompts extracted with regex"
            )

        fancy_logger.get().debug(
            "Stable Diffusion: image keywords: %s",
            ", ".join(self.image_words),
        )

    async def _generate_image(
        self,
        image_prompt: str,
        raw_message: discord.Message,
        response_channel: discord.abc.Messageable,
    ) -> discord.Message:
        is_channel_nsfw = False

        # note: public threads in NSFW channels are not considered here
        if isinstance(raw_message.channel, discord.TextChannel):
            is_channel_nsfw = raw_message.channel.is_nsfw()

        image_task = self.stable_diffusion_client.generate_image(
            image_prompt, is_channel_nsfw=is_channel_nsfw
        )
        try:
            file = await image_task_to_file(image_task, image_prompt)
        except (http_client.OobaHttpClientError, discord.DiscordException) as err:
            fancy_logger.get().error("Could not generate image: %s", err, exc_info=True)
            error_message = self.template_store.format(
                templates.Templates.IMAGE_GENERATION_ERROR,
                {
                    templates.TemplateToken.USER_NAME: raw_message.author.display_name,
                    templates.TemplateToken.IMAGE_PROMPT: image_prompt,
                },
            )
            return await response_channel.send(error_message, reference=raw_message)

        regen_view = StableDiffusionImageView(
            self.stable_diffusion_client,
            is_channel_nsfw=is_channel_nsfw,
            image_prompt=image_prompt,
            requesting_user_id=raw_message.author.id,
            requesting_user_name=raw_message.author.display_name,
            template_store=self.template_store,
        )

        kwargs = {}
        # we can only pass a reference if the message is in the same channel
        # as the original request.  Also, send() won't take None of this
        # argument, so we need to conditionally add it.
        if raw_message.channel == response_channel:
            kwargs["reference"] = raw_message

        image_message = await response_channel.send(
            content=regen_view.get_image_message_text(),
            file=file,
            view=regen_view,
            **kwargs,
        )
        regen_view.image_message = image_message
        return image_message

    def maybe_get_image_prompt(
        self, raw_message: discord.Message
    ) -> typing.Optional[str]:
        for image_pattern in self.image_patterns:
            match = image_pattern.search(raw_message.content)
            if match:
                image_prompt = match.group(2)
                if len(image_prompt) < self.MIN_IMAGE_PROMPT_LENGTH:
                    continue
                fancy_logger.get().debug("Found image prompt: %s", image_prompt)
                return image_prompt
        return None

    async def generate_image(
        self,
        user_image_keywords: str,
        raw_message: discord.Message,
        response_channel: discord.abc.Messageable,
    ) -> "asyncio.Task[discord.Message]":
        """
        Kick off a task to generate an image, post it to the channel,
        and return message the image is posted in.
        """

        if self.use_ai_generated_keywords:
            # ignore the prompt extracted above, and instead pass
            # the raw message back to Oobabooga and ask it to
            # generate keywords.  Then pass those keywords to
            # the image generator.
            return asyncio.create_task(
                self._generate_keywords_then_image(
                    raw_message,
                    response_channel,
                )
            )

        return asyncio.create_task(
            self._generate_image(user_image_keywords, raw_message, response_channel)
        )

    async def _generate_keywords_then_image(
        self,
        raw_message: discord.Message,
        response_channel: discord.abc.Messageable,
    ) -> "discord.Message":
        message = discord_utils.discord_message_to_generic_message(raw_message)
        # remove the bot's name from the body text, so it doesn't
        # pollute the keywords
        message.body_text = message.body_text.replace(self.ai_name, "")
        keyword_generation_prompt = self.prompt_generator.keyword_generation_prompt(
            message
        )
        ai_keywords = await self.ooba_client.request_as_string(
            keyword_generation_prompt
        )
        fancy_logger.get().debug("AI-generated keywords: %s", ai_keywords)
        return await self._generate_image(ai_keywords, raw_message, response_channel)
