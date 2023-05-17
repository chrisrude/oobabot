# -*- coding: utf-8 -*-
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
        add_to_group(
            group,
            key=self.name,
            value=self.value,
            comment_lines=self.make_yaml_comment(),
            indent=INDENT_UNIT,
        )

    def make_yaml_comment(self) -> typing.List[str]:
        comment_lines = self.description_lines.copy()

        if self.show_default_in_yaml:
            if self.default is not None:
                comment_lines.append(f"  default: {str(self.default).lower()}")
            else:
                comment_lines.append("  default: None")
        return comment_lines

    def set_value_from_yaml(self, yaml: ryaml.CommentedMap) -> None:
        if not self.include_in_yaml:
            return
        if self.name not in yaml:
            return
        self.set_value(yaml[self.name])

    def set_value(self, value: T) -> None:
        self.value = value
        self.fn_on_set(value)

    def get(self) -> T:
        if isinstance(self.value, dict):
            return self.value.copy()
        return self.value


class ConfigSettingGroup:
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
    try:
        with open(filename, "r", encoding="utf-8") as f:
            yaml = ryaml.YAML(typ="safe")
            yaml_settings = yaml.load(f)
            for group in setting_groups:
                group.set_values_from_yaml(yaml_settings)

    except FileNotFoundError:
        pass


def load_from_cli(
    args,
    setting_groups: typing.List["ConfigSettingGroup"],
) -> argparse.ArgumentParser:
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


def load(
    args: typing.List[str],
    setting_groups: typing.List["ConfigSettingGroup"],
    filename: str,
) -> argparse.ArgumentParser:
    # Load settings in this order.
    # The later sources will overwrite the earlier ones.
    #
    #  1. config.yml
    #  2. command line arguments
    #
    load_from_yaml(filename, setting_groups)
    namespace = load_from_cli(args, setting_groups)

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


def write_sample_config(
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
