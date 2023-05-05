# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

from asyncio.exceptions import TimeoutError
import json
from socket import gaierror
import typing
from urllib.parse import urljoin

import websockets as ws  # weird, but needed to avoid long lines later
from websockets.exceptions import WebSocketException

from oobabot.sentence_splitter import SentenceSplitter


class OobaClientError(Exception):
    pass


class OobaClient:
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    END_OF_INPUT = ""

    def __init__(self, base_url: str):
        self.api_url = urljoin(base_url, self.STREAMING_URI_PATH)
        self.total_response_tokens = 0

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

    STREAMING_URI_PATH = "./api/v1/stream"

    async def try_connect(self):
        """
        Attempt to connect to the oobabooga server.

        Returns:
            nothing, if the connection test was successful

        Raises:
            OobaClientError, if the connection fails
        """
        try:
            async with ws.connect(self.api_url):  # type: ignore
                return
        except (
            ConnectionRefusedError,
            gaierror,
            TimeoutError,
            WebSocketException,
        ) as e:
            raise OobaClientError(f"Failed to connect to {self.api_url}: {e}", e)

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

        async with ws.connect(self.api_url) as websocket:  # type: ignore
            await websocket.send(json.dumps(request))

            while True:
                incoming_data = await websocket.recv()
                incoming_data = json.loads(incoming_data)

                if "text_stream" == incoming_data["event"]:
                    if incoming_data["text"]:
                        self.total_response_tokens += 1
                        yield incoming_data["text"]

                elif "stream_end" == incoming_data["event"]:
                    # Make sure any unprinted text is flushed.
                    yield self.END_OF_INPUT
                    return
