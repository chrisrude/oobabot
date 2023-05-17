# -*- coding: utf-8 -*-
# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

# Purpose: Split a string into sentences, based on a set of terminators.
#          This is a helper class for ooba_client.py.
import json
import time
import typing

import aiohttp
import pysbd

from oobabot import fancy_logger
from oobabot import http_client


class SentenceSplitter:
    """
    Purpose: Split an English string into sentences.
    """

    # anything that can't be in a real response
    END_OF_INPUT = ""

    def __init__(self):
        self.printed_idx = 0
        self.full_response = ""
        self.segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)

    def by_sentence(self, new_token: str) -> typing.Generator[str, None, None]:
        """
        Collects tokens into a single string, looks for ends of english
        sentences, then yields each sentence as soon as it's found.

        Parameters:
            new_token: str, the next token to add to the string

        Returns:
            Generator[str, None, None], yields each sentence

        Note:
        When there is no longer any input, the caller must pass
        SentenceSplitter.END_OF_INPUT to this function.  This
        function will then yield any remaining text, even if it
        doesn't look like a full sentence.
        """

        self.full_response += new_token
        unseen = self.full_response[self.printed_idx :]

        # if we've reached the end of input, yield it all,
        # even if we don't think it's a full sentence.
        if self.END_OF_INPUT == new_token:
            to_print = unseen.strip()
            if to_print:
                yield unseen
            self.printed_idx += len(unseen)
            return

        segments = self.segmenter.segment(unseen)

        # any remaining non-sentence things will be in the last element
        # of the list.  Don't print that yet.  At the very worst, we'll
        # print it when the END_OF_INPUT signal is reached.
        for sentence_w_char_spans in segments[:-1]:
            # sentence_w_char_spans is a class with the following fields:
            #  - sent: str, sentence text
            #  - start: start idx of 'sent', relative to original string
            #  - end: end idx of 'sent', relative to original string
            #
            # we want to remove the last '\n' if there is one.
            # we do want to include any other whitespace, though.

            to_print = sentence_w_char_spans.sent  # type: ignore
            if to_print.endswith("\n"):
                to_print = to_print[:-1]

            yield to_print

        # since we've printed all the previous segments,
        # the start of the last segment becomes the starting
        # point for the next roud.
        if len(segments) > 0:
            self.printed_idx += segments[-1].start  # type: ignore


class OobaClient(http_client.SerializedHttpClient):
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    SERVICE_NAME = "Oobabooga"

    OOBABOOGA_STREAMING_URI_PATH: str = "/api/v1/stream"

    def __init__(
        self,
        settings: typing.Dict[str, typing.Any],
    ):
        super().__init__(self.SERVICE_NAME, settings["base_url"])
        self.total_response_tokens = 0
        self.request_params = settings["request_params"]
        self.log_all_the_things = settings["log_all_the_things"]

    async def _setup(self):
        async with self.get_session().ws_connect(self.OOBABOOGA_STREAMING_URI_PATH):
            return

    async def request_by_sentence(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each complete sentence of the response as it arrives.
        """

        splitter = SentenceSplitter()
        async for new_token in self.request_by_token(prompt):
            for sentence in splitter.by_sentence(new_token):
                yield sentence

    async def request_as_string(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields the entire response as a single string.
        """
        yield "".join([token async for token in self.request_by_token(prompt)])

    async def request_as_grouped_tokens(
        self,
        prompt: str,
        interval: float = 0.2,
    ) -> typing.AsyncIterator[str]:
        """
        Yields the response as a series of tokens, grouped by time.
        """

        last_response = time.perf_counter()
        tokens = ""
        async for token in self.request_by_token(prompt):
            if token == SentenceSplitter.END_OF_INPUT:
                if tokens:
                    yield tokens
                break
            tokens += token
            now = time.perf_counter()
            if now < (last_response + interval):
                continue
            yield tokens
            tokens = ""
            last_response = time.perf_counter()

    async def request_by_token(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives.
        """

        request: dict[
            str, typing.Union[bool, float, int, str, typing.List[typing.Any]]
        ] = {
            "prompt": prompt,
        }
        request.update(self.request_params)

        async with self.get_session().ws_connect(
            self.OOBABOOGA_STREAMING_URI_PATH
        ) as websocket:
            await websocket.send_json(request)
            if self.log_all_the_things:
                print(f"Sent request:\n{json.dumps(request, indent=1)}")
                print(f"Prompt:\n{request['prompt']}")

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
                        text = incoming_data["text"]
                        if text != SentenceSplitter.END_OF_INPUT:
                            if self.log_all_the_things:
                                print(text, end="", flush=True)

                            yield text

                    elif "stream_end" == incoming_data["event"]:
                        # Make sure any unprinted text is flushed.
                        yield SentenceSplitter.END_OF_INPUT
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
