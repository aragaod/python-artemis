import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import bluesky.plan_stubs as bps
import bluesky.preprocessors as bpp
import h5py
import numpy as np
import pytest
from bluesky.run_engine import RunEngine

from artemis.external_interaction.callbacks.rotation.rotation_callback_collection import (
    RotationCallbackCollection,
)
from artemis.parameters.external_parameters import from_file
from artemis.parameters.plan_specific.rotation_scan_internal_params import (
    RotationInternalParameters,
)

TEST_EXAMPLE_NEXUS_FILE = Path("ins_8_5.nxs")
TEST_DIRECTORY = Path("src/artemis/external_interaction/unit_tests/test_data/")
TEST_FILENAME = "rotation_scan_test_nexus"


@pytest.fixture
def test_params():
    param_dict = from_file(
        "src/artemis/parameters/tests/test_data/good_test_rotation_scan_parameters.json"
    )
    param_dict["artemis_params"]["detector_params"][
        "directory"
    ] = "src/artemis/external_interaction/unit_tests/test_data"
    param_dict["artemis_params"]["detector_params"]["prefix"] = TEST_FILENAME
    param_dict["experiment_params"]["rotation_angle"] = 360.0
    params = RotationInternalParameters(**param_dict)
    params.experiment_params.x = 0
    params.experiment_params.y = 0
    params.experiment_params.z = 0
    params.artemis_params.detector_params.exposure_time = 0.004
    params.artemis_params.detector_params.current_energy_ev = 12700
    params.artemis_params.ispyb_params.transmission_fraction = 0.49118047952
    params.artemis_params.ispyb_params.wavelength = 0.9762535433
    return params


def fake_get_plan(
    parameters: RotationInternalParameters, subscriptions: RotationCallbackCollection
):
    @bpp.subs_decorator(list(subscriptions))
    @bpp.set_run_key_decorator("rotation_scan_with_cleanup_and_subs")
    @bpp.run_decorator(  # attach experiment metadata to the start document
        md={
            "subplan_name": "rotation_scan_with_cleanup",
            "hyperion_internal_parameters": parameters.json(),
        }
    )
    def plan():
        yield from bps.sleep(0)

    return plan()


@patch(
    "artemis.external_interaction.callbacks.rotation.rotation_callback_collection.RotationZocaloHandlerCallback",
    autospec=True,
)
def test_rotation_scan_nexus_output_compared_to_existing_file(
    zocalo,
    test_params: RotationInternalParameters,
):
    run_number = test_params.artemis_params.detector_params.run_number
    nexus_filename = str(TEST_DIRECTORY / (TEST_FILENAME + f"_{run_number}.nxs"))
    master_filename = str(TEST_DIRECTORY / (TEST_FILENAME + f"_{run_number}_master.h5"))

    if os.path.isfile(nexus_filename):
        os.remove(nexus_filename)
    if os.path.isfile(master_filename):
        os.remove(master_filename)

    RE = RunEngine({})

    cb = RotationCallbackCollection.from_params(test_params)
    cb.ispyb_handler.start = MagicMock()
    cb.ispyb_handler.stop = MagicMock()
    cb.ispyb_handler.event = MagicMock()
    with patch(
        "artemis.external_interaction.nexus.write_nexus.get_current_time",
        return_value="test_time",
    ):
        RE(fake_get_plan(test_params, cb))

    assert os.path.isfile(nexus_filename)
    assert os.path.isfile(master_filename)

    with (
        h5py.File(str(TEST_DIRECTORY / TEST_EXAMPLE_NEXUS_FILE), "r") as example_nexus,
        h5py.File(nexus_filename, "r") as hyperion_nexus,
    ):
        assert hyperion_nexus["/entry/start_time"][()] == b"test_timeZ"
        assert hyperion_nexus["/entry/end_time"][()] == b"test_time"

        # we used to write the positions wrong...
        hyperion_omega: np.ndarray = np.array(
            hyperion_nexus["/entry/data/omega"][:]
        ) * (3599 / 3600)
        example_omega: np.ndarray = example_nexus["/entry/data/omega"][:]
        assert np.allclose(hyperion_omega, example_omega)

        hyperion_data_shape = hyperion_nexus["/entry/data/data"].shape
        example_data_shape = example_nexus["/entry/data/data"].shape

        assert hyperion_data_shape == example_data_shape

        hyperion_instrument = hyperion_nexus["/entry/instrument"]
        example_instrument = example_nexus["/entry/instrument"]
        transmission = "attenuator/attenuator_transmission"
        wavelength = "beam/incident_wavelength"
        assert np.isclose(
            hyperion_instrument[transmission][()],
            example_instrument[transmission][()],
        )
        assert np.isclose(
            hyperion_instrument[wavelength][()],
            example_instrument[wavelength][()],
        )

        hyperion_sam_x = hyperion_nexus["/entry/sample/sample_x/sam_x"]
        example_sam_x = example_nexus["/entry/sample/sample_x/sam_x"]
        hyperion_sam_y = hyperion_nexus["/entry/sample/sample_y/sam_y"]
        example_sam_y = example_nexus["/entry/sample/sample_y/sam_y"]
        hyperion_sam_z = hyperion_nexus["/entry/sample/sample_z/sam_z"]
        example_sam_z = example_nexus["/entry/sample/sample_z/sam_z"]

        hyperion_sam_phi = hyperion_nexus["/entry/sample/sample_phi/phi"]
        example_sam_phi = example_nexus["/entry/sample/sample_phi/phi"]
        hyperion_sam_chi = hyperion_nexus["/entry/sample/sample_chi/chi"]
        example_sam_chi = example_nexus["/entry/sample/sample_chi/chi"]

        hyperion_sam_omega = hyperion_nexus["/entry/sample/sample_omega/omega"]
        example_sam_omega = example_nexus["/entry/sample/sample_omega/omega"]

        assert np.isclose(
            hyperion_sam_x[()],
            example_sam_x[()],
        )
        assert np.isclose(
            hyperion_sam_y[()],
            example_sam_y[()],
        )
        assert np.isclose(
            hyperion_sam_z[()],
            example_sam_z[()],
        )

        assert hyperion_sam_x.attrs.get("depends_on") == example_sam_x.attrs.get(
            "depends_on"
        )
        assert hyperion_sam_y.attrs.get("depends_on") == example_sam_y.attrs.get(
            "depends_on"
        )
        assert hyperion_sam_z.attrs.get("depends_on") == example_sam_z.attrs.get(
            "depends_on"
        )
        assert hyperion_sam_phi.attrs.get("depends_on") == example_sam_phi.attrs.get(
            "depends_on"
        )
        assert hyperion_sam_chi.attrs.get("depends_on") == example_sam_chi.attrs.get(
            "depends_on"
        )
        assert hyperion_sam_omega.attrs.get(
            "depends_on"
        ) == example_sam_omega.attrs.get("depends_on")

    os.remove(nexus_filename)
    os.remove(master_filename)
