from unittest.mock import MagicMock

import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.oav.oav_detector import OAV
from dodal.devices.oav.oav_parameters import OAVParameters
from dodal.devices.smargon import Smargon
from ophyd.sim import make_fake_device

from artemis.exceptions import WarningException
from artemis.experiment_plans.pin_tip_centring_plan import (
    move_pin_into_view,
    move_smargon_warn_on_out_of_range,
    move_so_that_beam_is_at_pixel,
)


def test_given_the_pin_tip_is_already_in_view_when_get_tip_into_view_then_tip_returned_and_smargon_not_moved(
    smargon: Smargon, oav: OAV
):
    smargon.x.user_readback.sim_put(0)
    oav.mxsc.pin_tip.tip_x.sim_put(100)
    oav.mxsc.pin_tip.tip_y.sim_put(200)

    oav.mxsc.pin_tip.trigger = MagicMock(side_effect=oav.mxsc.pin_tip.trigger)

    RE = RunEngine(call_returns_result=True)
    result = RE(move_pin_into_view(oav, smargon))

    oav.mxsc.pin_tip.trigger.assert_called_once()
    assert smargon.x.user_readback.get() == 0
    assert result.plan_result == (100, 200)


def test_given_no_tip_found_but_will_be_found_when_get_tip_into_view_then_smargon_moved_positive_and_tip_returned(
    smargon: Smargon, oav: OAV
):
    oav.mxsc.pin_tip.triggered_tip.put(oav.mxsc.pin_tip.INVALID_POSITION)
    oav.mxsc.pin_tip.validity_timeout.put(0.01)

    smargon.x.user_readback.sim_put(0)

    def set_pin_tip_when_x_moved(*args, **kwargs):
        oav.mxsc.pin_tip.tip_x.sim_put(100)
        oav.mxsc.pin_tip.tip_y.sim_put(200)

    smargon.x.subscribe(set_pin_tip_when_x_moved, run=False)

    RE = RunEngine(call_returns_result=True)
    result = RE(move_pin_into_view(oav, smargon))

    assert smargon.x.user_readback.get() == 1
    assert result.plan_result == (100, 200)


def test_given_tip_at_zero_but_will_be_found_when_get_tip_into_view_then_smargon_moved_negative_and_tip_returned(
    smargon: Smargon, oav: OAV
):
    oav.mxsc.pin_tip.tip_x.sim_put(0)
    oav.mxsc.pin_tip.tip_y.sim_put(100)
    oav.mxsc.pin_tip.validity_timeout.put(0.01)

    smargon.x.user_readback.sim_put(0)

    def set_pin_tip_when_x_moved(*args, **kwargs):
        oav.mxsc.pin_tip.tip_x.sim_put(100)
        oav.mxsc.pin_tip.tip_y.sim_put(200)

    smargon.x.subscribe(set_pin_tip_when_x_moved, run=False)

    RE = RunEngine(call_returns_result=True)
    result = RE(move_pin_into_view(oav, smargon))

    assert smargon.x.user_readback.get() == -1
    assert result.plan_result == (100, 200)


def test_given_no_tip_found_ever_when_get_tip_into_view_then_smargon_moved_positive_and_exception_thrown(
    smargon: Smargon, oav: OAV
):
    oav.mxsc.pin_tip.triggered_tip.put(oav.mxsc.pin_tip.INVALID_POSITION)
    oav.mxsc.pin_tip.validity_timeout.put(0.01)

    smargon.x.user_readback.sim_put(0)

    with pytest.raises(WarningException):
        RE = RunEngine(call_returns_result=True)
        RE(move_pin_into_view(oav, smargon))

    assert smargon.x.user_readback.get() == 1


def test_given_moving_out_of_range_when_move_with_warn_called_then_warning_exception(
    RE: RunEngine,
):
    fake_smargon = make_fake_device(Smargon)(name="")
    fake_smargon.x.user_setpoint.sim_set_limits([0, 10])

    with pytest.raises(WarningException):
        RE(move_smargon_warn_on_out_of_range(fake_smargon, (100, 0, 0)))


@pytest.mark.parametrize(
    "px_per_um, beam_centre, angle, pixel_to_move_to, expected_xyz",
    [
        # Simple case of beam being in the top left and each pixel being 1 mm
        ([1000, 1000], [0, 0], 0, [100, 190], [100, 190, 0]),
        ([1000, 1000], [0, 0], -90, [50, 250], [50, 0, 250]),
        ([1000, 1000], [0, 0], 90, [-60, 450], [-60, 0, -450]),
        # Beam offset
        ([1000, 1000], [100, 100], 0, [100, 100], [0, 0, 0]),
        ([1000, 1000], [100, 100], -90, [50, 250], [-50, 0, 150]),
        # Pixels_per_micron different
        ([10, 50], [0, 0], 0, [100, 190], [1, 9.5, 0]),
        ([60, 80], [0, 0], -90, [50, 250], [3, 0, 20]),
    ],
)
def test_values_for_move_so_that_beam_is_at_pixel(
    smargon: Smargon,
    test_config_files,
    RE,
    px_per_um,
    beam_centre,
    angle,
    pixel_to_move_to,
    expected_xyz,
):
    params = OAVParameters(context="loopCentring", **test_config_files)
    params.micronsPerXPixel = px_per_um[0]
    params.micronsPerYPixel = px_per_um[1]
    params.beam_centre_i = beam_centre[0]
    params.beam_centre_j = beam_centre[1]

    smargon.omega.user_readback.sim_put(angle)

    RE(move_so_that_beam_is_at_pixel(smargon, pixel_to_move_to, params))

    assert smargon.x.user_readback.get() == pytest.approx(expected_xyz[0])
    assert smargon.y.user_readback.get() == pytest.approx(expected_xyz[1])
    assert smargon.z.user_readback.get() == pytest.approx(expected_xyz[2])
