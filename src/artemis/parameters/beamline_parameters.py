from dataclasses import dataclass
from typing import Any, Tuple, cast

from dodal.utils import get_beamline_name

from artemis.parameters.constants import (
    BEAMLINE_PARAMETER_PATHS,
    SIM_BEAMLINE,
    SIM_INSERTION_PREFIX,
)

BEAMLINE_PARAMETER_KEYWORDS = ["FB", "FULL", "deadtime"]


@dataclass
class BeamlinePrefixes:
    beamline_prefix: str
    insertion_prefix: str


def get_beamline_prefixes():
    beamline = get_beamline_name("s03")
    if beamline == "s03":
        return BeamlinePrefixes(SIM_BEAMLINE, SIM_INSERTION_PREFIX)
    if beamline == "i03":
        return BeamlinePrefixes("BL03I", "SR03I")
    else:
        raise Exception(f"Beamline {beamline} is not currently supported by Artemis")


class GDABeamlineParameters:
    params: dict[str, Any]

    def __repr__(self) -> str:
        return repr(self.params)

    def __getitem__(self, item: str):
        return self.params[item]

    @classmethod
    def from_lines(cls, config_lines: list[str]):
        ob = cls()
        config_lines_nocomments = [line.split("#", 1)[0] for line in config_lines]
        config_lines_sep_key_and_value = [
            line.translate(str.maketrans("", "", " \n\t\r")).split("=")
            for line in config_lines_nocomments
        ]
        config_pairs: list[tuple[str, Any]] = [
            cast(Tuple[str, Any], param)
            for param in config_lines_sep_key_and_value
            if len(param) == 2
        ]
        for i, (param, value) in enumerate(config_pairs):
            if value == "Yes":
                config_pairs[i] = (config_pairs[i][0], True)
            elif value == "No":
                config_pairs[i] = (config_pairs[i][0], False)
            elif value in BEAMLINE_PARAMETER_KEYWORDS:
                pass
            else:
                config_pairs[i] = (config_pairs[i][0], float(config_pairs[i][1]))
        ob.params = dict(config_pairs)
        return ob

    @classmethod
    def from_file(cls, path: str):
        with open(path) as f:
            config_lines = f.readlines()
        return cls.from_lines(config_lines)


def get_beamline_parameters():
    beamline_name = get_beamline_name("s03")
    beamline_param_path = BEAMLINE_PARAMETER_PATHS.get(beamline_name)
    if beamline_param_path is None:
        raise KeyError(
            "No beamline parameter path found, maybe 'BEAMLINE' environment variable is not set!"
        )
    return GDABeamlineParameters.from_file(beamline_param_path)
