# -*- coding: utf-8 -*-
"""
A replacement voice client for discord.py, using the Songbird rust library.
"""

import asyncio
import typing

import discord
import discord.backoff
import discord.gateway
import discord.guild
import discord.opus
import discord.state
import discord.types
from discord.types import voice  # this is so pylint doesn't complain
import songbird

from oobabot import fancy_logger

_log = fancy_logger.get()


class SongbirdDriver:
    """
    Connects to a single Chat instance aka voice connection.
    """

    voice_token: str
    endpoint: str
    session_id: str
    guild_id: int
    channel_id: int
    user_id: int

    driver: typing.Optional[songbird.songbird.Driver]
    track_handle: typing.Optional[songbird.songbird.TrackHandle]

    def __init__(
        self,
        voice_token: str,
        endpoint: str,
        session_id: str,
        guild_id: int,
        channel_id: int,
        user_id: int,
    ) -> None:
        self.voice_token = voice_token
        self.endpoint = endpoint
        self.session_id = session_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id

        self.driver = None
        self.track_handle = None

    async def connect(self):
        self.driver = await songbird.songbird.Driver.create()
        # `server` is the server payload from the gateway.
        # `state` is the voice state payload from the gateway.
        await self.driver.connect(
            token=self.voice_token,
            endpoint=self.endpoint,
            session_id=self.session_id,
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            user_id=self.user_id,
        )

    async def disconnect(self):
        if self.driver is None:
            return
        await self.driver.stop()
        self.driver = None

    def is_connected(self):
        # todo(rude): more than this?
        return self.driver is not None

    async def get_crypto_mode(self) -> typing.Optional[str]:
        if self.driver is None:
            return None
        config = await self.driver.get_config()
        crypto_mode = config.crypto_mode

        # Normal => "xsalsa20_poly1305",
        # Suffix => "xsalsa20_poly1305_suffix",
        # Lite => "xsalsa20_poly1305_lite",
        match crypto_mode:
            case songbird.songbird.CryptoMode.Normal:
                return "xsalsa20_poly1305"
            case songbird.songbird.CryptoMode.Suffix:
                return "xsalsa20_poly1305_suffix"
            case songbird.songbird.CryptoMode.Lite:
                return "xsalsa20_poly1305_lite"

        fancy_logger.get().error("Unknown crypto mode: %s", crypto_mode)
        return None

    async def play(
        self,
        url: str = "https://www.youtube.com/watch?v=y6120QOlsfU",
    ):
        if self.driver is None:
            raise RuntimeError("Driver not connected")

        await self.stop()

        source = await songbird.songbird.Source.ytdl(url)

        self.track_handle = await self.driver.play_source(source)

    async def stop(self):
        if self.track_handle is None:
            return
        self.track_handle.stop()
        self.track_handle = None


class SongbirdVoiceClient(discord.VoiceProtocol):
    """Represents a Discord voice connection, implmemented by the
    Songbird rust library.

    You do not create these, you typically get them from
    e.g. :meth:`VoiceChannel.connect`, by passing in
    cls=songbird_voice_client.SongbirdVoiceClient.

    Attributes
    -----------
    session_id: :class:`typing.Optional[str]`
        The voice connection session ID.
    token: :class:`str`
        The voice connection token.
    endpoint: :class:`typing.optional[str]`
        The endpoint we are connecting to.
    channel: Union[:class:`VoiceChannel`, :class:`StageChannel`]
        The voice channel connected to.
    """

    channel: discord.channel.VocalGuildChannel
    endpoint: typing.Optional[str]
    session_id: typing.Optional[str]

    # todo: what order do we want?
    # todo: query this dynamically from songbird
    supported_modes: typing.Tuple[voice.SupportedModes, ...] = (
        "xsalsa20_poly1305",
        "xsalsa20_poly1305_suffix",
        "xsalsa20_poly1305_lite",
    )

    def __init__(
        self, client: discord.client.Client, channel: discord.abc.Connectable
    ) -> None:
        super().__init__(client, channel)
        state = client._connection
        self.token: str = discord.utils.MISSING
        self.server_id: int = discord.utils.MISSING
        self._state: discord.state.ConnectionState = state
        self.endpoint: typing.Optional[str] = None

        self._handshaking: bool = False
        self._potentially_reconnecting: bool = False
        self._voice_state_complete: asyncio.Event = asyncio.Event()
        self._voice_server_complete: asyncio.Event = asyncio.Event()

        self.mode: str = discord.utils.MISSING
        self._connections: int = 0
        self.sequence: int = 0
        self.timestamp: int = 0
        self.timeout: float = 0

        if self.channel.guild is None:
            raise ValueError("Channel does not have a guild.")

        self._songbird_driver = None

    @property
    def guild(self) -> discord.guild.Guild:
        """:class:`Guild`: The guild we're connected to."""
        return self.channel.guild

    @property
    def user(self) -> discord.user.ClientUser:
        """:class:`ClientUser`: The user connected to voice (i.e. ourselves)."""
        return self._state.user  # type: ignore

    def checked_add(self, attr: str, value: int, limit: int) -> None:
        val = getattr(self, attr)
        if val + value > limit:
            setattr(self, attr, 0)
        else:
            setattr(self, attr, val + value)

    # connection related

    async def on_voice_state_update(
        self,
        data: voice.GuildVoiceState,
        /,
    ) -> None:
        self.session_id = data["session_id"]
        channel_id = data["channel_id"]

        if not self._handshaking or self._potentially_reconnecting:
            # If we're done handshaking then we just need to update ourselves
            # If we're potentially reconnecting due to a 4014, then we need to
            # differentiate
            # a channel move and an actual force disconnect
            if channel_id is None:
                # We're being disconnected so cleanup
                await self.disconnect()
            else:
                channel = self.guild.get_channel(int(channel_id))
                if channel is None:
                    _log.warning(
                        "Channel ID %s not found in Guild ID %s",
                        channel_id,
                        self.guild.id,
                    )
                    return
                if not isinstance(channel, discord.channel.VocalGuildChannel):
                    _log.warning("Channel ID %s not a VocalGuildChannel.", channel_id)
                    return
                self.channel = channel
        else:
            self._voice_state_complete.set()

    async def on_voice_server_update(
        self,
        data: voice.VoiceServerUpdate,
        /,
    ) -> None:
        if self._voice_server_complete.is_set():
            _log.warning("Ignoring extraneous voice server update.")
            return

        self.token = data["token"]
        self.server_id = int(data["guild_id"])
        endpoint = data.get("endpoint")

        if endpoint is None or self.token is None:
            _log.warning(
                "Awaiting endpoint... This requires waiting. "
                "If timeout occurred considering raising the timeout and reconnecting."
            )
            return

        self.endpoint, _, _ = endpoint.rpartition(":")
        if self.endpoint.startswith("wss://"):
            # Just in case, strip it off since we're going to add it later
            self.endpoint = self.endpoint[6:]

        self._voice_server_complete.set()

    async def voice_connect(
        self, self_deaf: bool = False, self_mute: bool = False
    ) -> None:
        await self.channel.guild.change_voice_state(
            channel=self.channel, self_deaf=self_deaf, self_mute=self_mute
        )

    async def voice_disconnect(self) -> None:
        _log.info(
            "The voice handshake is being terminated for Channel ID %s (Guild ID %s)",
            self.channel.id,
            self.guild.id,
        )
        await self.channel.guild.change_voice_state(channel=None)

    def prepare_handshake(self) -> None:
        self._voice_state_complete.clear()
        self._voice_server_complete.clear()
        self._handshaking = True
        _log.info(
            "Starting voice handshake... (connection attempt %d)", self._connections + 1
        )
        self._connections += 1

    def finish_handshake(self) -> None:
        _log.info("Voice handshake complete. Endpoint found %s", self.endpoint)
        self._handshaking = False
        self._voice_server_complete.clear()
        self._voice_state_complete.clear()

    async def connect(
        self,
        *,
        reconnect: bool,
        timeout: float,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        _log.info("Connecting to voice...")
        self.timeout = timeout

        for i in range(5):
            self.prepare_handshake()

            # This has to be created before we start the flow.
            futures = [
                self._voice_state_complete.wait(),
                self._voice_server_complete.wait(),
            ]

            # Start the connection flow
            await self.voice_connect(self_deaf=self_deaf, self_mute=self_mute)

            try:
                await discord.utils.sane_wait_for(futures, timeout=timeout)
            except asyncio.TimeoutError:
                await self.disconnect(force=True)
                raise

            self.finish_handshake()

            try:
                if self._songbird_driver is not None:
                    raise RuntimeError("Songbird driver already exists")

                if self.token is None:
                    raise RuntimeError("Voice token is None")

                if self.endpoint is None:
                    raise RuntimeError("Voice endpoint is None")

                if self.session_id is None:
                    raise RuntimeError("Voice session_id is None")

                self._songbird_driver = SongbirdDriver(
                    voice_token=self.token,
                    endpoint=self.endpoint,
                    session_id=self.session_id,
                    guild_id=self.guild.id,
                    channel_id=self.channel.id,
                    user_id=self.user.id,
                )
                await self._songbird_driver.connect()
                break
            except (discord.errors.ConnectionClosed, asyncio.TimeoutError):
                if reconnect:
                    _log.exception("Failed to connect to voice... Retrying...")
                    await asyncio.sleep(1 + i * 2.0)
                    await self.voice_disconnect()
                    continue
                raise

    async def potential_reconnect(self) -> bool:
        # Attempt to stop the player thread from playing early
        self.prepare_handshake()
        self._potentially_reconnecting = True
        try:
            # We only care about VOICE_SERVER_UPDATE since VOICE_STATE_UPDATE
            # can come before we get disconnected
            await asyncio.wait_for(
                self._voice_server_complete.wait(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            self._potentially_reconnecting = False
            await self.disconnect(force=True)
            return False

        self.finish_handshake()
        self._potentially_reconnecting = False
        try:
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            # todo: connect to songbird here
            ...
            # self.websocket = await self.connect_websocket()
        except (discord.errors.ConnectionClosed, asyncio.TimeoutError):
            return False
        return True

    async def disconnect(self, *, force: bool = False) -> None:
        """|coro|

        Disconnects this voice client from voice.
        """
        if not force and not self.is_connected():
            return

        if self._songbird_driver is not None:
            await self._songbird_driver.stop()

        try:
            if self._songbird_driver is not None:
                await self._songbird_driver.disconnect()
                self._songbird_driver = None

            await self.voice_disconnect()
        finally:
            self.cleanup()

    async def move_to(self, channel: typing.Optional[discord.abc.Snowflake]) -> None:
        """|coro|

        Moves you to a different voice channel.

        Parameters
        -----------
        channel: Optional[:class:`abc.Snowflake`]
            The channel to move to. Must be a voice channel.
        """
        # todo: check songbird too?
        # todo: check songbird too?
        # todo: check songbird too?
        # todo: check songbird too?
        await self.channel.guild.change_voice_state(channel=channel)

    def is_connected(self) -> bool:
        """Indicates if the voice client is connected to voice."""
        if self._songbird_driver is None:
            return False
        return self._songbird_driver.is_connected()
