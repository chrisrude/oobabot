# Purpose: Discord client for Rosie
#

import datetime
import random
import time
import discord
import re
import textwrap
import typing

from oobabot.fancy_logging import get_logger
from oobabot.ooba_client import OobaClient
from oobabot.response_stats import AggregateResponseStats


# strip newlines and replace them with spaces, to make
# it harder for users to trick the UI into injecting
# other instructions, or data that appears to be from
# a different user
FORBIDDEN_CHARACTERS = r'[\n\r\t]'
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


def sanitize_string(raw_string: str) -> str:
    '''
    Filter out any characters that are not commonly on a
    US-English keyboard
    '''
    return FORBIDDEN_CHARACTERS_PATTERN.sub(' ', raw_string)


def sanitize_message(raw_message: discord.Message) -> dict[str, str]:
    author = sanitize_string(raw_message.author.name)

    raw_guild = raw_message.guild
    if raw_guild:
        raw_guild_name = raw_guild.name
    else:
        raw_guild_name = 'DM'

    return {
        'author': author,
        'message_text': sanitize_string(raw_message.content).strip(),
        'server': sanitize_string(raw_guild_name),
    }


class PromptGenerator:
    '''
    Purpose: generate a prompt_prefix for the AI to use, given
    the message history and persona.
    '''

    # this is set by the AI, and is the maximum length
    # it will understand before it starts to ignore
    # the rest of the prompt_prefix
    MAX_AI_TOKEN_SPACE = 2048

    # our structure will be:
    # <prompt_prefix (includes persona)>
    # <a bunch of history lines>
    # <ai response>
    #
    # figure out our budget for the persona and history
    # so that we can be sure to always have at least
    # RESERVED_FOR_AI_RESPONSE tokens for the AI to use

    HIST_SIZE = 10
    EST_CHARS_PER_HISTORY_LINE = 40
    REQUIRED_HISTORY_SIZE = HIST_SIZE * EST_CHARS_PER_HISTORY_LINE

    # this is the number of tokens we reserve for the AI
    # to respond with.
    RESERVED_FOR_AI_RESPONSE = 512

    def __init__(self, ai_name: str,
                 ai_persona: str):
        self.ai_name = ai_name
        self.ai_persona = ai_persona

        self.prompt_prefix = textwrap.dedent(f'''
        You are in a chat room with multiple participants.
        Below is a transcript of recent messages in the conversation.
        Write the next one to three messages that you would send in this
        conversation, from the point of view of the participant named
        "{self.ai_name}".
        ''')

        self.prompt_prefix += self.ai_persona + '\n'
        self.prompt_prefix += self.get_todays_topic() + '\n'

        self.prompt_prefix += textwrap.dedent(f'''
        All responses you write must be from the point of view of
        {self.ai_name}.
        ### Transcript:
        ''')

        available_for_history = self.MAX_AI_TOKEN_SPACE
        available_for_history -= len(self.prompt_prefix)
        available_for_history -= self.RESERVED_FOR_AI_RESPONSE
        available_for_history -= len(self.make_prompt_footer())

        if available_for_history < self.REQUIRED_HISTORY_SIZE:
            raise ValueError(
                'AI token space is too small for prompt_prefix and history. ' +
                'Please shorten your persona by ' +
                f'{self.REQUIRED_HISTORY_SIZE - available_for_history} ' +
                'characters.'
            )
        self.available_for_history = available_for_history

    def get_todays_topic(self, topics_file='topics.txt') -> str:
        now = datetime.datetime.now()
        timestr = now.strftime(
            'Today is %A, %B %-d.  The time is %-I:%M %p.')
        try:
            file = open(topics_file, 'r')
            get_logger().debug(f'using topics file {topics_file}')
        except FileNotFoundError:
            return timestr

        # read all lines and remove empty lines
        topics = [line.strip().lower()
                  for line in file.readlines() if line.strip()]
        random.seed(now.year + now.month + now.day)
        topic = random.choice(topics)
        get_logger().debug(f"Today's surprise topic is: {topic}")
        return timestr + f'  Today you would like to {topic}'

    def make_prompt_footer(self) -> str:
        return f'{self.ai_name} says:\n'

    async def generate(
            self,
            ai_user_id: int,
            message_history: typing.AsyncIterator[discord.Message]) \
            -> str:
        '''
        Generates a prompt_prefix for the AI to use based on the message.
        '''

        # put this at the very end to tell the UI what it
        # should complete.  But generate this now so we
        # know how long it is.
        prompt_prefix_footer = self.make_prompt_footer()

        # add on more history, but only if we have room
        # if we don't have room, we'll just truncate the history
        # by discarding the oldest messages first
        # this is s
        # it will understand before ignore
        #
        prompt_len_remaining = self.available_for_history

        # history_lines is newest first, so figure out
        # how many we can take, then append them in
        # reverse order
        history_lines = []

        async for raw_message in message_history:
            clean_message = sanitize_message(raw_message)

            author = clean_message["author"]
            if raw_message.author.id == ai_user_id:
                author = self.ai_name

            if not clean_message["message_text"]:
                continue

            line = f'{author} says:\n' + \
                f'{clean_message["message_text"]}\n\n'

            if len(line) > prompt_len_remaining:
                get_logger().warn(
                    'ran out of prompt space, discarding ' +
                    f'{self.HIST_SIZE - len(history_lines)} lines ' +
                    'of chat history'
                )
                break

            prompt_len_remaining -= len(line)
            history_lines.append(line)

        history_lines.reverse()

        prompt = self.prompt_prefix
        prompt += ''.join(history_lines)
        prompt += prompt_prefix_footer

        return prompt


class DiscordBot(discord.Client):

    # some non-zero chance of responding to a message,  even if
    # it wasn't addressed directly to the bot.  We'll only do this
    # if we have posted to the same channel within the last
    # RELEVANT_TIME_SECONDS
    RELEVANT_TIME_SECONDS = 120
    UNPROMPTED_RESPONSE_CHANCE = 0.2

    def __init__(self,
                 ooba_client: OobaClient,
                 ai_name: str,
                 ai_persona: str,
                 wakewords: list[str],
                 log_all_the_things: bool):
        self.ooba_client = ooba_client

        self.ai_name = ai_name
        self.ai_persona = ai_persona
        self.ai_user_id = -1
        self.wakewords = wakewords
        self.log_all_the_things = log_all_the_things

        # a list of timestamps in which we last posted to a channel
        self.channel_last_response_time = {}

        self.average_stats = AggregateResponseStats(ooba_client)
        self.prompt_prefix_generator = PromptGenerator(
            ai_name, ai_persona)

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(fr'\b{wakeword}\b', re.IGNORECASE)
            for wakeword in wakewords
        ]

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(intents=intents)

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum([len(guild.channels) for guild in guilds])

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = str(self.ai_user_id)
        else:
            user_id_str = '<unknown>'

        get_logger().info(
            f'Connected to discord as {self.user} (ID: {user_id_str})')
        get_logger().debug(
            f'monitoring DMs, plus {num_channels} channels across ' +
            f'{num_guilds} server(s)')

        get_logger().debug(f'AI name: {self.ai_name}')
        get_logger().debug(f'AI persona: {self.ai_persona}')

        str_wakewords = ", ".join(
            self.wakewords) if self.wakewords else "<none>"
        get_logger().debug(
            f'wakewords: {str_wakewords}'
        )

    def run(self, token: str) -> None:
        super().run(token)

    def should_reply_to_message(self, message: discord.Message) -> bool:
        # we do not want the bot to reply to itself
        if self.user and message.author.id == self.user.id:
            return False

        # reply to all private messages
        if discord.ChannelType.private == message.channel.type:
            return True

        # reply to all messages that include a wakeword
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message.content):
                return True

        # reply to all messages in which we're @-mentioned
        if self.user and self.user.id in [m.id for m in message.mentions]:
            return True

        # if we've posted recently in this channel, there are a few
        # other reasons we may respond.  But if we haven't, just
        # ignore the message.
        if message.channel.id not in self.channel_last_response_time:
            return False

        if message.created_at.timestamp() - \
                self.channel_last_response_time[message.channel.id] > \
                self.RELEVANT_TIME_SECONDS:
            return False

        # if the new message ends with a question mark, we'll respond
        if message.content.endswith('?'):
            return True

        # if the new message ends with an exclamation point, we'll respond
        if message.content.endswith('!'):
            return True

        # otherwise we'll respond randomly
        if random.random() < self.UNPROMPTED_RESPONSE_CHANCE:
            return True

        # ignore anything else
        return False

    def log_stats(self) -> None:
        self.average_stats.write_stat_summary_to_log()

    async def on_message(self, raw_message: discord.Message) -> None:
        if not self.should_reply_to_message(raw_message):
            return
        try:
            async with raw_message.channel.typing():
                await self.send_response(raw_message)
        except Exception as e:
            get_logger().error(
                f'Exception while sending response: {e}', exc_info=True)

    async def send_response(self, raw_message: discord.Message) -> None:
        clean_message = sanitize_message(raw_message)
        author = clean_message['author']
        server = clean_message['server']
        get_logger().debug(
            f'Request from {author} in server [{server}]')

        recent_messages = raw_message.channel.history(
            limit=PromptGenerator.HIST_SIZE)

        prompt_prefix = await self.prompt_prefix_generator.generate(
            self.ai_user_id, recent_messages)

        response_stats = self.average_stats.log_request_arrived(prompt_prefix)
        if self.log_all_the_things:
            print('prompt_prefix:\n----------\n')
            print(prompt_prefix)
            print('Response:\n----------\n')

        try:
            async for sentence in self.ooba_client.request_by_sentence(
                prompt_prefix
            ):
                if self.log_all_the_things:
                    print(sentence)

                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if f'{self.ai_name} says:' == sentence:
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, continuing'
                    )
                    continue

                # hack: abort response if it looks like the AI is
                # continuing the conversation as someone else
                if sentence.endswith(' says:'):
                    get_logger().warning(
                        f'Filtered out "{sentence}" from response, aborting'
                    )
                    break

                await raw_message.channel.send(sentence)
                response_stats.log_response_part()

        except Exception as err:
            get_logger().error(f'Error: {str(err)}')
            self.average_stats.log_response_failure()
            return

        # store the timestamp of this response in channel_last_response_time
        self.channel_last_response_time[raw_message.channel.id] = time.time()

        response_stats.write_to_log(f"Response to {author} done!  ")
        self.average_stats.log_response_success(response_stats)
