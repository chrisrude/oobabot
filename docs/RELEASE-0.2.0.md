# Release v.0.2.0

Long time since the last release, but tons of work!

## New Features

### Backend changes for AUDIO SUPPORT 🥳 (coming soon)

This release includes a lot of work to support audio
channels.  This still needs to be documented and packaged,
but it is a thing that works!  Look for full support in
version 0.2.1, but here's a preview of what's coming:

- oobabot will be able to join audio channels using the `/join_voice` command
- it will transcribe audio from the channel, recording which user said what
- it will listen to wake-words, and respond using voice synthesis
- if you're using `oobabot-plugin`, you'll get a pretty transcript of the
  conversation

This has been a ton of work, and I'm eager to get to putting on the finishing
touches and get it out.  In the meantime, I wanted to release the now-unified
backend, so that I can make sure that it is stable, so that I can focus on
polishing the audio work.  Also, a few important bugs have been reported in
the meantime, and I don't want to hold those back.

## Add new .yaml settings

### stream_responses_speed_limit

When in "streaming" mode (i.e. when stream_responses is set to True), this will limit the
rate at which we update the streaming message in Discord.  We need this setting because Discord has rate-limiting logic, and if we send updates "too fast" then it will slow down our updates drastically, which will appear as jerky streaming.

This value is the minimum delay in seconds in between updates.  That is -- we will update Discord no more than once this number of seconds.  The updates may come slower than this, perhaps on systems that take a long time to generate tokens.  It's only guaranteed that they won't be any faster than this.

Previously, this value was hard-coded to 0.5.  Now the default is 0.7, which was determined by user testing.  Thanks to [@jmoney7823956789378](https://github.com/jmoney7823956789378) for helping make this happen!

### `discrivener_location` and `discrivener_model_location`

These are new settings to add voice support to oobabot.  Voice support means that the bot
can join voice chat channels, transcribe what is said, hear wakewords, and generate voice
responses in those channels.  All of the audio processing -- text to speech, and speech to
text -- is handled in a binary called "discrivener", whose source lives at [github.com/chrisrude/discrivener](https://github.com/chrisrude/discriviner).

I've tested this to work on Linux and OSX, but there is still more work to do in documenting and packaging the software.  So for now, these settings are blank by default, which will leave oobabot in text-only mode, as it has been.

### command_lobotomize_response

A user noticed that there was no setting to customize the text that gets shown when you use the `/lobotomize` command.  Whoops!  Now here it is.  This is of particular interest because the bot will see this text after a lobotomize occurs, so if you have specific character styling you want to keep it from getting confused about, then you might want to put in custom text of your choosing here.

You can also use variables `{AI_NAME}` and `{USER_NAME}` to represent the name of the AI, and the name of the user who ran the `/lobotomize` command.

### Show an error if a custom .yaml file could not be loaded

Previously, we would ignore any errors that occurred when loading a custom .yaml file, and just proceed with defaults if we could.  Now, we will show an error message to the user displaying the full path to the yaml file we could not load, and the bot will not start.

This should help users self-diagnose a number of configuration issues, such as accidentally having a syntax error in their .yaml file.

## Bug Fixes / Tech Improvements

- Fix [bug 38](https://github.com/chrisrude/oobabot/issues/38): the bot will now only
mark messages as replies if it was directly mentioned (by an @-mention or keyword).  Also,
if it is configured to reply across several messages, it will only mark the first message
in the series as a reply.  This reduces notification noise to users when using mobile clients.

- Increase default token space back to 2048.  Users who have not set a custom a token space value (aka `truncation_length`) will just have this updated automatically.
- Add new oobabooga request params:
    "epsilon_cutoff",
    "eta_cutoff",
    "tfs",
    "top_a",
    "mirostat_mode",
    "mirostat_tau", and
    "mirostat_eta"

- If the user forgets to enable either `SERVER MEMBERS INTENT` or `MESSAGE CONTENT INTENT` for their bot's Discord account, show a specific error message letting them know.

### Full Changelog

[All changes from 0.1.9 to 0.2.0](https://github.com/chrisrude/oobabot/compare/v0.1.9...v0.2.0)
