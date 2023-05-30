# -*- coding: utf-8 -*-
"""
Implementation of commands to join and leave voice channels.
"""
import typing

import discord

from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import persona


class AudioCommands:
    """
    Implementation of commands to join and leave voice channels.
    """

    voice_client: typing.Optional[discord.VoiceClient]

    def __init__(self, persona: persona.Persona):
        self.persona = persona
        self.voice_client = None

    def add_commands(self, tree):
        def is_bot_owner(interaction: discord.Interaction) -> bool:
            if interaction.guild is None:
                return False
            return interaction.user.id == interaction.guild.owner_id

        @discord.app_commands.command(
            name="join_voice",
            description=f"Have {self.persona.ai_name} join the voice "
            + "channel you are in right now.",
        )
        @discord.app_commands.check(is_bot_owner)
        async def join_voice(interaction: discord.Interaction):
            fancy_logger.get().debug(
                "/join_voice called by user '%s'", interaction.user.name
            )
            if interaction.user is None:
                await discord_utils.fail_interaction(interaction)

            if interaction.channel_id is None:
                await discord_utils.fail_interaction(interaction)
                return

            channel = await interaction.client.fetch_channel(interaction.channel_id)
            if channel is None:
                await discord_utils.fail_interaction(interaction)
                return

            if not isinstance(channel, discord.VoiceChannel):
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

            self.voice_client = await channel.connect()
            if self.voice_client is None:
                await discord_utils.fail_interaction(
                    interaction, "Failed to connect to voice channel"
                )
                return

            # here is what we need to send to Songbird to connect to a voice channel:

            # pub struct ConnectionInfo {
            #     /// ID of the voice channel being joined, if it is known.
            #     ///
            #     /// This is not needed to establish a connection, but can be useful
            #     /// for book-keeping.
            #     pub channel_id: Option<ChannelId>,
            #     /// URL of the voice websocket gateway server assigned to this call.
            #     pub endpoint: String,
            #     /// ID of the target voice channel's parent guild.
            #     ///
            #     /// Bots cannot connect to a guildless (i.e.,
            #     /// direct message) voice call.
            #     pub guild_id: GuildId,
            #     /// Unique string describing this session for validation/
            #     /// authentication purposes.
            #     pub session_id: String,
            #     /// Ephemeral secret used to validate the above session.
            #     pub token: String,
            #     /// UserID of this bot.
            #     pub user_id: UserId,
            # }

            # songbird_connection_info = {
            #     "channel_id": channel.id,
            #     "endpoint": self.voice_client.endpoint,
            #     "guild_id": channel.guild.id,
            #     "session_id": self.voice_client.session_id,
            #     "token": self.voice_client.token,
            #     "user_id": self.voice_client.user.id,
            # }

            await interaction.response.send_message(
                f"Listening to {channel.name}",
                ephemeral=True,
                silent=True,
                suppress_embeds=True,
            )

        @discord.app_commands.command(
            name="leave_voice",
            description=f"Have {self.persona.ai_name} leave the "
            + "voice channel it is in.",
        )
        @discord.app_commands.check(is_bot_owner)
        async def leave_voice(interaction: discord.Interaction):
            fancy_logger.get().debug(
                "/leave_voice called by user '%s'", interaction.user.name
            )
            if interaction.user is None:
                await discord_utils.fail_interaction(interaction)

            if interaction.channel_id is None:
                await discord_utils.fail_interaction(interaction)
                return

            channel = await interaction.client.fetch_channel(interaction.channel_id)
            if channel is None:
                await discord_utils.fail_interaction(interaction)
                return

            if not isinstance(channel, discord.VoiceChannel):
                await discord_utils.fail_interaction(
                    interaction, "You must be in a voice channel to use this command"
                )
                return

            # are we already connected to a voice channel?  If so, disconnect
            if self.voice_client is None:
                await discord_utils.fail_interaction(
                    interaction, "Not connected to a voice channel"
                )
                return

            fancy_logger.get().debug(
                "disconnecting from voice channel #%s", self.voice_client.channel
            )
            await self.voice_client.disconnect()
            self.voice_client = None

            await interaction.response.send_message(
                f"Listening to {channel.name}",
                ephemeral=True,
                silent=True,
                suppress_embeds=True,
            )

        fancy_logger.get().debug("Registering audio commands")
        tree.add_command(join_voice)
        tree.add_command(leave_voice)
