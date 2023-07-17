import types
from unittest.mock import ANY, MagicMock, call, patch

import bluesky.plan_stubs as bps
import numpy as np
import pytest
from bluesky.run_engine import RunEngine
from dodal.devices.det_dim_constants import (
    EIGER2_X_4M_DIMENSION,
    EIGER_TYPE_EIGER2_X_4M,
    EIGER_TYPE_EIGER2_X_16M,
)
from dodal.devices.fast_grid_scan import FastGridScan
from ophyd.sim import make_fake_device
from ophyd.status import Status

from artemis.exceptions import WarningException
from artemis.experiment_plans.fast_grid_scan_plan import (
    FGSComposite,
    get_plan,
    read_hardware_for_ispyb,
    run_gridscan,
    run_gridscan_and_move,
    wait_for_fgs_valid,
)
from artemis.external_interaction.callbacks.fgs.fgs_callback_collection import (
    FGSCallbackCollection,
)
from artemis.external_interaction.callbacks.fgs.ispyb_callback import (
    FGSISPyBHandlerCallback,
)
from artemis.external_interaction.callbacks.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from artemis.external_interaction.system_tests.conftest import (
    TEST_RESULT_LARGE,
    TEST_RESULT_MEDIUM,
    TEST_RESULT_SMALL,
)
from artemis.log import set_up_logging_handlers
from artemis.parameters import external_parameters
from artemis.parameters.plan_specific.fgs_internal_params import FGSInternalParameters


def test_given_full_parameters_dict_when_detector_name_used_and_converted_then_detector_constants_correct(
    test_fgs_params: FGSInternalParameters,
):
    assert (
        test_fgs_params.artemis_params.detector_params.detector_size_constants.det_type_string
        == EIGER_TYPE_EIGER2_X_16M
    )
    raw_params_dict = external_parameters.from_file()
    raw_params_dict["artemis_params"]["detector_params"][
        "detector_size_constants"
    ] = EIGER_TYPE_EIGER2_X_4M
    params: FGSInternalParameters = FGSInternalParameters(**raw_params_dict)
    det_dimension = (
        params.artemis_params.detector_params.detector_size_constants.det_dimension
    )
    assert det_dimension == EIGER2_X_4M_DIMENSION


def test_when_run_gridscan_called_then_generator_returned():
    plan = run_gridscan(MagicMock(), MagicMock())
    assert isinstance(plan, types.GeneratorType)


def test_read_hardware_for_ispyb_updates_from_ophyd_devices(
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    undulator_test_value = 1.234

    fake_fgs_composite.undulator.gap.user_readback.sim_put(undulator_test_value)

    synchrotron_test_value = "test"
    fake_fgs_composite.synchrotron.machine_status.synchrotron_mode.sim_put(
        synchrotron_test_value
    )

    transmission_test_value = 0.5
    fake_fgs_composite.attenuator.actual_transmission.sim_put(transmission_test_value)

    xgap_test_value = 0.1234
    ygap_test_value = 0.2345
    fake_fgs_composite.s4_slit_gaps.xgap.user_readback.sim_put(xgap_test_value)
    fake_fgs_composite.s4_slit_gaps.ygap.user_readback.sim_put(ygap_test_value)

    flux_test_value = 10.0
    fake_fgs_composite.flux.flux_reading.sim_put(flux_test_value)

    test_ispyb_callback = FGSISPyBHandlerCallback(test_fgs_params)
    test_ispyb_callback.ispyb = MagicMock()
    RE.subscribe(test_ispyb_callback)

    def standalone_read_hardware_for_ispyb(und, syn, slits, attn, fl):
        yield from bps.open_run()
        yield from read_hardware_for_ispyb(und, syn, slits, attn, fl)
        yield from bps.close_run()

    RE(
        standalone_read_hardware_for_ispyb(
            fake_fgs_composite.undulator,
            fake_fgs_composite.synchrotron,
            fake_fgs_composite.s4_slit_gaps,
            fake_fgs_composite.attenuator,
            fake_fgs_composite.flux,
        )
    )
    params = test_ispyb_callback.params

    assert params.artemis_params.ispyb_params.undulator_gap == undulator_test_value
    assert params.artemis_params.ispyb_params.synchrotron_mode == synchrotron_test_value
    assert params.artemis_params.ispyb_params.slit_gap_size_x == xgap_test_value
    assert params.artemis_params.ispyb_params.slit_gap_size_y == ygap_test_value
    assert params.artemis_params.ispyb_params.transmission == transmission_test_value
    assert params.artemis_params.ispyb_params.flux == flux_test_value


@patch(
    "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range"
)
@patch("artemis.experiment_plans.fast_grid_scan_plan.run_gridscan")
@patch("artemis.experiment_plans.fast_grid_scan_plan.move_xyz")
def test_results_adjusted_and_passed_to_move_xyz(
    move_xyz: MagicMock,
    run_gridscan: MagicMock,
    move_aperture: MagicMock,
    fake_fgs_composite: FGSComposite,
    mock_subscriptions: FGSCallbackCollection,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    set_up_logging_handlers(logging_level="INFO", dev_mode=True)
    RE.subscribe(VerbosePlanExecutionLoggingCallback())

    mock_subscriptions.zocalo_handler.zocalo_interactor.wait_for_result.return_value = (
        TEST_RESULT_LARGE
    )
    RE(
        run_gridscan_and_move(
            fake_fgs_composite,
            test_fgs_params,
            mock_subscriptions,
        )
    )
    mock_subscriptions.zocalo_handler.zocalo_interactor.wait_for_result.return_value = (
        TEST_RESULT_MEDIUM
    )
    RE(
        run_gridscan_and_move(
            fake_fgs_composite,
            test_fgs_params,
            mock_subscriptions,
        )
    )
    mock_subscriptions.zocalo_handler.zocalo_interactor.wait_for_result.return_value = (
        TEST_RESULT_SMALL
    )
    RE(
        run_gridscan_and_move(
            fake_fgs_composite,
            test_fgs_params,
            mock_subscriptions,
        )
    )

    call_large = call(
        *(fake_fgs_composite.aperture_scatterguard.aperture_positions.LARGE)
    )
    call_medium = call(
        *(fake_fgs_composite.aperture_scatterguard.aperture_positions.MEDIUM)
    )

    move_aperture.assert_has_calls(
        [call_large, call_large, call_medium], any_order=True
    )


@patch("bluesky.plan_stubs.mv")
def test_results_passed_to_move_motors(
    bps_mv: MagicMock,
    test_fgs_params: FGSInternalParameters,
    fake_fgs_composite: FGSComposite,
    RE: RunEngine,
):
    from artemis.experiment_plans.fast_grid_scan_plan import move_xyz

    set_up_logging_handlers(logging_level="INFO", dev_mode=True)
    RE.subscribe(VerbosePlanExecutionLoggingCallback())
    motor_position = test_fgs_params.experiment_params.grid_position_to_motor_position(
        np.array([1, 2, 3])
    )
    RE(move_xyz(fake_fgs_composite.sample_motors, motor_position))
    bps_mv.assert_called_once_with(
        ANY, motor_position[0], ANY, motor_position[1], ANY, motor_position[2]
    )


@patch(
    "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range"
)
@patch("artemis.experiment_plans.fast_grid_scan_plan.run_gridscan.do_fgs")
@patch("artemis.experiment_plans.fast_grid_scan_plan.run_gridscan")
@patch("artemis.experiment_plans.fast_grid_scan_plan.move_xyz")
@patch("bluesky.plan_stubs.rd")
def test_individual_plans_triggered_once_and_only_once_in_composite_run(
    rd: MagicMock,
    move_xyz: MagicMock,
    run_gridscan: MagicMock,
    do_fgs: MagicMock,
    move_aperture: MagicMock,
    mock_subscriptions: FGSCallbackCollection,
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    set_up_logging_handlers(logging_level="INFO", dev_mode=True)
    RE.subscribe(VerbosePlanExecutionLoggingCallback())

    RE(
        run_gridscan_and_move(
            fake_fgs_composite,
            test_fgs_params,
            mock_subscriptions,
        )
    )

    run_gridscan.assert_called_once_with(fake_fgs_composite, test_fgs_params)
    array_arg = move_xyz.call_args.args[1]
    np.testing.assert_allclose(array_arg, np.array([0.05, 0.15, 0.25]))
    move_xyz.assert_called_once()


@patch(
    "dodal.devices.aperturescatterguard.ApertureScatterguard._safe_move_within_datacollection_range"
)
@patch("artemis.experiment_plans.fast_grid_scan_plan.run_gridscan.do_fgs")
@patch("artemis.experiment_plans.fast_grid_scan_plan.run_gridscan")
@patch("artemis.experiment_plans.fast_grid_scan_plan.move_xyz")
@patch("bluesky.plan_stubs.rd")
def test_logging_within_plan(
    rd: MagicMock,
    move_xyz: MagicMock,
    run_gridscan: MagicMock,
    do_fgs: MagicMock,
    move_aperture: MagicMock,
    mock_subscriptions: FGSCallbackCollection,
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    set_up_logging_handlers(logging_level="INFO", dev_mode=True)
    RE.subscribe(VerbosePlanExecutionLoggingCallback())

    RE(
        run_gridscan_and_move(
            fake_fgs_composite,
            test_fgs_params,
            mock_subscriptions,
        )
    )

    run_gridscan.assert_called_once_with(fake_fgs_composite, test_fgs_params)
    array_arg = move_xyz.call_args.args[1]
    np.testing.assert_array_almost_equal(array_arg, np.array([0.05, 0.15, 0.25]))
    move_xyz.assert_called_once()


@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.sleep")
def test_GIVEN_scan_already_valid_THEN_wait_for_FGS_returns_immediately(
    patch_sleep: MagicMock, RE: RunEngine
):
    test_fgs: FastGridScan = make_fake_device(FastGridScan)("prefix", name="fake_fgs")

    test_fgs.scan_invalid.sim_put(False)
    test_fgs.position_counter.sim_put(0)

    RE(wait_for_fgs_valid(test_fgs))

    patch_sleep.assert_not_called()


@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.sleep")
def test_GIVEN_scan_not_valid_THEN_wait_for_FGS_raises_and_sleeps_called(
    patch_sleep: MagicMock, RE: RunEngine
):
    test_fgs: FastGridScan = make_fake_device(FastGridScan)("prefix", name="fake_fgs")

    test_fgs.scan_invalid.sim_put(True)
    test_fgs.position_counter.sim_put(0)
    with pytest.raises(WarningException):
        RE(wait_for_fgs_valid(test_fgs))

    patch_sleep.assert_called()


@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.abs_set")
@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.kickoff")
@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.complete")
@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.mv")
@patch("artemis.experiment_plans.fast_grid_scan_plan.wait_for_fgs_valid")
@patch("artemis.external_interaction.nexus.write_nexus.NexusWriter")
def test_when_grid_scan_ran_then_eiger_disarmed_before_zocalo_end(
    nexuswriter,
    wait_for_valid,
    mock_mv,
    mock_complete,
    mock_kickoff,
    mock_abs_set,
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    mock_subscriptions: FGSCallbackCollection,
    RE: RunEngine,
):
    # Put both mocks in a parent to easily capture order
    mock_parent = MagicMock()
    fake_fgs_composite.eiger.disarm_detector = mock_parent.disarm

    fake_fgs_composite.eiger.filewriters_finished = Status()
    fake_fgs_composite.eiger.filewriters_finished.set_finished()
    fake_fgs_composite.eiger.odin.check_odin_state = MagicMock(return_value=True)
    fake_fgs_composite.eiger.odin.file_writer.num_captured.sim_put(1200)
    fake_fgs_composite.eiger.stage = MagicMock(
        return_value=Status(None, None, 0, True, True)
    )

    mock_subscriptions.zocalo_handler.zocalo_interactor.run_end = mock_parent.run_end
    with patch(
        "artemis.experiment_plans.fast_grid_scan_plan.fast_grid_scan_composite",
        fake_fgs_composite,
    ), patch(
        "artemis.experiment_plans.fast_grid_scan_plan.FGSCallbackCollection.from_params",
        lambda _: mock_subscriptions,
    ), patch(
        "artemis.external_interaction.callbacks.fgs.nexus_callback.NexusWriter.create_nexus_file"
    ), patch(
        "artemis.external_interaction.callbacks.fgs.nexus_callback.NexusWriter.update_nexus_file_timestamp"
    ):
        RE(get_plan(test_fgs_params))

    mock_parent.assert_has_calls([call.disarm(), call.run_end(0), call.run_end(0)])


@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.wait")
@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.complete")
def test_fgs_arms_eiger_without_grid_detect(
    mock_complete,
    mock_wait,
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    fake_fgs_composite.eiger.stage = MagicMock()
    fake_fgs_composite.eiger.unstage = MagicMock()

    RE(run_gridscan(fake_fgs_composite, test_fgs_params))
    fake_fgs_composite.eiger.stage.assert_called_once()
    fake_fgs_composite.eiger.unstage.assert_called_once()


@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.wait")
@patch("artemis.experiment_plans.fast_grid_scan_plan.bps.complete")
def test_when_grid_scan_fails_then_detector_disarmed_and_correct_exception_returned(
    mock_complete,
    mock_wait,
    fake_fgs_composite: FGSComposite,
    test_fgs_params: FGSInternalParameters,
    RE: RunEngine,
):
    class CompleteException(Exception):
        pass

    mock_complete.side_effect = CompleteException()

    fake_fgs_composite.eiger.stage = MagicMock(
        return_value=Status(None, None, 0, True, True)
    )

    fake_fgs_composite.eiger.odin.check_odin_state = MagicMock()

    fake_fgs_composite.eiger.disarm_detector = MagicMock()
    fake_fgs_composite.eiger.disable_roi_mode = MagicMock()

    # Without the complete finishing we will not get all the images
    fake_fgs_composite.eiger.ALL_FRAMES_TIMEOUT = 0.1

    # Want to get the underlying completion error, not the one raised from unstage
    with pytest.raises(CompleteException):
        RE(run_gridscan(fake_fgs_composite, test_fgs_params))

    fake_fgs_composite.eiger.disable_roi_mode.assert_called()
    fake_fgs_composite.eiger.disarm_detector.assert_called()
