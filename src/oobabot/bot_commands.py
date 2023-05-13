import discord

from oobabot import fancy_logger
from oobabot import repetition_tracker
from oobabot import templates


class BotCommands:
    def __init__(
        self,
        ai_name: str,
        repetition_tracker: repetition_tracker.RepetitionTracker,
        template_store: templates.TemplateStore,
    ):
        self.ai_name = ai_name
        self.repetition_tracker = repetition_tracker
        self.template_store = template_store

    async def on_ready(self, client: discord.Client):
        """
        Register commands with Discord.
        """

        @discord.app_commands.command(
            name="lobotomize",
            description=f"Erase {self.ai_name}'s memory of any message "
            + "before now in this channel.",
        )
        @discord.app_commands.guild_only()
        async def lobotomize(interaction: discord.Interaction):
            async def fail():
                fancy_logger.get().warning(
                    "lobotomize called from an unexpected channel: "
                    + f"{interaction.channel_id}"
                )
                await interaction.response.send_message(
                    "failed to lobotomize", ephemeral=True, silent=True
                )

            if interaction.channel_id is None:
                await fail()
                return

            # find the current message in this channel
            # tell the Repetition Tracker to hide messages
            # before this message
            channel = interaction.client.get_channel(interaction.channel_id)
            if channel is None:
                await fail()
                return

            if not isinstance(channel, discord.abc.Messageable):
                await fail()
                return

            # find the current message in this channel
            # tell the Repetition Tracker to hide messages
            # before this message
            async for message in channel.history(limit=1):
                fancy_logger.get().info(
                    f"lobotomize called in #{channel.name}, "
                    + f"hiding messages before {message.id}"
                )
                self.repetition_tracker.hide_messages_before(
                    channel_id=channel.id,
                    message_id=message.id,
                )

            response = self.template_store.format(
                template_name=templates.Templates.COMMAND_LOBOTOMIZE_RESPONSE,
                format_args={
                    templates.TemplateToken.AI_NAME: self.ai_name,
                    templates.TemplateToken.USER_NAME: interaction.user.name,
                },
            )
            await interaction.response.send_message(
                response,
                silent=True,
            )

        fancy_logger.get().debug(
            "Registering commands, this may take a while sometimes..."
        )

        tree = discord.app_commands.CommandTree(client)
        tree.add_command(lobotomize)
        commands = await tree.sync(guild=None)
        for command in commands:
            fancy_logger.get().info(
                f"Registered command: {command.name}: {command.description}"
            )
        fancy_logger.get().debug(
            "If you try to run any command within the first ~5 minutes of "
            + "the bot starting, it will fail with the error: 'This command "
            + "is outdated,...'."
        )
