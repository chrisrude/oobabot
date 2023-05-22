# -*- coding: utf-8 -*-
"""
Implementation of the bot's slash commands.
"""
import typing

import discord

from oobabot import decide_to_respond
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import persona
from oobabot import repetition_tracker
from oobabot import templates


class BotCommands:
    """
    Implementation of the bot's slash commands.
    """

    def __init__(
        self,
        decide_to_respond: decide_to_respond.DecideToRespond,
        repetition_tracker: repetition_tracker.RepetitionTracker,
        persona: persona.Persona,
        discord_settings: dict,
        template_store: templates.TemplateStore,
    ):
        self.decide_to_respond = decide_to_respond
        self.repetition_tracker = repetition_tracker
        self.persona = persona
        self.reply_in_thread = discord_settings["reply_in_thread"]
        self.template_store = template_store

    async def on_ready(self, client: discord.Client):
        """
        Register commands with Discord.
        """

        async def fail(
            interaction: discord.Interaction, reason: typing.Optional[str] = None
        ):
            msg = reason
            if msg is None:
                command = "command"
                if interaction.command is not None:
                    command = interaction.command.name
                fancy_logger.get().warning(
                    f"{command} called from an unexpected channel: "
                    + f"{interaction.channel_id}"
                )
                msg = f"{command} failed"

            await interaction.response.send_message(msg, ephemeral=True, silent=True)

        async def get_messageable(
            interaction: discord.Interaction,
        ) -> (
            typing.Optional[
                typing.Union[
                    discord.TextChannel,
                    discord.Thread,
                    discord.DMChannel,
                    discord.GroupChannel,
                ]
            ]
        ):
            if interaction.channel_id is not None:
                # find the current message in this channel
                # tell the Repetition Tracker to hide messages
                # before this message
                channel = await interaction.client.fetch_channel(interaction.channel_id)
                if channel is not None:
                    if isinstance(channel, discord.TextChannel):
                        return channel
                    if isinstance(channel, discord.Thread):
                        return channel
                    if isinstance(channel, discord.DMChannel):
                        return channel
                    if isinstance(channel, discord.GroupChannel):
                        return channel
            return None

        @discord.app_commands.command(
            name="say",
            description=f"Force {self.persona.ai_name} to say the provided message.",
        )
        @discord.app_commands.rename(text_to_send="message")
        @discord.app_commands.describe(
            text_to_send=f"Message to force {self.persona.ai_name} to say."
        )
        async def say(interaction: discord.Interaction, text_to_send: str):
            if interaction.channel_id is None:
                await fail(interaction)
                return

            # if reply_in_thread is True, we don't want our bot to
            # speak in guild channels, only threads and private messages
            if self.reply_in_thread:
                channel = await get_messageable(interaction)
                if channel is None or isinstance(channel, discord.TextChannel):
                    await fail(
                        interaction, f"{self.persona.ai_name} may only speak in threads"
                    )
                    return

            fancy_logger.get().debug(
                "/say called by user '%s' in channel #%d",
                interaction.user.name,
                interaction.channel_id,
            )
            # this will cause the bot to monitor the channel
            # and consider unsolicited responses
            self.decide_to_respond.log_mention(
                channel_id=interaction.channel_id,
                send_timestamp=interaction.created_at.timestamp(),
            )
            await interaction.response.send_message(
                text_to_send,
                suppress_embeds=True,
            )

        @discord.app_commands.command(
            name="lobotomize",
            description=f"Erase {self.persona.ai_name}'s memory of any message "
            + "before now in this channel.",
        )
        async def lobotomize(interaction: discord.Interaction):
            channel = await get_messageable(interaction)
            if channel is None:
                await fail(interaction)
                return

            # find the current message in this channel
            # tell the Repetition Tracker to hide messages
            # before this message
            async for message in channel.history(limit=1):
                channel_name = discord_utils.get_channel_name(channel)
                fancy_logger.get().info(
                    "/lobotomize called by user '%s' in #%s",
                    interaction.user.name,
                    channel_name,
                )
                self.repetition_tracker.hide_messages_before(
                    channel_id=channel.id,
                    message_id=message.id,
                )

            response = self.template_store.format(
                template_name=templates.Templates.COMMAND_LOBOTOMIZE_RESPONSE,
                format_args={
                    templates.TemplateToken.AI_NAME: self.persona.ai_name,
                    templates.TemplateToken.USER_NAME: interaction.user.name,
                },
            )
            await interaction.response.send_message(
                response,
                silent=True,
                suppress_embeds=True,
            )

        fancy_logger.get().debug(
            "Registering commands, sometimes this takes a while..."
        )

        tree = discord.app_commands.CommandTree(client)
        tree.add_command(lobotomize)
        tree.add_command(say)
        commands = await tree.sync(guild=None)
        for command in commands:
            fancy_logger.get().info(
                "Registered command: %s: %s", command.name, command.description
            )
