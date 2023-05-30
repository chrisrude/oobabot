# -*- coding: utf-8 -*-
"""
Implementation of commands to join and leave voice channels.
"""
import typing

import discord

from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import persona
<<<<<<< HEAD
from oobabot import songbird_voice_client
=======
>>>>>>> c889e67 (merge: safekeeping commit, may not work)


class AudioCommands:
    """
    Implementation of commands to join and leave voice channels.
    """

<<<<<<< HEAD
    voice_client: typing.Optional[songbird_voice_client.SongbirdVoiceClient]
=======
    voice_client: typing.Optional[discord.VoiceClient]
>>>>>>> c889e67 (merge: safekeeping commit, may not work)

    def __init__(self, persona: persona.Persona):
        self.persona = persona
        self.voice_client = None

    def add_commands(self, tree):
<<<<<<< HEAD
=======
        def is_bot_owner(interaction: discord.Interaction) -> bool:
            if interaction.guild is None:
                return False
            return interaction.user.id == interaction.guild.owner_id

>>>>>>> c889e67 (merge: safekeeping commit, may not work)
        @discord.app_commands.command(
            name="join_voice",
            description=f"Have {self.persona.ai_name} join the voice "
            + "channel you are in right now.",
        )
<<<<<<< HEAD
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
=======
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
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
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

<<<<<<< HEAD
            self.voice_client = await voice_channel.connect(
                # todo: have our own class which implements
                # VoiceProtocol but uses Songbird
                cls=songbird_voice_client.SongbirdVoiceClient,
            )
=======
            self.voice_client = await channel.connect()
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
            if self.voice_client is None:
                await discord_utils.fail_interaction(
                    interaction, "Failed to connect to voice channel"
                )
                return

<<<<<<< HEAD
            if had_to_discover_guild:
                message = (
                    f"Joining voice channel in {voice_channel.guild.name}: "
                    + voice_channel.name
                )
            else:
                message = f"Joining voice channel: {voice_channel.name}"

            await interaction.response.send_message(
                message,
=======
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
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
                ephemeral=True,
                silent=True,
                suppress_embeds=True,
            )

        @discord.app_commands.command(
            name="leave_voice",
            description=f"Have {self.persona.ai_name} leave the "
            + "voice channel it is in.",
        )
<<<<<<< HEAD
        async def leave_voice(interaction: discord.Interaction):
            if interaction.user is None:
                await discord_utils.fail_interaction(interaction)

            fancy_logger.get().debug(
                "/leave_voice called by user: '%s'", interaction.user.name
            )

            # are we already connected to a voice channel?  If so, disconnect
            if self.voice_client is None or not self.voice_client.is_connected():
=======
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
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
                await discord_utils.fail_interaction(
                    interaction, "Not connected to a voice channel"
                )
                return

<<<<<<< HEAD
            channel = self.voice_client.channel

            fancy_logger.get().debug("leaving voice channel #%s", channel)
=======
            fancy_logger.get().debug(
                "disconnecting from voice channel #%s", self.voice_client.channel
            )
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
            await self.voice_client.disconnect()
            self.voice_client = None

            await interaction.response.send_message(
<<<<<<< HEAD
                f"Left voice channel: {channel.name}",
                ephemeral=True,
                silent=True,
=======
                f"Listening to {channel.name}",
                ephemeral=True,
                silent=True,
                suppress_embeds=True,
>>>>>>> c889e67 (merge: safekeeping commit, may not work)
            )

        fancy_logger.get().debug("Registering audio commands")
        tree.add_command(join_voice)
        tree.add_command(leave_voice)
