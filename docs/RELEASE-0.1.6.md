
# Release 0.1.6

## New Features

### Discord Hygiene Choices

I want the bot to act like an A+ human participant in your Discord server.  Different servers have different behavior conventions, though, so I've added some options to change how it acts:

- `--dont-split-responses`

  With this, the bot will bundle everything into a single response, rather than splitting responses by sentences.

- `--reply-in-thread`

  With this, the bot will create a new thread to respond into.  This can be great to keeping multiple conversational tracks organized on busy channels.

  A few caveats:

  - the user who summoned the bot must have "create public thread" permissions.  If they don't, the bot will ignore their summon.
  - when creating a thread, the bot will only be able to see the message that summoned it, and then any further replies in its thread.  This might be useful in some circumstances.  But it also means the bot will not have context about the conversation before the summon.

### Slash commands

slash commands~
  /lobotomize -- make the bot forget everything in the channel before the command is run
  /say "message" -- speak as the bot

| **`/command`**  | what it does |
|---------------|------------------|
| **`/lobotomize`** | make the bot forget everything in the channel before the command is run |
| **`/say "message"`** | speak as the bot |

## Breaking Changes

- Oobabot doesn't add any restrictions on who can run these commands, but luckily Discord does!  You can find this inside Discord by visiting "Server Settings" -> Integrations -> Bots and Apps -> hit the icon which looks like [/] next to your bot

If you're running on a large server, you may want to restrict who can run these commands.  I suggest creating a new role, and only allowing that role to run the commands.

- The hard-coded token budget has been decreased from 2048 to 730.  This was based on reports from users who were running models which didn't actually support 2048 tokens, myself included.  This will be configurable in the future, but for now this a safer default.

- The default number of history lines has decreased from 15 to 7.  This was because of the smaller token budget, but also because 15 tokens increased inference times a lot for those running on CPUs.  This is configurable with the `--history-lines` command line argument.

## Notable Bugfixes

- if people are using nicknames, use them instead of their discord username
- fix regression in 0.1.5 which caused stable diffusion image generation to fail unless it ran in less than 5 seconds
- fix a regression when running on python <3.10.  Python 3.8.1+ should now work.

## Help Make Oobabot Better

Looking to help add to the bot?  Check out [our new CONTRIBUTING.md](https://github.com/chrisrude/oobabot/blob/main/docs/CONTRIBUTING.md).  You can also use the instructions there if you want the bleeding-edge changes from github, rather than waiting for a release.
