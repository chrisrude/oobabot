# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

from asyncio.exceptions import TimeoutError
from socket import gaierror
import typing

import aiohttp

from oobabot.fancy_logging import get_logger
from oobabot.sentence_splitter import SentenceSplitter


class OobaClientError(Exception):
    pass


class OobaClient:
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    END_OF_INPUT = ""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.total_response_tokens = 0
        self._session = None

    DEFAULT_REQUEST_PARAMS = {
        "max_new_tokens": 250,
        "do_sample": True,
        "temperature": 1.3,
        "top_p": 0.1,
        "typical_p": 1,
        "repetition_penalty": 1.18,
        "top_k": 40,
        "min_length": 0,
        "no_repeat_ngram_size": 0,
        "num_beams": 1,
        "penalty_alpha": 0,
        "length_penalty": 1,
        "early_stopping": False,
        "seed": -1,
        "add_bos_token": True,
        "truncation_length": 2048,
        "ban_eos_token": False,
        "skip_special_tokens": True,
        "stopping_strings": [],
    }

    STREAMING_URI_PATH = "/api/v1/stream"

    async def setup(self):
        """
        Attempt to connect to the oobabooga server.

        Returns:
            nothing, if the connection test was successful

        Raises:
            OobaClientError, if the connection fails
        """
        try:
            async with self.get_session().ws_connect(self.STREAMING_URI_PATH):
                return
        except (
            ConnectionRefusedError,
            gaierror,
            TimeoutError,
        ) as e:
            raise OobaClientError(f"Failed to connect to {self.base_url}: {e}", e)

    async def request_by_sentence(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each complete sentence of the response as it arrives.
        """

        splitter = SentenceSplitter()
        async for new_token in self.request_by_token(prompt):
            for sentence in splitter.by_sentence(new_token):
                yield sentence

    async def request_by_token(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives.
        """

        request = {
            "prompt": prompt,
        }
        request.update(self.DEFAULT_REQUEST_PARAMS)

        async with self.get_session().ws_connect(self.STREAMING_URI_PATH) as websocket:
            await websocket.send_json(request)

            async for msg in websocket:
                # we expect a series of text messages in JSON encoding,
                # like this:
                #
                # {"event": "text_stream", "message_num": 0, "text": ""}
                # {"event": "text_stream", "message_num": 1, "text": "Oh"}
                # {"event": "text_stream", "message_num": 2, "text": ","}
                # {"event": "text_stream", "message_num": 3, "text": " okay"}
                # {"event": "text_stream", "message_num": 4, "text": "."}
                # {"event": "stream_end", "message_num": 5}
                # get_logger().debug(f"Received message: {msg}")
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # bdata = typing.cast(bytes, msg.data)
                    # get_logger().debug(f"Received data: {bdata}")

                    incoming_data = msg.json()
                    if "text_stream" == incoming_data["event"]:
                        self.total_response_tokens += 1
                        yield incoming_data["text"]

                    elif "stream_end" == incoming_data["event"]:
                        # Make sure any unprinted text is flushed.
                        yield self.END_OF_INPUT
                        return

                    else:
                        get_logger().warning(f"Unexpected event: {incoming_data}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    get_logger().error(f"WebSocket connection closed with error: {msg}")
                    raise OobaClientError(
                        f"WebSocket connection closed with error {msg}"
                    )
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    get_logger().info(f"WebSocket connection closed normally: {msg}")
                    return

    def get_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise OobaClientError("Session not initialized")
        return self._session

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit_per_host=1)
        self._session = aiohttp.ClientSession(
            base_url=self.base_url, connector=connector
        )
        return self

    async def __aexit__(self, *_err):
        if self._session:
            await self._session.close()
        self._session = None
