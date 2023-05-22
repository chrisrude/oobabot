# -*- coding: utf-8 -*-
"""
Settings library which supports both CLI and YAML settings files.
Allows for settings to be exposed through one or both of these interfaces.

load - sets defaults, then loads from YAML, then loads from CLI.
load_from_cli - sets defaults, then loads from CLI only.
load_from_dict - sets defaults, then loads from a dictionary only.
load_from_yaml - sets defaults, then loads from YAML only.
write_to_file - writes the given config as YAML to the given file.
write_to_stream - writes the given config as YAML to the given stream.
"""

import argparse
import textwrap
import typing

import ruamel.yaml as ryaml

import oobabot

YAML_WIDTH = 88
DIVIDER = "# " * (YAML_WIDTH >> 1)
INDENT_UNIT = 2

SettingDictType = typing.Dict[
    str, typing.Union[bool, int, float, str, typing.List[str]]
]

SettingValueType = typing.Union[
    bool, int, float, str, typing.List[str], SettingDictType
]


def format_yaml_comment(comment_lines: typing.List[str]) -> str:
    out = []
    for line in comment_lines:
        out.append("\n".join(textwrap.wrap(line, width=YAML_WIDTH)))
    return "\n" + "\n".join(out)


def add_to_group(
    group: ryaml.CommentedMap,
    key: str,
    value: typing.Any,
    comment_lines: typing.List[str],
    indent: int,
) -> None:
    group[key] = value
    group.yaml_set_comment_before_after_key(
        key,
        before=format_yaml_comment(comment_lines),
        indent=indent,
    )


T = typing.TypeVar("T", bound="SettingValueType")


class ConfigSetting(typing.Generic[T]):
    """
    An individual setting that can be exposed through CLI and/or YAML
    """

    data_type: T
    description_lines: typing.List[str]
    cli_args: typing.List[str]
    include_in_argparse: bool
    include_in_yaml: bool
    show_default_in_yaml: bool
    fn_on_set: typing.Callable[[T], None]

    def __init__(
        self,
        name: str,
        default: T,
        description_lines: typing.List[str],
        cli_args: typing.Optional[typing.List[str]] = None,
        place_default_in_yaml: bool = False,
        include_in_argparse: bool = True,
        include_in_yaml: bool = True,
        show_default_in_yaml: bool = True,
        fn_on_set: typing.Callable[[T], None] = lambda x: None,
    ):
        self.name = name
        self.default = default
        self.description_lines = [x.strip() for x in description_lines]
        if cli_args is None:
            cli_args = ["--" + name.replace("_", "-")]
        self.cli_args = cli_args
        self.value = default
        self.include_in_argparse = include_in_argparse
        self.include_in_yaml = include_in_yaml
        self.place_default_in_yaml = place_default_in_yaml
        self.show_default_in_yaml = show_default_in_yaml
        self.fn_on_set = fn_on_set

    def add_to_argparse(self, parser: argparse._ArgumentGroup):
        if not self.include_in_argparse:
            return

        kwargs = {
            "default": self.value,
            "help": " ".join(self.description_lines),
        }

        # note: the other way to do this is with
        #   typing.get_args(self.__orig_class__)[0]
        # but that isn't officially supported, so
        # let's do it the jankier way
        if isinstance(self.default, str):
            kwargs["type"] = str
        elif isinstance(self.default, bool):
            kwargs["action"] = "store_true"
            if self.default:
                kwargs["action"] = "store_false"
        elif isinstance(self.default, int):
            kwargs["type"] = int
        elif isinstance(self.default, float):
            kwargs["type"] = float
        elif isinstance(self.default, list):
            kwargs["type"] = str
            kwargs["nargs"] = "*"

        parser.add_argument(*self.cli_args, **kwargs)

    def set_value_from_argparse(self, args: argparse.Namespace) -> None:
        if not self.include_in_argparse:
            return
        if not hasattr(args, self.name):
            raise ValueError(f"Namespace does not have attribute {self.name}")
        self.set_value(getattr(args, self.name))

    def add_to_yaml_group(self, group: ryaml.CommentedMap):
        if not self.include_in_yaml:
            return
        value = None
        if self.place_default_in_yaml or (self.value != self.default):
            value = self.value
        add_to_group(
            group,
            key=self.name,
            value=value,
            comment_lines=self.make_yaml_comment(),
            indent=INDENT_UNIT,
        )

    def make_yaml_comment(self) -> typing.List[str]:
        comment_lines = self.description_lines.copy()

        if self.show_default_in_yaml:
            if self.default is not None:
                comment_lines.append(f"  default: {self.default}")
            else:
                comment_lines.append("  default: None")
        return comment_lines

    def set_value_from_yaml(self, yaml: ryaml.CommentedMap) -> None:
        if not self.include_in_yaml:
            return
        if self.name not in yaml:
            return
        if (not self.place_default_in_yaml) and (yaml[self.name] is None):
            # if we didn't place the default in the yaml, and the setting
            # is now blank, that's no surprise.  Keep the default
            # rather than overwriting it with None
            return
        value = yaml[self.name]
        # if value is a dict, it's possible that it only contains
        # some, but not all of the keys that we need.  So we want to
        # merge it with the default dict, overwriting the default
        # values with the values from the yaml
        if isinstance(value, dict):
            if isinstance(self.default, dict):
                value = {**self.default, **value}
            else:
                raise ValueError(
                    f"Setting {self.name} is a dict, but the default value is not"
                )
        # note: keeping the type checker happy across python versions
        # here is actually kinda hard.  It's worried about what the
        # values in the combined dict might be.  But really it's fine,
        # so just tell it to chill.
        self.set_value(value)  # type: ignore

    def set_value(self, value: T) -> None:
        self.value = value
        self.fn_on_set(value)

    def get(self) -> T:
        if isinstance(self.value, dict):
            return self.value.copy()
        return self.value


class ConfigSettingGroup:
    """
    A group of related settings that can be exposed through CLI and/or YAML
    """

    name: str
    description: str
    settings: typing.Dict[str, ConfigSetting]

    def __init__(
        self,
        name: str,
        description: str = "",
        include_in_argparse: bool = True,
        include_in_yaml: bool = True,
    ):
        self.name = name
        self.description = description
        self.settings = {}
        self.include_in_argparse = include_in_argparse
        self.include_in_yaml = include_in_yaml

    def add_setting(self, setting: "ConfigSetting") -> None:
        self.settings[setting.name] = setting

    def add_to_argparse(self, parser: argparse.ArgumentParser):
        if not self.include_in_argparse:
            return
        arg_group = parser.add_argument_group(self.name, self.description)
        for setting in self.settings.values():
            setting.add_to_argparse(arg_group)

    def set_values_from_argparse(self, args: argparse.Namespace) -> None:
        if not self.include_in_argparse:
            return
        for setting in self.settings.values():
            setting.set_value_from_argparse(args)

    def add_to_yaml(self, yaml: ryaml.CommentedMap):
        if not self.include_in_yaml:
            return
        group_key = self.name.lower().replace(" ", "_")

        group = ryaml.CommentedMap()
        for setting in self.settings.values():
            setting.add_to_yaml_group(group)

        add_to_group(
            group=yaml,
            key=group_key,
            value=group,
            comment_lines=[DIVIDER, group_key, "."],
            indent=0,
        )

    def set_values_from_yaml(self, yaml: dict):
        if not self.include_in_yaml:
            return
        if yaml is None:
            return
        group_key = self.name.lower().replace(" ", "_")
        if group_key not in yaml:
            return
        group = yaml[group_key]
        for setting in self.settings.values():
            setting.set_value_from_yaml(group)

    def set_values_from_dict(self, main_dict: dict):
        group_dict = main_dict.get(self.name.lower().replace(" ", "_"), {})
        for setting in self.settings.values():
            if setting.name in group_dict:
                val = group_dict[setting.name]
                setting.set_value(val)

    def set(self, name: str, value: SettingValueType) -> None:
        self.settings[name].set_value(value)

    def get_setting(self, name: str) -> ConfigSetting:
        return self.settings[name]

    def get(self, name: str) -> SettingValueType:
        return self.settings[name].value

    def get_str(self, name: str) -> str:
        return self.settings[name].value

    def get_list(self, name: str) -> typing.List[SettingValueType]:
        return self.settings[name].value

    def get_all(self) -> typing.Dict[str, SettingValueType]:
        return {name: setting.get() for (name, setting) in self.settings.items()}.copy()


def load_from_yaml(
    filename: str,
    setting_groups: typing.List["ConfigSettingGroup"],
) -> None:
    """
    Load settings from a YAML file only
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            yaml = ryaml.YAML(typ="safe")
            yaml_settings = yaml.load(file)
            for group in setting_groups:
                group.set_values_from_yaml(yaml_settings)

    except (FileNotFoundError, IsADirectoryError):
        pass


def load_from_cli(
    args,
    setting_groups: typing.List["ConfigSettingGroup"],
) -> argparse.ArgumentParser:
    """
    Load settings from the command line only
    """
    cli_parser = argparse.ArgumentParser(
        description=f"oobabot v{oobabot.__version__}: Discord bot for "
        + "oobabooga's text-generation-webui",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=False,
    )

    # we need to initialize argparse AFTER we read from
    # the yaml file, so that the argparse defaults are
    # set to the yaml-read values.
    for group in setting_groups:
        group.add_to_argparse(cli_parser)

    cli_settings = cli_parser.parse_args(args=args)
    for group in setting_groups:
        group.set_values_from_argparse(cli_settings)

    return cli_parser


def load_from_dict(
    setting_groups: typing.List["ConfigSettingGroup"],
    settings_dict: dict,
) -> None:
    """
    Load settings from a dictionary
    """
    print(f"settings_dict: {settings_dict}")
    for group in setting_groups:
        group.set_values_from_dict(settings_dict)


def load(
    cli_args: typing.List[str],
    setting_groups: typing.List["ConfigSettingGroup"],
    config_file: str,
) -> argparse.ArgumentParser:
    """
    Load settings from defaults, config.yml, and command line arguments
    in that order.  Later sources will overwrite earlier ones.

    Returns the argparse parser, which can be used to print out the help
    message.
    """
    load_from_yaml(config_file, setting_groups)
    namespace = load_from_cli(cli_args, setting_groups)

    # returning this since it can print out the help message
    return namespace


START_COMMENT = textwrap.dedent(
    """
    # Welcome to Oobabot!
    #
    # This is the configuration file for Oobabot.  It is a YAML file, and
    # comments are allowed.  Oobabot attempts to load a file named
    # "config.yml" from the current directory when it is run.
    #
    """
)


def write_to_stream(
    setting_groups: typing.List["ConfigSettingGroup"],
    out_stream: typing.TextIO,
) -> None:
    yaml_map = ryaml.CommentedMap()
    yaml_map.yaml_set_start_comment(START_COMMENT)

    add_to_group(
        group=yaml_map,
        key="version",
        value=oobabot.__version__,
        comment_lines=[],
        indent=0,
    )

    for group in setting_groups:
        group.add_to_yaml(yaml_map)

    yaml = ryaml.YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.indent(mapping=INDENT_UNIT, sequence=2 * INDENT_UNIT, offset=INDENT_UNIT)

    yaml.dump(yaml_map, out_stream)


def write_to_file(
    setting_groups: typing.List["ConfigSettingGroup"], filename: str
) -> None:
    """
    Write the current values in the setting groups to a YAML file
    """
    with open(filename, "w", encoding="utf-8") as file:
        write_to_stream(setting_groups, file)
