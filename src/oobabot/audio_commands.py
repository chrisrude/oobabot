# -*- coding: utf-8 -*-
"""
Implementation of commands to join and leave voice channels.
"""
import typing

import discord

from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import persona
from oobabot import voice_client


class AudioCommands:
    """
    Implementation of commands to join and leave voice channels.
    """

    def __init__(self, persona: persona.Persona):
        voice_client.VoiceClient.wakewords = persona.wakewords

        self.persona = persona
        self.voice_client: typing.Optional[voice_client.VoiceClient] = None

    def _discover_voice_channel(
        self, interaction: discord.Interaction
    ) -> typing.Optional[discord.VoiceChannel]:
        if isinstance(interaction.user, discord.Member):
            # if invoked from a guild channel, join the voice channel
            # the invoker is in, within that guild
            if interaction.user.voice is not None:
                return interaction.user.voice.channel

        # if invoked from a private message, look at all guilds
        # which have both the bot and the invoking user as a member,
        # find find the first such guild where the user is in a voice
        # channel.
        for guild in interaction.user.mutual_guilds:
            # get member of guild
            member = guild.get_member(interaction.user.id)
            if member is None:
                continue
            if member.voice is None:
                continue
            if member.voice.channel is None:
                continue
            return (member.voice.channel, True)
        return None

    def add_commands(self, tree):
        @discord.app_commands.command(
            name="join_voice",
            description=f"Have {self.persona.ai_name} join the voice "
            + "channel you are in right now.",
        )
        async def join_voice(interaction: discord.Interaction):
            if interaction.user is None:
                await discord_utils.fail_interaction(interaction)

            fancy_logger.get().debug(
                "/join_voice called by user '%s'", interaction.user.name
            )

            voice_channel = self._discover_voice_channel(interaction)
            if voice_channel is None:
                await discord_utils.fail_interaction(
                    interaction, "You must be in a voice channel to use this command"
                )
                return

            # are we already connected to a voice channel?  If so, disconnect
            if self.voice_client is not None:
                fancy_logger.get().debug(
                    "disconnecting from voice channel #%s", self.voice_client.channel
                )
                await self.voice_client.disconnect()
                self.voice_client = None

            await interaction.response.defer(
                ephemeral=True,
                thinking=True,
            )

            try:
                self.voice_client = await voice_channel.connect(
                    cls=voice_client.VoiceClient,
                )
                message = f"Joined voice channel #{voice_channel.name}"
            except discord.DiscordException as err:
                fancy_logger.get().error(
                    "Failed to connect to voice channel #%d: %s", voice_channel.id, err
                )
                message = (
                    f"Failed to connect to voice channel #{voice_channel.name}: {err}"
                )
                return

            await interaction.followup.send(message)

        @discord.app_commands.command(
            name="leave_voice",
            description=f"Have {self.persona.ai_name} leave the "
            + "voice channel it is in.",
        )
        async def leave_voice(interaction: discord.Interaction):
            if interaction.user is None:
                await discord_utils.fail_interaction(interaction)

            fancy_logger.get().debug(
                "/leave_voice called by user: '%s'", interaction.user.name
            )

            # are we already connected to a voice channel?  If so, disconnect
            if self.voice_client is None:
                await discord_utils.fail_interaction(
                    interaction, "Not connected to a voice channel"
                )
                return

            channel = self.voice_client.channel

            fancy_logger.get().debug("leaving voice channel #%s", channel)

            await self.voice_client.disconnect()
            self.voice_client = None

            await interaction.response.send_message(
                f"Left voice channel: {channel.name}",
                ephemeral=True,
                silent=True,
            )

        fancy_logger.get().debug("Registering audio commands")
        tree.add_command(join_voice)
        tree.add_command(leave_voice)
