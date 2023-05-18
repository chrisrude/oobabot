# Configuring **`oobabot`**

## Using a config.yml file

You can run oobabot from the command line, or you can use a config.yml
file.  The config.yml file is a YAML file that contains all the
settings you would normally pass on the command line, and more.

### Creating a new `config.yml` file

Pass `--generate-config` to the CLI to print a fresh new config.yml
file to STDOUT.  You can then redirect this to a file.

This file will include any other settings you've supplied on the
command line.  So if you're upgrading from an earlier version,
all you have to do is:

If you've been running with the CLI alone, all you need to do is:
  `oobabot {your normal args} --generate-config > config.yml`

and then
  `oobabot`

## Where to place `config.yml`

`oobabot` will look for a config.yml file in the current
directory by default.  If you want to place it somewhere
else, you can specify a different location with the
`--config-file` flag.  e.g.

```bash
   oobabot --config-file /path/to/config.yml
```

### Upgrading from an earlier version

If you ever upgrade and want to regenerate the config.yml,
you can just do this:

  ```bash
  cp config.yml config.yml.backup &&
  oobabot --config config.yml.backup --generate-config > config.yml
  ```

> Note: it's important to **make a backup copy of your config.yml** first,
> because the pipe command in the second line will overwrite it!

Your previous config.yml file will be read before generating the new one,
and the new one will include all the settings from the old one, plus
any new settings that have been added since the last time you generated
the config.yml file.

## All of the Settings

The config.yml file contains comments on all its settings, so you can
just check out [this sample config.yml file here.](./config.sample.yml)
