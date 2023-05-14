# -*- coding: utf-8 -*-
# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

import typing

import aiohttp

from oobabot import fancy_logger
from oobabot import http_client
from oobabot import sentence_splitter


class OobaClient(http_client.SerializedHttpClient):
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    SERVICE_NAME = "Oobabooga"

    OOBABOOGA_STREAMING_URI_PATH: str = "/api/v1/stream"

    END_OF_INPUT = ""

    def __init__(
        self, base_url: str, default_oobabooga_params: typing.Dict[str, typing.Any]
    ):
        super().__init__(self.SERVICE_NAME, base_url)
        self.total_response_tokens = 0
        self.default_oobabooga_params = default_oobabooga_params

    async def _setup(self):
        async with self.get_session().ws_connect(self.OOBABOOGA_STREAMING_URI_PATH):
            return

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
        yield "".join([token async for token in self.request_by_token(prompt)])

    async def request_by_token(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives.
        """

        request: dict[
            str, typing.Union[bool, float, int, str, typing.List[typing.Any]]
        ] = {
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
                        fancy_logger.get().warning(
                            "Unexpected event: %s", incoming_data
                        )

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    fancy_logger.get().error(
                        "WebSocket connection closed with error: %s", msg
                    )
                    raise http_client.OobaHttpClientError(
                        f"WebSocket connection closed with error {msg}"
                    )
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    fancy_logger.get().info(
                        "WebSocket connection closed normally: %s", msg
                    )
                    return
