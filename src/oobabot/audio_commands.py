# -*- coding: utf-8 -*-
"""
Implementation of commands to join and leave voice channels.
"""
import typing

import discord

from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import persona
from oobabot import songbird_voice_client


class AudioCommands:
    """
    Implementation of commands to join and leave voice channels.
    """

    voice_client: typing.Optional[songbird_voice_client.SongbirdVoiceClient]

    def __init__(self, persona: persona.Persona):
        self.persona = persona
        self.voice_client = None

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

            voice_channel = None
            had_to_discover_guild = False
            if isinstance(interaction.user, discord.Member):
                # if invoked from a guild channel, join the voice channel
                # the invoker is in, within that guild
                if interaction.user.voice is not None:
                    voice_channel = interaction.user.voice.channel
            else:
                # if invoked from a private message, look at all guilds
                # which have both the bot and the invoking user as a member,
                # find find the first such guild where the user is in a voice
                # channel.
                had_to_discover_guild = True
                for guild in interaction.user.mutual_guilds:
                    # get member of guild
                    member = guild.get_member(interaction.user.id)
                    if member is None:
                        continue
                    if member.voice is None:
                        continue
                    if member.voice.channel is None:
                        continue
                    voice_channel = member.voice.channel

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

            self.voice_client = await voice_channel.connect(
                cls=songbird_voice_client.SongbirdVoiceClient,
            )
            if self.voice_client is None:
                await discord_utils.fail_interaction(
                    interaction, "Failed to connect to voice channel"
                )
                return

            if had_to_discover_guild:
                message = (
                    f"Joining voice channel in {voice_channel.guild.name}: "
                    + voice_channel.name
                )
            else:
                message = f"Joining voice channel: {voice_channel.name}"

            await interaction.response.send_message(
                message,
                ephemeral=True,
                silent=True,
                suppress_embeds=True,
            )

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
            if self.voice_client is None or not self.voice_client.is_connected():
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
