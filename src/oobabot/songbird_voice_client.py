# -*- coding: utf-8 -*-
"""
A replacement voice client for discord.py, using the Songbird rust library.
"""

import asyncio
import socket
import threading
import typing

import discord
import discord.backoff
import discord.gateway
import discord.guild
import discord.opus
import discord.state
import discord.types
from discord.types import voice  # this is so pylint doesn't complain

from oobabot import fancy_logger

_log = fancy_logger.get()


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
    endpoint_ip: str
    voice_port: int
    ip: str
    port: int
    secret_key: typing.List[int]
    session_id: typing.Optional[str]
    ssrc: int

    # todo: what does Songbird support?  This will actually
    #       be sent to the server
    supported_modes: typing.Tuple[voice.SupportedModes, ...] = (
        "xsalsa20_poly1305_lite",
        "xsalsa20_poly1305_suffix",
        "xsalsa20_poly1305",
    )

    def __init__(
        self, client: discord.client.Client, channel: discord.abc.Connectable
    ) -> None:
        super().__init__(client, channel)
        state = client._connection
        self.token: str = discord.utils.MISSING
        self.server_id: int = discord.utils.MISSING
        self.socket = discord.utils.MISSING
        self.loop: asyncio.AbstractEventLoop = state.loop
        self._state: discord.state.ConnectionState = state
        self._connected: threading.Event = threading.Event()
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
        self._runner: asyncio.Task = discord.utils.MISSING
        self.encoder: discord.opus.Encoder = discord.utils.MISSING
        self._lite_nonce: int = 0
        self.websocket: discord.gateway.DiscordVoiceWebSocket = discord.utils.MISSING

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

        # This gets set later
        self.endpoint_ip = discord.utils.MISSING

        self.socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)

        if not self._handshaking:
            # If we're not handshaking then we need to terminate our previous
            # connection in the websocket
            await self.websocket.close(4000)
            return

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

    async def connect_websocket(self) -> discord.gateway.DiscordVoiceWebSocket:
        websocket = await discord.gateway.DiscordVoiceWebSocket.from_client(
            self  # type: ignore
        )
        self._connected.clear()
        while websocket.secret_key is None:
            await websocket.poll_event()
        self._connected.set()
        return websocket

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
                self.websocket = await self.connect_websocket()
                break
            except (discord.errors.ConnectionClosed, asyncio.TimeoutError):
                if reconnect:
                    _log.exception("Failed to connect to voice... Retrying...")
                    await asyncio.sleep(1 + i * 2.0)
                    await self.voice_disconnect()
                    continue
                raise

        if self._runner is discord.utils.MISSING:
            self._runner = self.client.loop.create_task(self.poll_voice_ws(reconnect))

    async def potential_reconnect(self) -> bool:
        # Attempt to stop the player thread from playing early
        self._connected.clear()
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
            self.websocket = await self.connect_websocket()
        except (discord.errors.ConnectionClosed, asyncio.TimeoutError):
            return False
        return True

    @property
    def latency(self) -> float:
        """:class:`float`: Latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds.

        This could be referred to as the Discord Voice WebSocket latency and is
        an analogue of user's voice latencies as seen in the Discord client.

        .. versionadded:: 1.4
        """
        return float("inf") if not self.websocket else self.websocket.latency

    @property
    def average_latency(self) -> float:
        """:class:`float`: Average of most recent 20 HEARTBEAT latencies in seconds.

        .. versionadded:: 1.4
        """
        return float("inf") if not self.websocket else self.websocket.average_latency

    async def poll_voice_ws(self, reconnect: bool) -> None:
        backoff = discord.backoff.ExponentialBackoff()
        while True:
            try:
                await self.websocket.poll_event()
            except (discord.errors.ConnectionClosed, asyncio.TimeoutError) as exc:
                if isinstance(exc, discord.errors.ConnectionClosed):
                    # The following close codes are undocumented so I will document
                    # them here.
                    # 1000 - normal closure (obviously)
                    # 4014 - voice channel has been deleted.
                    # 4015 - voice server has crashed
                    if exc.code in (1000, 4015):
                        _log.info(
                            "Disconnecting from voice normally, close code %d.",
                            exc.code,
                        )
                        await self.disconnect()
                        break
                    if exc.code == 4014:
                        _log.info(
                            "Disconnected from voice by force... "
                            + "potentially reconnecting."
                        )
                        successful = await self.potential_reconnect()
                        if not successful:
                            _log.info(
                                "Reconnect was unsuccessful, disconnecting "
                                + "from voice normally..."
                            )
                            await self.disconnect()
                            break
                        continue

                if not reconnect:
                    await self.disconnect()
                    raise

                retry = backoff.delay()
                _log.exception(
                    "Disconnected from voice... Reconnecting in %.2fs.", retry
                )
                self._connected.clear()
                await asyncio.sleep(retry)
                await self.voice_disconnect()
                try:
                    await self.connect(reconnect=True, timeout=self.timeout)
                except asyncio.TimeoutError:
                    # at this point we've retried 5 times... let's continue the loop.
                    _log.warning("Could not connect to voice... Retrying...")
                    continue

    async def disconnect(self, *, force: bool = False) -> None:
        """|coro|

        Disconnects this voice client from voice.
        """
        if not force and not self.is_connected():
            return

        # self.stop()
        self._connected.clear()

        try:
            if self.websocket:
                await self.websocket.close()

            await self.voice_disconnect()
        finally:
            self.cleanup()
            if self.socket:
                self.socket.close()

    async def move_to(self, channel: typing.Optional[discord.abc.Snowflake]) -> None:
        """|coro|

        Moves you to a different voice channel.

        Parameters
        -----------
        channel: Optional[:class:`abc.Snowflake`]
            The channel to move to. Must be a voice channel.
        """
        await self.channel.guild.change_voice_state(channel=channel)

    def is_connected(self) -> bool:
        """Indicates if the voice client is connected to voice."""
        return self._connected.is_set()
