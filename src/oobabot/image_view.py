import asyncio
import io

import discord

from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings
from oobabot.types import MessageTemplate
from oobabot.types import TemplateToken


async def image_task_to_file(image_task: asyncio.Task[bytes], image_request: str):
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

    def __init__(
        self,
        sd_client: StableDiffusionClient,
        is_channel_nsfw: bool,
        image_request: str,
        requesting_user_id: int,
        requesting_user_name: str,
        settings: Settings,
    ):
        super().__init__(timeout=120.0)

        self.settings = settings

        # only the user who requested generation of the image
        # can have it replaced
        self.requesting_user_id = requesting_user_id
        self.requesting_user_name = requesting_user_name
        self.image_request = image_request
        self.photo_accepted = False

        #####################################################
        # "Try Again" button
        #
        btn_try_again = discord.ui.Button(
            label="Try Again",
            style=discord.ButtonStyle.blurple,
            row=1,
        )
        self.image_message = None

        async def on_try_again(interaction: discord.Interaction):
            result = await self.diy_interaction_check(interaction)
            if not result:
                # unauthorized user
                return

            # generate a new image
            regen_task = sd_client.generate_image(image_request, is_channel_nsfw)
            regen_file = await image_task_to_file(regen_task, image_request)
            await interaction.response.defer()

            await self.get_image_message().edit(attachments=[regen_file])

        btn_try_again.callback = on_try_again

        #####################################################
        # "Accept" button
        #
        btn_lock_in = discord.ui.Button(
            label="Accept",
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
            label="Delete",
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
        await interaction.response.send_message(
            f"Sorry, only {self.requesting_user_name} can press the buttons.",
            ephemeral=True,
        )
        return False

    def get_image_message_text(self) -> str:
        return self._get_message(MessageTemplate.IMAGE_CONFIRMATION)

    def get_detach_message(self) -> str:
        return self._get_message(MessageTemplate.IMAGE_DETACH)

    def _get_message(self, message_type: MessageTemplate) -> str:
        return self.settings.template_store.format(
            message_type,
            {
                TemplateToken.USER_NAME: self.requesting_user_name,
                TemplateToken.IMAGE_REQUEST: self.image_request,
            },
        )


async def send_image(
    stable_diffusion_client: StableDiffusionClient,
    raw_message: discord.Message,
    image_request: str,
    settings: Settings,
) -> None:
    is_channel_nsfw = False
    if isinstance(raw_message.channel, discord.TextChannel):
        is_channel_nsfw = raw_message.channel.is_nsfw()
    image_task = stable_diffusion_client.generate_image(
        image_request, is_channel_nsfw=is_channel_nsfw
    )
    file = await image_task_to_file(image_task, image_request)

    regen_view = StableDiffusionImageView(
        stable_diffusion_client,
        is_channel_nsfw,
        image_request=image_request,
        requesting_user_id=raw_message.author.id,
        requesting_user_name=raw_message.author.name,
        settings=settings,
    )

    image_message = await raw_message.channel.send(
        content=regen_view.get_image_message_text(),
        reference=raw_message,
        file=file,
        view=regen_view,
    )
    regen_view.image_message = image_message
