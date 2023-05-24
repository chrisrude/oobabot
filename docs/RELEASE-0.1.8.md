# Release v.0.1.8

Lots of bugfixes in this release, and a lot of behind-the-scenes work to support a proper plugin to Oobabooga.  Coming Soon (tm)!

However, there a number of small new features as well.

## New Features

### Reading Personas from a File

In `config.yml`, in `persona` > `persona_file`, you can now specify a path to a .yml, .json or .txt file containing a persona.

This file can be just a single string, a json file in the common "tavern" formats, or a yaml file in the Oobabooga format.

With a single string, the persona will be set to that string.  Otherwise, the ai_name and persona will be overwritten with the values in the file.  Also, the wakewords will be extended to include the character's own name.

### Regex-based message splitting

This new setting is in `oobabooga` > `message_regex`.

Some newer chat-specific models are trained to generate specific delimiters to separate their response into individual messages.

This adds a setting to tell the bot what regex to use to split such responses into individual messages.

If this is set, it will only effect *how* message-splitting happens, not whether it happens.  By default, the bot will still split messages.  But if `stream_responses` or `dont_split_responses` is enabled, this setting will be ignored, as the messages won't be split anyway.

### `--invite-url` command line option

This will generate an invite URL for the bot, and print it to the console.  This is useful for when you have a new bot, or want to generate a new invite URL to add it to a new server.  It will also automatically be printed if we notice the bot is listening on zero servers.

## Configurable logging level

In `config.yml`, in `discord` > `log_level`, you can now specify the logging level.

## Breaking Changes

Reminder that the deprecated CLI methods are going away soon.

## Bug Fixes / Tech Improvements

- replace `<@___user_id___>` with the user's display name in history.  This would confuse the AI, and leak syntax into its regular chat.

- Add "draw me" to the list of words that will trigger a picture

- Inline stop tokens

  With this change, we'll now look for stop tokens even if they're not on a separate line.
  Also, automatically add anything from `oobabot` > `request_params` > `stopping_strings` into the list of stop tokens to look for.

- Don't allow the bot to @-mention anyone but the user who it's replying
to.  This is to prevent users from tricking the bot into pinging broad
groups, should the admin have granted them permission to do so.
  @-mentions will still work when used via the /say command, which I am
presuming will be used by trusted users

- The bot will now mark its responses to @-mentions or keywords by showing an explicit reply in Discord.  When this happens, the bot will not see any history "after" the summon.  Unsolicited replies will see the full message history, and will not show an explicit reply.  This is to help make it clear when the bot is responding to a specific message, and when it's responding to the channel in general.

- turn 'token space too small' message from error into warning
  This is to allow users to crank it super high if they want, and let messages be dropped if they run out of space.

### Full Changelog

[Changes from 0.1.7 to 0.1.8](https://github.com/chrisrude/oobabot/compare/v0.1.7...v0.1.8)
