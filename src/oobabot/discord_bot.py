# -*- coding: utf-8 -*-
"""
Main bot class.  Contains Discord-specific code that can't
be easily extracted into a cross-platform library.
"""

import asyncio
import typing
import discord
import base64
import io
import re
import requests
from PIL import Image

from oobabot import bot_commands
from oobabot import decide_to_respond
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import image_generator
from oobabot import ooba_client
from oobabot import persona
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import response_stats
from oobabot import types
from oobabot import vision


class DiscordBot(discord.Client):
    """
    Main bot class.  Connects to Discord, monitors for messages,
    and dispatches responses.
    """

    def __init__(
        self,
        bot_commands: bot_commands.BotCommands,
        decide_to_respond: decide_to_respond.DecideToRespond,
        discord_settings: dict,
        vision_api_settings: typing.Dict[str, typing.Any],
        image_generator: typing.Optional[image_generator.ImageGenerator],
        ooba_client: ooba_client.OobaClient,
        persona: persona.Persona,
        prompt_generator: prompt_generator.PromptGenerator,
        repetition_tracker: repetition_tracker.RepetitionTracker,
        response_stats: response_stats.AggregateResponseStats,
    ):
        self.bot_commands = bot_commands
        self.decide_to_respond = decide_to_respond
        self.image_generator = image_generator
        self.ooba_client = ooba_client
        self.persona = persona
        self.prompt_generator = prompt_generator
        self.repetition_tracker = repetition_tracker
        self.response_stats = response_stats

        self.ai_user_id = -1
        self.url_extractor = re.compile(r"(https?://\S+)")

        self.dont_split_responses = discord_settings["dont_split_responses"]
        self.ignore_dms = discord_settings["ignore_dms"]
        self.reply_in_thread = discord_settings["reply_in_thread"]
        self.stop_markers = discord_settings["stop_markers"]
        self.stream_responses = discord_settings["stream_responses"]
        self.stream_responses_speed_limit = discord_settings["stream_responses_speed_limit"]
        self.vision_api_url = vision_api_settings["vision_api_url"]
        self.vision_api_key = vision_api_settings["vision_api_key"]
        self.vision_model = vision_api_settings["model"]
        self.vision_max_tokens = vision_api_settings["max_tokens"]
        self.vision_max_image_size = vision_api_settings["max_image_size"]
        self.vision_fetch_urls = vision_api_settings["fetch_urls"]
        self.use_vision = vision_api_settings["use_vision"]

        self.prompt_prefix = discord_settings["prompt_prefix"]
        self.prompt_suffix = discord_settings["prompt_suffix"]
        self.prompt_finder = re.compile(r"\[.+?\]+:")

        # add stopping_strings to stop_markers
        self.stop_markers.extend(self.ooba_client.get_stopping_strings())

        super().__init__(intents=discord_utils.get_intents())

    async def on_ready(self) -> None:
        guilds = self.guilds
        num_guilds = len(guilds)
        num_channels = sum(len(guild.channels) for guild in guilds)

        if self.user:
            self.ai_user_id = self.user.id
            user_id_str = self.user.name
        else:
            user_id_str = "<unknown>"

        fancy_logger.get().info(
            "Connected to discord as %s (ID: %d)", user_id_str, self.ai_user_id
        )
        fancy_logger.get().debug(
            "monitoring %d channels across %d server(s)", num_channels, num_guilds
        )
        if self.ignore_dms:
            fancy_logger.get().debug("Ignoring DMs")
        else:
            fancy_logger.get().debug("listening to DMs")

        if self.stream_responses:
            fancy_logger.get().debug(
                "Response Grouping: streamed live into a single message"
            )
        elif self.dont_split_responses:
            fancy_logger.get().debug("Response Grouping: returned as single messages")
        else:
            fancy_logger.get().debug(
                "Response Grouping: split into messages by sentence"
            )

        fancy_logger.get().debug("AI name: %s", self.persona.ai_name)
        fancy_logger.get().debug("AI persona: %s", self.persona.persona)

        fancy_logger.get().debug(
            "History: %d lines ", self.prompt_generator.history_lines
        )

        fancy_logger.get().debug(
            "Stop markers: %s", ", ".join(self.stop_markers) or "<none>"
        )

        # log unsolicited_channel_cap
        cap = self.decide_to_respond.get_unsolicited_channel_cap()
        cap = str(cap) if cap > 0 else "<unlimited>"
        fancy_logger.get().debug(
            "Unsolicited channel cap: %s",
            cap,
        )

        str_wakewords = (
            ", ".join(self.persona.wakewords) if self.persona.wakewords else "<none>"
        )
        fancy_logger.get().debug("Wakewords: %s", str_wakewords)

        self.ooba_client.on_ready()

        if self.image_generator is None:
            fancy_logger.get().debug("Stable Diffusion: disabled")
        else:
            self.image_generator.on_ready()

        # we do this at the very end because when you restart
        # the bot, it can take a while for the commands to
        # register
        try:
            # register the commands
            await self.bot_commands.on_ready(self)
        except discord.DiscordException as err:
            fancy_logger.get().warning(
                "Failed to register commands: %s (continuing without commands)", err
            )

        # show a warning if the bot is connected to zero guilds,
        # with a helpful link on how to fix it
        if num_guilds == 0:
            fancy_logger.get().warning(
                "The bot is not connected to any servers.  "
                + "Please add the bot to a server here:",
            )
            fancy_logger.get().warning(
                discord_utils.generate_invite_url(self.ai_user_id)
            )

    async def on_message(self, raw_message: discord.Message) -> None:
         """
         Called when a message is received from Discord.

         This method is called for every message that the bot can see.
         It decides whether to respond to the message, and if so,
         calls _handle_response() to generate a response.

         :param raw_message: The raw message from Discord.
         """


         # If the message is not a command, proceed with regular message handling
         try:
            message = discord_utils.discord_message_to_generic_message(raw_message)
            should_respond, is_summon = self.decide_to_respond.should_reply_to_message(
                self.ai_user_id, message
            )
            if not should_respond:
                return

            image_descriptions = []
            if self.use_vision:
                if should_respond:
                    if self.vision_fetch_urls:
                        urls = self.url_extractor.findall(raw_message.content)
                        if urls:
                            for url in urls:
                                r = requests.head(url)
                                if r.headers["content-type"].startswith("image/"):
                                    try:
                                        description = await vision.get_image_description(url, vision_api_url=self.vision_api_url, vision_api_key=self.vision_api_key, model=self.vision_model, max_tokens=self.vision_max_tokens)
                                        if description:
                                            image_descriptions.append(description)
                                    except Exception as e:
                                        fancy_logger.get().error("Error processing image: %s", e, exc_info=True)
                    if raw_message.attachments:
                        for attachment in raw_message.attachments:
                            if attachment.content_type and attachment.content_type.startswith("image/"):
                                try:
                                    # Create a BytesIO buffer
                                    buffer = io.BytesIO()
                                    # Save the attachment to the buffer
                                    await attachment.save(buffer)
                                    buffer.seek(0)  # Move to the start of the buffer
                                    # Resample the image to something our image recognition model can handle, if necessary
                                    image = Image.open(buffer)
                                    buffer.flush()
                                    if image.width > self.vision_max_image_size or image.height > self.vision_max_image_size:
                                        # Resize image using its largest side as the baseline, preserving aspect ratio
                                        if image.width > image.height:
                                            height = int(image.height * (self.vision_max_image_size / image.width))
                                            image = image.resize((self.vision_max_image_size, height), Image.LANCZOS)
                                        else:
                                            width = int(image.width * (self.vision_max_image_size / image.height))
                                            image = image.resize((width, self.vision_max_image_size), Image.LANCZOS)
                                    image.save(buffer, "PNG", optimize=True) # dump image data in PNG format
                                    buffer.seek(0)
                                    # Encode the image in base64
                                    #image_base64 = "data:image/png;base64," # this doesn't work with LocalAI for some reason, someone save me
                                    image_base64 = "data:image/jpeg;base64," # we lie to the API since it only accepts JPEG, but can decode PNG data anyway
                                    image_base64 += base64.b64encode(buffer.read()).decode("utf-8")
                                    # Now pass the base64-encoded image to the vision function
                                    description = await vision.get_image_description(image_base64, vision_api_url=self.vision_api_url, vision_api_key=self.vision_api_key, model=self.vision_model, max_tokens=self.vision_max_tokens)
                                    if description:
                                        image_descriptions.append(description)
                                except Exception as e:
                                    fancy_logger.get().error("Error processing image: %s", e, exc_info=True)

            is_summon_in_public_channel = is_summon and isinstance(
                message,
                types.ChannelMessage,
            )

            async with raw_message.channel.typing():
                await self._handle_response(
                    message, raw_message, is_summon_in_public_channel, image_descriptions
                )
         except discord.DiscordException as err:
            fancy_logger.get().error(
                "Exception while processing message: %s", err, exc_info=True
            )

    async def _handle_response(
      self,
      message: types.GenericMessage,
      raw_message: discord.Message,
      is_summon_in_public_channel: bool,
      image_descriptions: typing.List[str],
      ) -> None:
      """
      Called when we've decided to respond to a message.

      It decides if we're sending a text response, an image response,
      or both, and then sends the response(s).
      """
      image_prompt = None
      if self.image_generator is not None:
            # are we creating an image?
            image_prompt = self.image_generator.maybe_get_image_prompt(raw_message)

      result = await self._send_text_response(
            message=message,
            raw_message=raw_message,
            image_requested=image_prompt is not None,
            is_summon_in_public_channel=is_summon_in_public_channel,
            image_descriptions=image_descriptions
      )
      if result is None:
            # we failed to create a thread that the user could
            # read our response in, so we're done here.  Abort!
            return
      message_task, response_channel = result

      # log the mention, now that we know the channel we
      # want to monitor later to continue to conversation
      if isinstance(response_channel, (discord.Thread, discord.abc.GuildChannel)):
            if is_summon_in_public_channel:
               self.decide_to_respond.log_mention(
                  response_channel.id,
                  message.send_timestamp,
               )

      image_task = None
      if self.image_generator is not None and image_prompt is not None:
            image_task = self.image_generator.generate_image(
               image_prompt,
               raw_message,
               response_channel=response_channel,
            )

      response_tasks = [
            task for task in [message_task, image_task] if task is not None
      ]

      # Use asyncio.gather instead of asyncio.wait to properly handle exceptions
      if response_tasks:
            done, pending = await asyncio.wait(response_tasks, return_when=asyncio.ALL_COMPLETED)
            # Check for exceptions in the tasks that have completed
            for task in done:
               if task.exception():
                  fancy_logger.get().error(
                        f"Exception while running {task.get_coro()} "
                        + f"response: {task.exception()}",
                        stack_info=True,
                  )
                  raise task.exception()

    async def _send_text_response(
        self,
        message: types.GenericMessage,
        raw_message: discord.Message,
        image_requested: bool,
        is_summon_in_public_channel: bool,
        image_descriptions: typing.List[str],
    ) -> typing.Optional[typing.Tuple[asyncio.Task, discord.abc.Messageable]]:
        """
        Send a text response to a message.

        This method determines what channel or thread to post the message
        in, creating a thread if necessary.  It then posts the message
        by calling _send_text_response_to_channel().

        Returns a tuple of the task that was created to send the message,
        and the channel that the message was sent to.

        If no message was sent, the task and channel will be None.
        """
        response_channel = raw_message.channel
        if (
            self.reply_in_thread
            and isinstance(raw_message.channel, discord.TextChannel)
            and isinstance(raw_message.author, discord.Member)
        ):
            # we want to create a response thread, if possible
            # but we have to see if the user has permission to do so
            # if the user can't we wont respond at all.
            perms = raw_message.channel.permissions_for(raw_message.author)
            if perms.create_public_threads:
                response_channel = await raw_message.create_thread(
                    name=f"{self.persona.ai_name}, replying to "
                    + f"{raw_message.author.display_name}",
                )
                fancy_logger.get().debug(
                    f"Created response thread {response_channel.name} "
                    + f"({response_channel.id}) "
                    + f"in {raw_message.channel.name}"
                )
            else:
                # This user can't create threads, so we won't respond.
                # The reason we don't respond in the channel is that
                # it can create confusion later if a second user who
                # DOES have thread-create permission replies to that
                # message.  We'd end up creating a thread for that
                # second user's response, and again for a third user,
                # etc.
                fancy_logger.get().debug("User can't create threads, not responding.")
                return None

        response_coro = self._send_text_response_in_channel(
            message=message,
            raw_message=raw_message,
            image_requested=image_requested,
            is_summon_in_public_channel=is_summon_in_public_channel,
            response_channel=response_channel,
            response_channel_id=response_channel.id,
            image_descriptions=image_descriptions,
        )
        response_task = asyncio.create_task(response_coro)
        return (response_task, response_channel)

    async def _send_text_response_in_channel(
        self,
        message: types.GenericMessage,
        raw_message: discord.Message,
        image_requested: bool,
        is_summon_in_public_channel: bool,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
        image_descriptions: typing.List[str],
    ) -> None:
        """
        Getting closer now!  This method is what actually gathers message
        history, queries the AI for a text response, breaks the response
        into individual messages, and then and then calls
        __send_response_message() to send each message.
        """
        fancy_logger.get().debug(
            "Request from %s in %s", message.author_name, message.channel_name
        )
    
        repeated_id = self.repetition_tracker.get_throttle_message_id(
            response_channel_id
        )
    
        # determine if we're responding to a specific message that
        # summoned us.  If so, find out what message ID that was, so
        # that we can ignore all messages sent after it (as not to
        # confuse the AI about what to reply to)
        reference = None
        ignore_all_until_message_id = None
        if is_summon_in_public_channel:
            # we can't use the message reference if we're starting a new thread
            if message.channel_id == response_channel_id:
                reference = raw_message.to_reference()
            ignore_all_until_message_id = raw_message.id
    
        recent_messages = await self._recent_messages_following_thread(
            channel=response_channel,
            num_history_lines=self.prompt_generator.history_lines,
            stop_before_message_id=repeated_id,
            ignore_all_until_message_id=ignore_all_until_message_id,
            image_descriptions=image_descriptions,
        )

        # Convert the recent messages into a list to modify it
        recent_messages_list = [msg async for msg in recent_messages]

        # If there are image descriptions, create a new message with the user's name and prepend it
        if image_descriptions:
            description_text = ' '.join(f'[{message.author_name} posted an image and your image recognition system describes it to you: {desc}]' for desc in image_descriptions)
            for msg in recent_messages_list:
                if msg.author_id == message.author_id:
                    # Append the image descriptions to the body text of the user's last message
                    msg.body_text += "\n" + description_text
                    break

        # Convert the list back into an asynchronous iterator
        async def list_to_async_iterator(lst):
            for item in lst:
                yield item
        recent_messages_async_iter = list_to_async_iterator(recent_messages_list)

        # Generate the prompt prefix using the modified recent messages list
        if isinstance(response_channel, discord.abc.GuildChannel):
            guild_name = response_channel.guild.name
        elif isinstance(response_channel, discord.GroupChannel):
            guild_name = response_channel
        else:
            guild_name = "Direct Message"
        prompt_prefix = await self.prompt_generator.generate(
            message_history=recent_messages_async_iter,
            image_requested=image_requested,
            guild_name=str(guild_name),
            response_channel=str(response_channel),
        )
        
    
        this_response_stat = self.response_stats.log_request_arrived(prompt_prefix)
        # restrict the @mentions the AI is allowed to use in its response.
        # this is to prevent another user from being able to trick the AI
        # into @-pinging a large group and annoying them.
        # Only the author of the original message may be @-pinged.
        allowed_mentions = discord.AllowedMentions(
            everyone=True,
            users=True,
            roles=True,
        )

        # will be set to true when we abort the response because:
        #  it was empty
        #  it repeated a previous response and we're throttling it
        aborted_by_us = False
        sent_message_count = 0
        try:
            if self.stream_responses:
                generator = self.ooba_client.request_as_grouped_tokens(
                    prompt_prefix, interval=self.stream_responses_speed_limit
                )
                last_sent_message = await self._render_streaming_response(
                    generator,
                    this_response_stat,
                    response_channel,
                    response_channel_id,
                    allowed_mentions,
                    reference,
                )
                if last_sent_message is not None:
                    sent_message_count = 1
            else:
                if self.dont_split_responses:
                    response = await self.ooba_client.request_as_string(prompt_prefix)
                    (
                        last_sent_message,
                        aborted_by_us,
                    ) = await self._send_response_message(
                        response,
                        this_response_stat,
                        response_channel,
                        response_channel_id,
                        allowed_mentions,
                        reference,
                    )
                    if last_sent_message is not None:
                        sent_message_count = 1
                else:
                    sent_message_count = 0
                    last_sent_message = None
                    async for sentence in self.ooba_client.request_by_message(
                        prompt_prefix
                    ):
                        (
                            sent_message,
                            abort_response,
                        ) = await self._send_response_message(
                            sentence,
                            this_response_stat,
                            response_channel,
                            response_channel_id,
                            allowed_mentions=allowed_mentions,
                            reference=reference,
                        )
                        if sent_message is not None:
                            last_sent_message = sent_message
                            sent_message_count += 1
                            # only use the reference for the first
                            # message in a multi-message chain
                            reference = None
                        if abort_response:
                            aborted_by_us = True
                            break

        except discord.DiscordException as err:
            fancy_logger.get().error("Error: %s", err, exc_info=True)
            self.response_stats.log_response_failure()
            return

        if 0 == sent_message_count:
            if aborted_by_us:
                fancy_logger.get().warning(
                    "No response sent.  The AI has generated a message that we have "
                    + "chosen not to send, probably because it was empty or repeated."
                )
            else:
                fancy_logger.get().warning(
                    "An empty response was received from Oobabooga.  Please check that "
                    + "the AI is running properly on the Oobabooga server at %s.",
                    self.ooba_client.base_url,
                )
            self.response_stats.log_response_failure()
            return

        this_response_stat.write_to_log(f"Response to {message.author_name} done!  ")
        self.response_stats.log_response_success(this_response_stat)

    async def _send_response_message(
        self,
        response: str,
        this_response_stat: response_stats.ResponseStats,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
        allowed_mentions: discord.AllowedMentions,
        reference: typing.Optional[discord.MessageReference],
    ) -> typing.Tuple[typing.Optional[discord.Message], bool]:
        """
        Given a string that represents an individual response message,
        post it in the given channel.

        It also looks to see if a message contains a termination string,
        and if so it will return False to indicate that we should stop
        the response.

        Also does some bookkeeping to make sure we don't repeat ourselves,
        and to track how many messages we've sent.

        Returns a tuple with:
        - the sent discord message, if any
        - a boolean indicating if we need to abort the response entirely
        """
        (sentence, abort_response) = self._filter_immersion_breaking_lines(response)
        if abort_response:
            return (None, True)
        if not sentence:
            # we can't send an empty message
            return (None, False)

        response_message = await response_channel.send(
            sentence,
            allowed_mentions=allowed_mentions,
            suppress_embeds=True,
            reference=reference,  # type: ignore
        )
        self.repetition_tracker.log_message(
            response_channel_id,
            discord_utils.discord_message_to_generic_message(response_message),
        )

        this_response_stat.log_response_part()
        return (response_message, False)

    async def _render_streaming_response(
        self,
        response_iterator: typing.AsyncIterator[str],
        this_response_stat: response_stats.ResponseStats,
        response_channel: discord.abc.Messageable,
        response_channel_id: int,
        allowed_mentions: discord.AllowedMentions,
        reference: typing.Optional[discord.MessageReference],
    ) -> typing.Optional[discord.Message]:
        response = ""
        last_message = None
        async for token in response_iterator:
            if "" == token:
                continue

            response += token
            (response, abort_response) = self._filter_immersion_breaking_lines(response)

            # if we are aborting a response, we want to at least post
            # the valid parts, so don't abort quite yet.

            if last_message is None:
                if not response:
                    # we don't want to send an empty message
                    continue

                # when we send the first message, we don't want to send a notification,
                # as it will only include the first token of the response.  This will
                # not be very useful to anyone.
                last_message = await response_channel.send(
                    response,
                    allowed_mentions=allowed_mentions,
                    silent=True,
                    suppress_embeds=True,
                    reference=reference,  # type: ignore
                )
            else:
                await last_message.edit(
                    content=response,
                    allowed_mentions=allowed_mentions,
                    suppress=True,
                )
                last_message.content = response

            # we want to abort the response only after we've sent any valid
            # messages, and potentially removed any partial immersion-breaking
            # lines that we posted when they were in the process of being received.
            if abort_response:
                break

            this_response_stat.log_response_part()

        if last_message is not None:
            self.repetition_tracker.log_message(
                response_channel_id,
                discord_utils.discord_message_to_generic_message(last_message),
            )

        return last_message

    def _filter_immersion_breaking_lines(
    self, text: str
    ) -> typing.Tuple[str, bool]:
        """
        Given a string that represents an individual response message,
        filter out any lines that would break immersion.

        These include lines that include a termination symbol, lines
        that attempt to carry on the conversation as a different user,
        and lines that include text which is part of the AI prompt.

        Returns the subset of the input string that should be sent,
        and a boolean indicating if we should abort the response entirely,
        ignoring any further lines.
        """
        # This pattern uses a positive lookahead to keep the punctuation at the end of the sentence
        split_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        # First, split the text by 'real' newlines to preserve them
        lines = text.split('\n')
        good_lines = []
        abort_response = False

        for line in lines:
            # Split the line by the pattern to get individual sentences
            sentences = re.split(split_pattern, line)
            good_sentences = []

            for sentence in sentences:
                # if the AI gives itself a second line, just ignore
                # the line instruction and continue
                if self.prompt_generator.bot_prompt_line == sentence:
                    fancy_logger.get().warning(
                        "Filtered out %s from response, continuing", sentence
                    )
                    continue

                # hack: abort response if it looks like the AI is
                # continuing the conversation as someone else
                if self.prompt_finder.match(sentence):
                    fancy_logger.get().warning(
                        'Filtered out "%s" from response, aborting', sentence
                    )
                    abort_response = True
                    break

                # look for partial stop markers within a sentence
                for marker in self.stop_markers:
                    if marker in sentence:
                        (keep_part, removed) = sentence.split(marker, 1)
                        fancy_logger.get().warning(
                            'Filtered out "%s" from response, aborting',
                            removed,
                        )
                        if keep_part:
                            good_sentences.append(keep_part)
                        abort_response = True
                        break

                if abort_response:
                    break

                # filter out sentences that are entirely made of whitespace
                if not sentence.strip():
                    continue

                good_sentences.append(sentence)

            if abort_response:
                break

            # Join the good sentences with a space and append to good_lines
            good_line = " ".join(good_sentences)
            if good_line:
                good_lines.append(good_line)

        return ("\n".join(good_lines), abort_response)

    ########
    async def _filter_history_message(
      self,
      message: discord.Message,
      stop_before_message_id: typing.Optional[int],
   ) -> typing.Tuple[typing.Optional[types.GenericMessage], bool]:
      """
      Filter out any messages that we don't want to include in the
      AI's history.

      These include:
       - messages generated by our image generator
       - messages at or before the stop_before_message_id

      Also, modify the message in the following ways:
       - if the message is from the AI, set the author name to
         the AI's persona name, not its Discord account name
       - remove <@_0000000_> user-id based message mention text,
         replacing them with @username mentions
      """
      # if we've hit the throttle message, stop and don't add any
      # more history
      if stop_before_message_id and message.id == stop_before_message_id:
         return (None, False)

      generic_message = discord_utils.discord_message_to_generic_message(message)

      if generic_message.author_id == self.ai_user_id:
         # make sure the AI always sees its persona name
         # in the transcript, even if the chat program
         # has it under a different account name
         generic_message.author_name = self.persona.ai_name

         # hack: use the suppress_embeds=True flag to indicate
         # that this message is one we generated as part of a text
         # response, as opposed to an image or application message
         if not message.flags.suppress_embeds:
            # this is a message generated by our image generator
            return (None, True)

      if isinstance(message.channel, discord.DMChannel):
         fn_user_id_to_name = discord_utils.dm_user_id_to_name(
            self.ai_user_id,
            self.persona.ai_name,
         )
      elif isinstance(message.channel, discord.TextChannel):
         fn_user_id_to_name = discord_utils.guild_user_id_to_name(
            message.channel.guild,
         )
      elif isinstance(message.channel, discord.GroupChannel):
         fn_user_id_to_name = discord_utils.group_user_id_to_name(
            message.channel,
         )
      else:
         fn_user_id_to_name = discord_utils.dm_user_id_to_name(
            self.ai_user_id,
            self.persona.ai_name,
         )

      discord_utils.replace_mention_ids_with_names(
         generic_message,
         fn_user_id_to_name=fn_user_id_to_name,
      )
      return (generic_message, True)

    async def _filtered_history_iterator(
        self,
        async_iter_history: typing.AsyncIterator[discord.Message],
        stop_before_message_id: typing.Optional[int],
        ignore_all_until_message_id: typing.Optional[int],
        limit: int,
    ) -> typing.AsyncIterator[types.GenericMessage]:
        """
        When returning the history of a thread, Discord
        does not include the message that kicked off the thread.

        It will show it in the UI as if it were, but it's not
        one of the messages returned by the history iterator.

        This method attempts to return that message as well,
        if we need it.
        """
        items = 0
        last_returned = None
        ignoring_all = ignore_all_until_message_id is not None
        async for item in async_iter_history:
            if items >= limit:
                return

            if ignoring_all:
                if item.id == ignore_all_until_message_id:
                    ignoring_all = False
                else:
                    # this message was sent after the message we're
                    # responding to.  So filter out it as to not confuse
                    # the AI into responding to content from that message
                    # instead
                    continue

            last_returned = item
            (sanitized_message, allow_more) = await self._filter_history_message(
                item,
                stop_before_message_id=stop_before_message_id,
            )
            if not allow_more:
                # we've hit a message which requires us to stop
                # and look at more history
                return
            if sanitized_message is not None:
                yield sanitized_message
                items += 1

        if last_returned is not None and items < limit:
            # we've reached the beginning of the history, but
            # still have space.  If this message was a reply
            # to another message, return that message as well.
            if last_returned.reference is None:
                return

            ref = last_returned.reference.resolved

            # the resolved message may be None if the message
            # was deleted
            if ref is not None and isinstance(ref, discord.Message):
                (sanitized_message, _) = await self._filter_history_message(
                    ref,
                    stop_before_message_id,
                )
                if sanitized_message is not None:
                    yield sanitized_message

    # when looking through the history of a channel, we'll have a goal
    # of retrieving a certain number of lines of history.  However,
    # there are some messages in the history that we'll want to filter
    # out.  These include messages that were generated by our image
    # generator, as well as certain messages that will be ignored
    # in order to generate a response for a specific user who
    # @-mentions the bot.
    #
    # This is the maximum number of "extra" messages to retrieve
    # from the history, in an attempt to find enough messages
    # that we can filter out the ones we don't want and still
    # have enough left over to satisfy the request.
    #
    # Note that since the history is returned in reverse order,
    # and each is pulled in only as needed, there's not much of a
    # penalty to making this somewhat large.  But still, we want
    # to keep it reasonable.
    MESSAGE_HISTORY_LOOKBACK_BONUS = 20

    async def _recent_messages_following_thread(
        self,
        channel: discord.abc.Messageable,
        stop_before_message_id: typing.Optional[int],
        ignore_all_until_message_id: typing.Optional[int],
        num_history_lines: int,
        image_descriptions: typing.List[str],  # Add this parameter
    ) -> typing.AsyncIterator[types.GenericMessage]:
        max_messages_to_check = num_history_lines + self.MESSAGE_HISTORY_LOOKBACK_BONUS
        history = channel.history(limit=max_messages_to_check)
        result = self._filtered_history_iterator(
            history,
            limit=num_history_lines,
            stop_before_message_id=stop_before_message_id,
            ignore_all_until_message_id=ignore_all_until_message_id,
        )


        return result
