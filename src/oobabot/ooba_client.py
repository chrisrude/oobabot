# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

from asyncio.exceptions import TimeoutError
from socket import gaierror
import typing

import aiohttp

from oobabot import fancy_logger
from oobabot import http_client
from oobabot import sentence_splitter


class OobaClient(http_client.SerializedHttpClient):
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    OOBABOOGA_STREAMING_URI_PATH: str = "/api/v1/stream"

    END_OF_INPUT = ""

    def __init__(self, base_url: str, default_oobabooga_params: dict[str, typing.Any]):
        super().__init__(base_url)
        self.total_response_tokens = 0
        self.default_oobabooga_params = default_oobabooga_params

    async def setup(self):
        """
        Attempt to connect to the oobabooga server.

        Returns:
            nothing, if the connection test was successful

        Raises:
            OobaClientError, if the connection fails
        """
        try:
            async with self.get_session().ws_connect(self.OOBABOOGA_STREAMING_URI_PATH):
                return
        except (
            ConnectionRefusedError,
            gaierror,
            TimeoutError,
        ) as e:
            raise http_client.OobaClientError(
                f"Failed to connect to {self.base_url}: {e}", e
            )

    async def request_by_sentence(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each complete sentence of the response as it arrives.
        """

        splitter = sentence_splitter.SentenceSplitter()
        async for new_token in self.request_by_token(prompt):
            for sentence in splitter.by_sentence(new_token):
                yield sentence

    async def request_as_string(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields the entire response as a single string.
        """

        response = ""
        async for token in self.request_by_token(prompt):
            response += token
        yield response

    async def request_by_token(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives.
        """

        request: dict[str, bool | float | int | str | typing.List[typing.Any]] = {
            "prompt": prompt,
        }
        request.update(self.default_oobabooga_params)

        async with self.get_session().ws_connect(
            self.OOBABOOGA_STREAMING_URI_PATH
        ) as websocket:
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
                        fancy_logger.get().warning(f"Unexpected event: {incoming_data}")

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    fancy_logger.get().error(
                        f"WebSocket connection closed with error: {msg}"
                    )
                    raise http_client.OobaClientError(
                        f"WebSocket connection closed with error {msg}"
                    )
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    fancy_logger.get().info(
                        f"WebSocket connection closed normally: {msg}"
                    )
                    return
