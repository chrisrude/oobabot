# -*- coding: utf-8 -*-
"""
Client for the Ooba API.
Can provide the response by token or by sentence.
"""
import abc
import json
import re
import time
import typing

import aiohttp
import pysbd
import pysbd.utils

from oobabot import fancy_logger
from oobabot import http_client


class MessageSplitter(abc.ABC):
    """
    Split a response into separate messages.
    """

    # anything that can't be in a real response
    END_OF_INPUT = ""

    def __init__(self):
        self.printed_idx = 0
        self.full_response = ""

    def next(self, new_token: str) -> typing.Generator[str, None, None]:
        """
        Collects tokens into a single string, splits into messages
        by the subclass's logic, then yields each message as soon
        as it's found.

        Parameters:
            new_token: str, the next token to add to the string

        Returns:
            Generator[str, None, None], yields each sentence

        Note:
        When there is no longer any input, the caller must pass
        MessageSplitter.END_OF_INPUT to this function.  This
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

        yield from self.partition(unseen)

    @abc.abstractmethod
    def partition(self, unseen: str) -> typing.Generator[str, None, None]:
        pass


class RegexSplitter(MessageSplitter):
    """
    Split a response into separate messages using a regex.
    """

    def __init__(self, regex: str):
        super().__init__()
        self.pattern = re.compile(regex)

    def partition(self, unseen: str) -> typing.Generator[str, None, None]:
        while True:
            match = self.pattern.match(unseen)
            if not match:
                break
            to_print = match.group(1)
            yield to_print
            self.printed_idx += match.end()
            unseen = self.full_response[self.printed_idx :]


class SentenceSplitter(MessageSplitter):
    """
    Split a response into separate messages using English
    sentence word breaks.
    """

    def __init__(self):
        super().__init__()
        self.segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)

    def partition(self, unseen: str) -> typing.Generator[str, None, None]:
        segments: typing.List[pysbd.utils.TextSpan] = self.segmenter.segment(
            unseen
        )  # type: ignore -- type is determined by char_span=True above

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
            # if to_print.endswith("\n"):
            #     to_print = to_print[:-1]

            yield to_print

        # since we've printed all the previous segments,
        # the start of the last segment becomes the starting
        # point for the next round.
        if len(segments) > 0:
            self.printed_idx += segments[-1].start  # type: ignore


class OobaClient(http_client.SerializedHttpClient):
    """
    Client for the Ooba API.  Can provide the response by token or by sentence.
    """


    SERVICE_NAME = "Oobabooga"

    OOBABOOGA_STREAMING_URI_PATH: str = "/api/v1/stream"
    OOBABOOGA_STOP_STREAM_URI_PATH: str = "/v1/internal/stop-generation"

    def __init__(
        self,
        settings: typing.Dict[str, typing.Any],
    ):
        super().__init__(self.SERVICE_NAME, settings["base_url"])
        self.total_response_tokens = 0
        self.message_regex = settings["message_regex"]
        self.request_params = settings["request_params"]
        self.log_all_the_things = settings["log_all_the_things"]
        self.base_blocking = settings["base_blocking"]
        self.use_openai = settings["use_openai"]
        self.openai_model = settings["openai_model"]
        self.api_key = settings["api_key"]
        self.openai_endpoint = settings["openai_endpoint"]
        if self.message_regex:
            self.fn_new_splitter = lambda: RegexSplitter(self.message_regex)
        else:
            self.fn_new_splitter = SentenceSplitter

    def on_ready(self):
        """
        Called when the client is ready to start.
        Used to log our configuration.
        """
        if self.message_regex:
            fancy_logger.get().debug(
                "Ooba Client: Splitting responses into messages " + "with: %s",
                self.message_regex,
            )
        else:
            fancy_logger.get().debug(
                "Ooba Client: Splitting responses into messages "
                + "by English sentence.",
            )

    async def _setup(self):
        if not self.use_openai:
            async with self._get_session().ws_connect(self.OOBABOOGA_STREAMING_URI_PATH):
                return
    async def __aenter__(self):
        if self.use_openai:
            # No need to create a session for SSE streaming
            return self


    def get_stopping_strings(self) -> typing.List[str]:
        """
        Returns a list of strings that indicate the end of a response.
        Taken from the yaml `stopping_strings` within our
        response_params.
        """
        return self.request_params.get("stopping_strings", [])

    async def request_by_message(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields individual messages from the response as it arrives.
        These can be split by a regex or by sentence.
        """
        splitter = self.fn_new_splitter()
        async for new_token in self.request_by_token(prompt):
            for sentence in splitter.next(new_token):
                # remove "### Assistant: " from strings
                if sentence.startswith("### Assistant: "):
                    sentence = sentence[len("### Assistant: ") :]
                yield sentence

    async def request_as_string(self, prompt: str) -> str:
        """
        Yields the entire response as a single string.
        """
        return "".join([token async for token in self.request_by_token(prompt)])

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

    async def stop(self):
        # New Ooba OpenAPI stopping logic
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_blocking}{self.OOBABOOGA_STOP_STREAM_URI_PATH}"
            headers = {"accept": "application/json"}

            async with session.post(url, data=json.dumps({}), headers=headers) as response:
               response_text = await response.text()
               print(response_text)
               return response_text
    async def request_by_token(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives.
        """
        if self.use_openai:
            # Directly iterate over the async generator
            async for token in self._request_by_token_openai(prompt):
                yield token
        else:
            # The Ooba API request is already an async generator
            async for token in self._request_by_token_ooba(prompt):
                yield token

    async def _request_by_token_openai(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields the response from the Cohere API by sentences.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

        request = {
            "model": self.openai_model,
            "prompt": prompt,
            "message": prompt, #Sending both of these because apparently cohere's api only takes message. neat. >:(
            "stream": True,

        }

        request.update(self.request_params)
        #print(request)

        async with aiohttp.ClientSession() as session:
            async with session.post(self.openai_endpoint, headers=headers, json=request, verify_ssl=False) as response:
                #print(response)
                if response.status != 200:
                    response_text = await response.text()
                    raise http_client.OobaHttpClientError(
                        f"Request failed with status {response.status}: {response_text}"
                    )
                if self.log_all_the_things:
                    try:
                        print(f"Sent request:\n{json.dumps(request, indent=1)}")
                        print(f"Prompt:\n{str(request['prompt'])}")
                    except UnicodeEncodeError:
                        print(
                            "Sent request:\n"
                            + f"{json.dumps(request, indent=1).encode('utf-8')}"
                        )
                        print(f"Prompt:\n{str(request['prompt']).encode('utf-8')}")
                async for line in response.content:
                    #print(line)
                    decoded_line = line.decode('utf-8').strip()
                    if decoded_line.startswith("data: "):
                        decoded_line = decoded_line[6:]  # Strip "data: "
                    if decoded_line:
                        try:
                            event_data = json.loads(decoded_line)
                            if "choices" in event_data:  # Handling the format with "choices"
                                for choice in event_data.get("choices", []):
                                    text = choice.get("text", "")
                                    if text:
                                        if self.log_all_the_things:
                                            try:
                                                print(text, end="", flush=True)
                                            except UnicodeEncodeError:
                                                print(text.encode("utf-8"), end="", flush=True)
                                        yield text
                                    if choice.get("finish_reason") is not None:
                                        break
                            else:  # Handling other formats
                                text = event_data.get("text", "")
                                is_finished = event_data.get("is_finished", False)
                                if text:
                                    if self.log_all_the_things:
                                        try:
                                            print(text, end="", flush=True)
                                        except UnicodeEncodeError:
                                            print(text.encode("utf-8"), end="", flush=True)
                                    yield text
                                if is_finished:
                                    break
                        except json.JSONDecodeError:
                            continue
                else:
                    response_text = await response.text()
                    print(f"Unexpected Content-Type encountered: {response.headers.get('Content-Type')}. Response: {response_text}")


                # Make sure to signal the end of input
                yield MessageSplitter.END_OF_INPUT



    async def _request_by_token_ooba(self, prompt: str) -> typing.AsyncIterator[str]:
        """
        Yields each token of the response as it arrives from the Ooba API.
        """           
        request: dict[
            str, typing.Union[bool, float, int, str, typing.List[typing.Any]]
        ] = {
            "prompt": prompt,
        }
        request.update(self.request_params)

        async with self._get_session().ws_connect(
            self.OOBABOOGA_STREAMING_URI_PATH
        ) as websocket:
            await websocket.send_json(request)
            if self.log_all_the_things:
                try:
                    print(f"Sent request:\n{json.dumps(request, indent=1)}")
                    print(f"Prompt:\n{str(request['prompt'])}")
                except UnicodeEncodeError:
                    print(
                        "Sent request:\n"
                        + f"{json.dumps(request, indent=1).encode('utf-8')}"
                    )
                    print(f"Prompt:\n{str(request['prompt']).encode('utf-8')}")

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
                if msg.type == aiohttp.WSMsgType.TEXT:
                    # bdata = typing.cast(bytes, msg.data)
                    # get_logger().debug(f"Received data: {bdata}")

                    incoming_data = msg.json()
                    if "text_stream" == incoming_data["event"]:
                        self.total_response_tokens += 1
                        text = incoming_data["text"]
                        if text != SentenceSplitter.END_OF_INPUT:
                            if self.log_all_the_things:
                                try:
                                    print(text, end="", flush=True)
                                except UnicodeEncodeError:
                                    print(text.encode("utf-8"), end="", flush=True)

                            yield text

                    elif "stream_end" == incoming_data["event"]:
                        # Make sure any unprinted text is flushed.
                        if self.log_all_the_things:
                            print("", flush=True)
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
