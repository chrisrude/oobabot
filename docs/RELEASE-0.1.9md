# Release v.0.1.9

Very minor release, mainly want to get this out to support a big pending update in the new [Oobabot-plugin GUI for Oobaboog's Text Generation WebUI.](https://github.com/chrisrude/oobabot-plugin)

## New Features

### Unsolicited Reply Cap

There's a new `unsolicited_channel_cap` option in
`discord` section of `config.yml`.  It does this:

FEATURE PREVIEW: Adds a limit to the number of channels
the bot will post unsolicited messages in at the same
time.  This is to prevent the bot from being too noisy
in large servers.

When set, only the most recent N channels the bot has
been summoned in will have a chance of receiving an
unsolicited message.  The bot will still respond to
@-mentions and wake words in any channel it can access.

Set to 0 to disable this feature.

## Breaking Changes

### Remove deprecated command-line options

The following CLI arguments have been removed:

- `diffusion_steps`
- `image_height`
- `image_width`
- `stable_diffusion_sampler`
- `sd_negative_prompt`
- `sd_negative_prompt_nsfw`

All of these settings are still changeable via the config file.

If you don't have a config file, you can generate one first on your previous version by using:
``oobabot [all your normal CLI arguments] --generate-config > config.yml

From the directory you run oobabot from.  Now all your CLI arguments are stored in the yml file,
and you don't need to pass them anymore.

## Bug Fixes / Tech Improvements

- add a method to generate / load yml config files from another package

- Discord's own logs are now included in the standard logging output, in a purple background

### Full Changelog

[Changes from 0.1.8 to 0.1.9](https://github.com/chrisrude/oobabot/compare/v0.1.8...v0.1.9)
