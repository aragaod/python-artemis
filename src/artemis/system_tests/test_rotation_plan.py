from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from artemis.experiment_plans.rotation_scan_plan import (
    DEFAULT_DIRECTION,
    create_devices,
    move_to_end_w_buffer,
    move_to_start_w_buffer,
)

if TYPE_CHECKING:
    from dodal.devices.backlight import Backlight  # noqa
    from dodal.devices.detector_motion import DetectorMotion  # noqa
    from dodal.devices.eiger import EigerDetector  # noqa
    from dodal.devices.smargon import Smargon
    from dodal.devices.zebra import Zebra  # noqa


@pytest.fixture()
def devices():
    with patch("artemis.experiment_plans.rotation_scan_plan.i03.backlight"), patch(
        "artemis.experiment_plans.rotation_scan_plan.i03.detector_motion"
    ):
        return create_devices()


TEST_OFFSET = 1
TEST_SHUTTER_DEGREES = 2


@pytest.mark.s03()
def test_move_to_start(devices, RE):
    # may need to run 'caput BL03S-MO-SGON-01:OMEGA.VMAX 120' as S03 has 45 by default
    smargon: Smargon = devices["smargon"]
    start_angle = 153
    RE(
        move_to_start_w_buffer(
            smargon.omega, start_angle, TEST_OFFSET, wait_for_velocity_set=False
        )
    )
    velocity = smargon.omega.velocity.get()
    omega_position = smargon.omega.user_setpoint.get()

    assert velocity == 120
    assert omega_position == (start_angle - TEST_OFFSET * DEFAULT_DIRECTION)


@pytest.mark.s03()
def test_move_to_end(devices, RE):
    smargon: Smargon = devices["smargon"]
    scan_width = 153
    RE(move_to_end_w_buffer(smargon.omega, scan_width, TEST_OFFSET))
    omega_position = smargon.omega.user_setpoint.get()

    assert omega_position == (
        (scan_width + TEST_OFFSET * 2 + TEST_SHUTTER_DEGREES) * DEFAULT_DIRECTION
    )
