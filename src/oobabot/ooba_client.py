# Purpose: Streaming client for the Ooba API.
# Can provide the response by token or by sentence.
#

import json
import textwrap
import typing
import websockets

from oobabot.sentence_splitter import SentenceSplitter
from urllib.parse import urljoin


class OobaClient:
    # Purpose: Streaming client for the Ooba API.
    # Can provide the response by token or by sentence.

    END_OF_INPUT = ''

    def __init__(self, base_url: str, request_prefix: str):
        self.api_url = urljoin(base_url, self.STREAMING_URI_PATH)
        self.request_prefix = request_prefix
        self.total_response_tokens = 0

    DEFAULT_REQUEST_PARAMS = {
        'max_new_tokens': 250,
        'do_sample': True,
        'temperature': 1.3,
        'top_p': 0.1,
        'typical_p': 1,
        'repetition_penalty': 1.18,
        'top_k': 40,
        'min_length': 0,
        'no_repeat_ngram_size': 0,
        'num_beams': 1,
        'penalty_alpha': 0,
        'length_penalty': 1,
        'early_stopping': False,
        'seed': -1,
        'add_bos_token': True,
        'truncation_length': 2048,
        'ban_eos_token': False,
        'skip_special_tokens': True,
        'stopping_strings': [],
    }

    STREAMING_URI_PATH = './api/v1/stream'

    PROMPT_PREFIX = textwrap.dedent(
        """
        Below is an instruction that describes a task.  Write a response that
        appropriately completes the request.
        ### Instruction:
        """)

    PROMPT_SUFFIX = textwrap.dedent(
        """
        ### Response:
        """)

    async def try_connect(self) -> str:
        '''
        Attempt to connect to the oobabooga server.

        Returns:
            str, error message if unsuccessful, empty string on success
        '''
        try:
            async with websockets.connect(self.api_url) as _:
                return ''
        except Exception as e:
            return str(e)

    def set_request_prefix(self, prefix: str) -> None:
        self.request_prefix = prefix

    async def request_by_sentence(self, user_prompt: str, prefix2: str = '') \
            -> typing.AsyncIterator[str]:
        '''
        Yields each complete sentence of the response as it arrives.
        '''

        splitter = SentenceSplitter()
        async for new_token in self.request_by_token(user_prompt, prefix2):
            for sentence in splitter.by_sentence(new_token):
                yield sentence

    async def request_by_token(self, user_prompt: str, prefix2: str = '') \
            -> typing.AsyncIterator[str]:
        '''
        Yields each token of the response as it arrives.
        '''

        request = {
            'prompt': f'{self.request_prefix}{prefix2}{self.PROMPT_PREFIX}' +
                      f'{user_prompt}{self.PROMPT_SUFFIX}',
        }
        request.update(self.DEFAULT_REQUEST_PARAMS)

        print(f'Prompt: {request["prompt"]}')

        async with websockets.connect(self.api_url) as websocket:
            await websocket.send(json.dumps(request))

            while True:
                incoming_data = await websocket.recv()
                incoming_data = json.loads(incoming_data)

                if 'text_stream' == incoming_data['event']:
                    if (incoming_data['text']):
                        self.total_response_tokens += 1
                        yield incoming_data['text']

                elif 'stream_end' == incoming_data['event']:
                    # Make sure any unprinted text is flushed.
                    yield self.END_OF_INPUT
                    return
