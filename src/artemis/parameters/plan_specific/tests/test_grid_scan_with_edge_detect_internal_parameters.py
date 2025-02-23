import numpy as np
from dodal.devices.det_dim_constants import EIGER2_X_16M_SIZE

from artemis.parameters import external_parameters
from artemis.parameters.plan_specific.grid_scan_with_edge_detect_params import (
    GridScanWithEdgeDetectInternalParameters,
    GridScanWithEdgeDetectParams,
)


def test_grid_scan_with_edge_detect_parameters_load_from_file():
    params = external_parameters.from_file(
        "src/artemis/parameters/tests/test_data/good_test_grid_with_edge_detect_parameters.json"
    )
    internal_parameters = GridScanWithEdgeDetectInternalParameters(**params)

    assert isinstance(
        internal_parameters.experiment_params, GridScanWithEdgeDetectParams
    )

    ispyb_params = internal_parameters.artemis_params.ispyb_params

    np.testing.assert_array_equal(ispyb_params.position, np.array([10, 20, 30]))
    np.testing.assert_array_equal(ispyb_params.upper_left, np.array([0, 0, 0]))

    detector_params = internal_parameters.artemis_params.detector_params

    assert detector_params.detector_size_constants == EIGER2_X_16M_SIZE
    assert detector_params.num_triggers == 0
    assert detector_params.num_images_per_trigger == 1
