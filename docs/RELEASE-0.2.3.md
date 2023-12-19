
# Release v.0.2.3

Note: version 0.2.2 only updated oobabot-plugin, not oobabot.  This
shows changes to oobabot since the prior release, [v0.2.1](RELEASE-0.2.1.md).

## What's Changed

Mainly a bugfix update for 0.2.1, with a few fixes and configuration
parameters.

## New Features

* Option to disable unsolicited replies entirely

Unsolicited replies are still enabled by default, but you can now disable them entirely by changing this setting in your config.yml:

```yaml
  # If set, the bot will not reply to any messages that do not @-mention it or include a
  # wakeword.  If unsolicited replies are disabled, the unsolicited_channel_cap setting will
  # have no effect.
  #   default: False
  disable_unsolicited_replies: true
```

The objective of this change is to support cases where
unsolicited replies are not desired, such as when the bot is used in a
channel with a high volume of messages.

## Bug Fixes / Tech Improvements

* Unicode logging reliability fix ooba_client.py

  Unicode bugs in oobabooga seem to be a moving target, so
this fix gates the fix applied in 0.2.1 to only be applied
in cases where oobabooga is known to be broken.

* Security fix: Bump aiohttp from 3.8.4 to 3.8.5

  Update dependency aiohttp to v3.8.5.  This fixes [a security
issue in aiohttp](https://github.com/aio-libs/aiohttp/blob/v3.8.5/CHANGES.rst).  On a quick scan it doesn't seem to be something
a user could exploit within oobabot, but better to update anyway.

* Preserve newlines when prompting the bot

  In some cases the whitespace in user messages is important.  One case is
described in the [issue 76, reported by @xydreen](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-45c4-8wx5-qw6w).

  When sending a prompt to the bot, we will now preserve any newlines
that the bot itself had generated in the past.

  We will still strip newlines from messages from user-generated messages,
as otherwise they would have the ability to imitate our prompt format.
This would let users so inclined to fool the bot into thinking a
message was sent by another user, or even itself.

### Full Changelog

[All changes from 0.2.1 to 0.2.3](https://github.com/chrisrude/oobabot/compare/v0.2.1...v0.2.3)
