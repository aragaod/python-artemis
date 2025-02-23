import re
from copy import deepcopy
from unittest.mock import MagicMock, Mock, mock_open, patch

import numpy as np
import pytest
from ispyb.sp.mxacquisition import MXAcquisition
from mockito import mock, when

from artemis.external_interaction.ispyb.store_in_ispyb import (
    Store2DGridscanInIspyb,
    Store3DGridscanInIspyb,
    StoreRotationInIspyb,
)
from artemis.parameters.constants import SIM_ISPYB_CONFIG
from artemis.parameters.external_parameters import from_file as default_raw_params
from artemis.parameters.plan_specific.fgs_internal_params import FGSInternalParameters
from artemis.parameters.plan_specific.rotation_scan_internal_params import (
    RotationInternalParameters,
)

TEST_DATA_COLLECTION_IDS = [12, 13]
TEST_DATA_COLLECTION_GROUP_ID = 34
TEST_GRID_INFO_ID = 56
TEST_POSITION_ID = 78
TEST_SESSION_ID = 90

TIME_FORMAT_REGEX = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"

EMPTY_DATA_COLLECTION_PARAMS = {
    "id": None,
    "parentid": None,
    "visitid": None,
    "sampleid": None,
    "detectorid": None,
    "positionid": None,
    "apertureid": None,
    "datacollectionnumber": None,
    "starttime": None,
    "endtime": None,
    "runstatus": None,
    "axisstart": None,
    "axisend": None,
    "axisrange": None,
    "overlap": None,
    "nimages": None,
    "startimagenumber": None,
    "npasses": None,
    "exptime": None,
    "imgdir": None,
    "imgprefix": None,
    "imgsuffix": None,
    "imgcontainersubpath": None,
    "filetemplate": None,
    "wavelength": None,
    "resolution": None,
    "detectordistance": None,
    "xbeam": None,
    "ybeam": None,
    "comments": None,
    "slitgapvertical": None,
    "slitgaphorizontal": None,
    "transmission_fraction": None,
    "synchrotronmode": None,
    "xtalsnapshot1": None,
    "xtalsnapshot2": None,
    "xtalsnapshot3": None,
    "xtalsnapshot4": None,
    "rotationaxis": None,
    "phistart": None,
    "kappastart": None,
    "omegastart": None,
    "resolutionatcorner": None,
    "detector2theta": None,
    "undulatorgap1": None,
    "undulatorgap2": None,
    "undulatorgap3": None,
    "beamsizeatsamplex": None,
    "beamsizeatsampley": None,
    "avgtemperature": None,
    "actualcenteringposition": None,
    "beamshape": None,
    "focalspotsizeatsamplex": None,
    "focalspotsizeatsampley": None,
    "polarisation": None,
    "flux": None,
    "processeddatafile": None,
    "datfile": None,
    "magnification": None,
    "totalabsorbeddose": None,
    "binning": None,
    "particlediameter": None,
    "boxsizectf": None,
    "minresolution": None,
    "mindefocus": None,
    "maxdefocus": None,
    "defocusstepsize": None,
    "amountastigmatism": None,
    "extractsize": None,
    "bgradius": None,
    "voltage": None,
    "objaperture": None,
    "c1aperture": None,
    "c2aperture": None,
    "c3aperture": None,
    "c1lens": None,
    "c2lens": None,
    "c3lens": None,
}


@pytest.fixture
def dummy_params():
    dummy_params = FGSInternalParameters(**default_raw_params())
    dummy_params.artemis_params.ispyb_params.upper_left = np.array([100, 100, 50])
    dummy_params.artemis_params.ispyb_params.microns_per_pixel_x = 0.8
    dummy_params.artemis_params.ispyb_params.microns_per_pixel_y = 0.8
    return dummy_params


@pytest.fixture
def dummy_rotation_params():
    dummy_params = RotationInternalParameters(
        **default_raw_params(
            "src/artemis/parameters/tests/test_data/good_test_rotation_scan_parameters.json"
        )
    )
    return dummy_params


@pytest.fixture
def dummy_ispyb(dummy_params):
    store_in_ispyb_2d = Store2DGridscanInIspyb(SIM_ISPYB_CONFIG, dummy_params)
    return store_in_ispyb_2d


@pytest.fixture
def dummy_rotation_ispyb(dummy_rotation_params):
    store_in_ispyb = StoreRotationInIspyb(SIM_ISPYB_CONFIG, dummy_rotation_params)
    return store_in_ispyb


@pytest.fixture
def dummy_ispyb_3d(dummy_params):
    store_in_ispyb_3d = Store3DGridscanInIspyb(SIM_ISPYB_CONFIG, dummy_params)
    return store_in_ispyb_3d


def test_get_current_time_string(dummy_ispyb):
    current_time = dummy_ispyb.get_current_time_string()

    assert isinstance(current_time, str)
    assert re.match(TIME_FORMAT_REGEX, current_time) is not None


@pytest.mark.parametrize(
    "visit_path, expected_match",
    [
        ("/dls/i03/data/2022/cm6477-45/", "cm6477-45"),
        ("/dls/i03/data/2022/cm6477-45", "cm6477-45"),
        ("/dls/i03/data/2022/mx54663-1/", "mx54663-1"),
        ("/dls/i03/data/2022/mx54663-1", "mx54663-1"),
        ("/dls/i03/data/2022/mx53-1/", None),
        ("/dls/i03/data/2022/mx53-1", None),
        ("/dls/i03/data/2022/mx5563-1565/", None),
        ("/dls/i03/data/2022/mx5563-1565", None),
    ],
)
def test_regex_string(dummy_ispyb, visit_path: str, expected_match: str):
    test_visit_path = dummy_ispyb.get_visit_string_from_path(visit_path)
    assert test_visit_path == expected_match


@patch("ispyb.open", new_callable=mock_open)
def test_mutate_params(
    ispyb_conn,
    dummy_rotation_ispyb: StoreRotationInIspyb,
    dummy_ispyb_3d: Store3DGridscanInIspyb,
    dummy_params: FGSInternalParameters,
    dummy_rotation_params: RotationInternalParameters,
):
    rotation_dict = deepcopy(EMPTY_DATA_COLLECTION_PARAMS)
    fgs_dict = deepcopy(EMPTY_DATA_COLLECTION_PARAMS)

    dummy_ispyb_3d.y_steps = 5

    rotation_transformed = (
        dummy_rotation_ispyb._mutate_data_collection_params_for_experiment(
            rotation_dict
        )
    )
    assert rotation_transformed["axis_range"] == 180.0
    assert rotation_transformed["axis_end"] == 180.0
    assert rotation_transformed["n_images"] == 1800

    fgs_transformed = dummy_ispyb_3d._mutate_data_collection_params_for_experiment(
        fgs_dict
    )
    assert fgs_transformed["axis_range"] == 0
    assert fgs_transformed["n_images"] == 200


@patch("ispyb.open", new_callable=mock_open)
def test_store_rotation_scan(
    ispyb_conn, dummy_rotation_ispyb: StoreRotationInIspyb, dummy_rotation_params
):
    ispyb_conn.return_value.mx_acquisition = mock()
    ispyb_conn.return_value.core = mock()

    when(dummy_rotation_ispyb)._store_position_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[0]
    ).thenReturn(TEST_POSITION_ID)

    when(dummy_rotation_ispyb)._store_data_collection_group_table(
        ispyb_conn()
    ).thenReturn(TEST_DATA_COLLECTION_GROUP_ID)

    when(dummy_rotation_ispyb)._store_data_collection_table(
        ispyb_conn(), TEST_DATA_COLLECTION_GROUP_ID
    ).thenReturn(TEST_DATA_COLLECTION_IDS[0])

    assert dummy_rotation_ispyb.experiment_type == "SAD"

    assert dummy_rotation_ispyb._store_scan_data(ispyb_conn()) == (
        TEST_DATA_COLLECTION_IDS[0],
        TEST_DATA_COLLECTION_GROUP_ID,
    )

    assert dummy_rotation_ispyb.begin_deposition() == (
        TEST_DATA_COLLECTION_IDS[0],
        TEST_DATA_COLLECTION_GROUP_ID,
    )


@patch("ispyb.open", new_callable=mock_open)
def test_store_rotation_scan_failures(
    ispyb_conn,
    dummy_rotation_ispyb: StoreRotationInIspyb,
    dummy_rotation_params: RotationInternalParameters,
):
    ispyb_conn.return_value.mx_acquisition = mock()
    ispyb_conn.return_value.core = mock()

    dummy_rotation_ispyb.data_collection_id = None

    with pytest.raises(AssertionError):
        dummy_rotation_ispyb.end_deposition("", "")

    with patch("artemis.log.LOGGER.warning", autospec=True) as warning:
        dummy_rotation_params.artemis_params.ispyb_params.xtal_snapshots_omega_start = (
            None
        )
        ispyb_no_snapshots = StoreRotationInIspyb(  # noqa
            SIM_ISPYB_CONFIG, dummy_rotation_params
        )
        warning.assert_called_once_with("No xtal snapshot paths sent to ISPyB!")


@patch("ispyb.open", new_callable=mock_open)
def test_store_grid_scan(ispyb_conn, dummy_ispyb, dummy_params):
    ispyb_conn.return_value.mx_acquisition = mock()
    ispyb_conn.return_value.core = mock()

    when(dummy_ispyb)._store_position_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[0]
    ).thenReturn(TEST_POSITION_ID)
    when(dummy_ispyb)._store_data_collection_group_table(ispyb_conn()).thenReturn(
        TEST_DATA_COLLECTION_GROUP_ID
    )
    when(dummy_ispyb)._store_data_collection_table(
        ispyb_conn(), TEST_DATA_COLLECTION_GROUP_ID
    ).thenReturn(TEST_DATA_COLLECTION_IDS[0])
    when(dummy_ispyb)._store_grid_info_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[0]
    ).thenReturn(TEST_GRID_INFO_ID)

    assert dummy_ispyb.experiment_type == "mesh"

    assert dummy_ispyb.store_grid_scan(dummy_params) == (
        [TEST_DATA_COLLECTION_IDS[0]],
        [TEST_GRID_INFO_ID],
        TEST_DATA_COLLECTION_GROUP_ID,
    )


@patch("ispyb.open", new_callable=mock_open)
def test_store_3d_grid_scan(
    ispyb_conn,
    dummy_ispyb_3d: Store3DGridscanInIspyb,
    dummy_params: FGSInternalParameters,
):
    ispyb_conn.return_value.mx_acquisition = mock()
    ispyb_conn.return_value.core = mock()

    when(dummy_ispyb_3d)._store_position_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[0]
    ).thenReturn(TEST_POSITION_ID)
    when(dummy_ispyb_3d)._store_position_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[1]
    ).thenReturn(TEST_POSITION_ID)
    when(dummy_ispyb_3d)._store_data_collection_group_table(ispyb_conn()).thenReturn(
        TEST_DATA_COLLECTION_GROUP_ID
    )

    when(dummy_ispyb_3d)._store_grid_info_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[0]
    ).thenReturn(TEST_GRID_INFO_ID)
    when(dummy_ispyb_3d)._store_grid_info_table(
        ispyb_conn(), TEST_DATA_COLLECTION_IDS[1]
    ).thenReturn(TEST_GRID_INFO_ID)

    dummy_ispyb_3d._store_data_collection_table = Mock(
        side_effect=TEST_DATA_COLLECTION_IDS
    )

    x = 0
    y = 1
    z = 2

    dummy_params.artemis_params.ispyb_params.upper_left = np.array([x, y, z])
    dummy_params.experiment_params.z_step_size = 0.2

    assert dummy_ispyb_3d.experiment_type == "Mesh3D"

    assert dummy_ispyb_3d.store_grid_scan(dummy_params) == (
        TEST_DATA_COLLECTION_IDS,
        [TEST_GRID_INFO_ID, TEST_GRID_INFO_ID],
        TEST_DATA_COLLECTION_GROUP_ID,
    )

    assert (
        dummy_ispyb_3d.omega_start
        == dummy_params.artemis_params.detector_params.omega_start + 90
    )
    assert (
        dummy_ispyb_3d.run_number
        == dummy_params.artemis_params.detector_params.run_number + 1
    )
    assert (
        dummy_ispyb_3d.xtal_snapshots
        == dummy_params.artemis_params.ispyb_params.xtal_snapshots_omega_end
    )
    assert dummy_ispyb_3d.y_step_size == dummy_params.experiment_params.z_step_size
    assert dummy_ispyb_3d.y_steps == dummy_params.experiment_params.z_steps

    assert dummy_ispyb_3d.upper_left[0] == x
    assert dummy_ispyb_3d.upper_left[1] == z


def setup_mock_return_values(ispyb_conn):
    mx_acquisition = ispyb_conn.return_value.__enter__.return_value.mx_acquisition

    mx_acquisition.get_data_collection_group_params = (
        MXAcquisition.get_data_collection_group_params
    )
    mx_acquisition.get_data_collection_params = MXAcquisition.get_data_collection_params
    mx_acquisition.get_dc_grid_params = MXAcquisition.get_dc_grid_params
    mx_acquisition.get_dc_position_params = MXAcquisition.get_dc_position_params

    ispyb_conn.return_value.core.retrieve_visit_id.return_value = TEST_SESSION_ID
    mx_acquisition.upsert_data_collection.side_effect = TEST_DATA_COLLECTION_IDS * 2
    mx_acquisition.update_dc_position.return_value = TEST_POSITION_ID
    mx_acquisition.upsert_data_collection_group.return_value = (
        TEST_DATA_COLLECTION_GROUP_ID
    )
    mx_acquisition.upsert_dc_grid.return_value = TEST_GRID_INFO_ID


@patch("ispyb.open", autospec=True)
def test_param_keys(ispyb_conn, dummy_ispyb, dummy_params):
    setup_mock_return_values(ispyb_conn)

    assert dummy_ispyb.store_grid_scan(dummy_params) == (
        [TEST_DATA_COLLECTION_IDS[0]],
        [TEST_GRID_INFO_ID],
        TEST_DATA_COLLECTION_GROUP_ID,
    )


def _test_when_grid_scan_stored_then_data_present_in_upserts(
    ispyb_conn, dummy_ispyb, dummy_params, test_function, test_group=False
):
    setup_mock_return_values(ispyb_conn)

    dummy_ispyb.store_grid_scan(dummy_params)

    mx_acquisition = ispyb_conn.return_value.__enter__.return_value.mx_acquisition

    upsert_data_collection_arg_list = (
        mx_acquisition.upsert_data_collection.call_args_list[0][0]
    )
    actual = upsert_data_collection_arg_list[0]
    assert test_function(MXAcquisition.get_data_collection_params(), actual)

    if test_group:
        upsert_data_collection_group_arg_list = (
            mx_acquisition.upsert_data_collection_group.call_args_list[0][0]
        )
        actual = upsert_data_collection_group_arg_list[0]
        assert test_function(MXAcquisition.get_data_collection_group_params(), actual)


@patch("ispyb.open", autospec=True)
def test_given_sampleid_of_none_when_grid_scan_stored_then_sample_id_not_set(
    ispyb_conn, dummy_ispyb, dummy_params
):
    def test_sample_id(default_params, actual):
        sampleid_idx = list(default_params).index("sampleid")
        return actual[sampleid_idx] == default_params["sampleid"]

    _test_when_grid_scan_stored_then_data_present_in_upserts(
        ispyb_conn, dummy_ispyb, dummy_params, test_sample_id, True
    )


@patch("ispyb.open", autospec=True)
def test_given_real_sampleid_when_grid_scan_stored_then_sample_id_set(
    ispyb_conn, dummy_ispyb: Store2DGridscanInIspyb, dummy_params: FGSInternalParameters
):
    expected_sample_id = "0001"
    dummy_params.artemis_params.ispyb_params.sample_id = expected_sample_id

    def test_sample_id(default_params, actual):
        sampleid_idx = list(default_params).index("sampleid")
        return actual[sampleid_idx] == expected_sample_id

    _test_when_grid_scan_stored_then_data_present_in_upserts(
        ispyb_conn, dummy_ispyb, dummy_params, test_sample_id, True
    )


@patch("ispyb.open", autospec=True)
def test_fail_result_run_results_in_bad_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: Store2DGridscanInIspyb,
):
    setup_mock_return_values(mock_ispyb_conn)
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_aquisition.upsert_data_collection

    dummy_ispyb.begin_deposition()
    dummy_ispyb.end_deposition("fail", "test specifies failure")

    mock_upsert_data_collection_calls = mock_upsert_data_collection.call_args_list
    mock_upsert_data_collection_second_call_args = mock_upsert_data_collection_calls[1][
        0
    ]
    upserted_param_value_list = mock_upsert_data_collection_second_call_args[0]
    assert "DataCollection Unsuccessful" in upserted_param_value_list
    assert "DataCollection Successful" not in upserted_param_value_list


@patch("ispyb.open", autospec=True)
def test_no_exception_during_run_results_in_good_run_status(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: Store2DGridscanInIspyb,
):
    setup_mock_return_values(mock_ispyb_conn)
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_aquisition.upsert_data_collection
    dummy_ispyb.begin_deposition()
    dummy_ispyb.end_deposition("success", "")
    mock_upsert_data_collection_calls = mock_upsert_data_collection.call_args_list
    mock_upsert_data_collection_second_call_args = mock_upsert_data_collection_calls[1][
        0
    ]
    upserted_param_value_list = mock_upsert_data_collection_second_call_args[0]
    assert "DataCollection Unsuccessful" not in upserted_param_value_list
    assert "DataCollection Successful" in upserted_param_value_list


@patch("ispyb.open", autospec=True)
def test_ispyb_deposition_comment_correct(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: Store2DGridscanInIspyb,
):
    setup_mock_return_values(mock_ispyb_conn)
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_aquisition.upsert_data_collection
    dummy_ispyb.begin_deposition()
    mock_upsert_call_args = mock_upsert_data_collection.call_args_list[0][0]

    upserted_param_value_list = mock_upsert_call_args[0]
    assert upserted_param_value_list[29] == (
        "Artemis: Xray centring - Diffraction grid scan of 40 by 20 images "
        "in 100.0 um by 100.0 um steps. Top left (px): [100,100], bottom right (px): [3300,1700]."
    )


@patch("ispyb.open", autospec=True)
def test_ispyb_deposition_rounds_to_int(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb: Store2DGridscanInIspyb,
):
    setup_mock_return_values(mock_ispyb_conn)
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_data_collection = mock_mx_aquisition.upsert_data_collection
    dummy_ispyb.full_params.artemis_params.ispyb_params.upper_left = np.array(
        [0.01, 100, 50]
    )
    dummy_ispyb.begin_deposition()
    mock_upsert_call_args = mock_upsert_data_collection.call_args_list[0][0]

    upserted_param_value_list = mock_upsert_call_args[0]
    assert upserted_param_value_list[29] == (
        "Artemis: Xray centring - Diffraction grid scan of 40 by 20 images "
        "in 100.0 um by 100.0 um steps. Top left (px): [0,100], bottom right (px): [3200,1700]."
    )


@patch("ispyb.open", autospec=True)
def test_ispyb_deposition_comment_for_3D_correct(
    mock_ispyb_conn: MagicMock,
    dummy_ispyb_3d: Store3DGridscanInIspyb,
):
    setup_mock_return_values(mock_ispyb_conn)
    mock_mx_aquisition = (
        mock_ispyb_conn.return_value.__enter__.return_value.mx_acquisition
    )
    mock_upsert_dc = mock_mx_aquisition.upsert_data_collection
    dummy_ispyb_3d.begin_deposition()
    first_upserted_param_value_list = mock_upsert_dc.call_args_list[0][0][0]
    second_upserted_param_value_list = mock_upsert_dc.call_args_list[1][0][0]
    assert first_upserted_param_value_list[29] == (
        "Artemis: Xray centring - Diffraction grid scan of 40 by 20 images "
        "in 100.0 um by 100.0 um steps. Top left (px): [100,100], bottom right (px): [3300,1700]."
    )
    assert second_upserted_param_value_list[29] == (
        "Artemis: Xray centring - Diffraction grid scan of 40 by 10 images "
        "in 100.0 um by 100.0 um steps. Top left (px): [100,50], bottom right (px): [3300,850]."
    )


@patch("ispyb.open", autospec=True)
def test_given_x_and_y_steps_different_from_total_images_when_grid_scan_stored_then_num_images_correct(
    ispyb_conn, dummy_ispyb: Store2DGridscanInIspyb, dummy_params: FGSInternalParameters
):
    expected_number_of_steps = 200 * 3
    dummy_params.experiment_params.x_steps = 200
    dummy_params.experiment_params.y_steps = 3

    def test_number_of_steps(default_params, actual):
        # Note that internally the ispyb API removes underscores so this is the same as n_images
        number_of_steps_idx = list(default_params).index("nimages")
        return actual[number_of_steps_idx] == expected_number_of_steps

    _test_when_grid_scan_stored_then_data_present_in_upserts(
        ispyb_conn, dummy_ispyb, dummy_params, test_number_of_steps
    )
