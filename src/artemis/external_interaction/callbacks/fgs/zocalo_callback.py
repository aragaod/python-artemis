from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np
from bluesky.callbacks import CallbackBase
from numpy import ndarray

from artemis.external_interaction.callbacks.fgs.ispyb_callback import (
    FGSISPyBHandlerCallback,
)
from artemis.external_interaction.exceptions import ISPyBDepositionNotMade
from artemis.external_interaction.zocalo.zocalo_interaction import (
    NoDiffractionFound,
    ZocaloInteractor,
)
from artemis.log import LOGGER
from artemis.parameters.plan_specific.fgs_internal_params import FGSInternalParameters


class FGSZocaloCallback(CallbackBase):
    """Callback class to handle the triggering of Zocalo processing.
    Sends zocalo a run_start signal on recieving a start document for the 'do_fgs'
    sub-plan, and sends a run_end signal on recieving a stop document for the#
    'run_gridscan' sub-plan.

    Needs to be connected to an ISPyBHandlerCallback subscribed to the same run in order
    to have access to the deposition numbers to pass on to Zocalo.

    To use, subscribe the Bluesky RunEngine to an instance of this class.
    E.g.:
        nexus_file_handler_callback = NexusFileHandlerCallback(parameters)
        RE.subscribe(nexus_file_handler_callback)
    Or decorate a plan using bluesky.preprocessors.subs_decorator.

    See: https://blueskyproject.io/bluesky/callbacks.html#ways-to-invoke-callbacks

    Usually used as part of an FGSCallbackCollection.
    """

    def __init__(
        self, parameters: FGSInternalParameters, ispyb_handler: FGSISPyBHandlerCallback
    ):
        self.grid_position_to_motor_position: Callable[
            [ndarray], ndarray
        ] = parameters.experiment_params.grid_position_to_motor_position
        self.processing_start_time = 0.0
        self.processing_time = 0.0
        self.do_fgs_uid: Optional[str] = None
        self.ispyb: FGSISPyBHandlerCallback = ispyb_handler
        self.zocalo_interactor = ZocaloInteractor(
            parameters.artemis_params.zocalo_environment
        )

    def start(self, doc: dict):
        LOGGER.info("Zocalo handler received start document.")
        if doc.get("subplan_name") == "do_fgs":
            self.do_fgs_uid = doc.get("uid")
            if self.ispyb.ispyb_ids[0] is not None:
                datacollection_ids = self.ispyb.ispyb_ids[0]
                for id in datacollection_ids:
                    self.zocalo_interactor.run_start(id)
            else:
                raise ISPyBDepositionNotMade("ISPyB deposition was not initialised!")

    def stop(self, doc: dict):
        if doc.get("run_start") == self.do_fgs_uid:
            LOGGER.info(
                f"Zocalo handler received stop document, for run {doc.get('run_start')}."
            )
            if self.ispyb.ispyb_ids == (None, None, None):
                raise ISPyBDepositionNotMade("ISPyB deposition was not initialised!")
            datacollection_ids = self.ispyb.ispyb_ids[0]
            for id in datacollection_ids:
                self.zocalo_interactor.run_end(id)
            self.processing_start_time = time.time()

    def wait_for_results(self, fallback_xyz: ndarray) -> tuple[ndarray, Optional[list]]:
        """Blocks until a centre has been received from Zocalo

        Args:
            fallback_xyz (ndarray): The position to fallback to if no centre is found

        Returns:
            ndarray: The xray centre position to move to
        """
        datacollection_group_id = self.ispyb.ispyb_ids[2]

        try:
            raw_results = self.zocalo_interactor.wait_for_result(
                datacollection_group_id
            )

            # Sort from strongest to weakest in case of multiple crystals
            raw_results = sorted(
                raw_results, key=lambda d: d["total_count"], reverse=True
            )
            LOGGER.info(f"Zocalo: found {len(raw_results)} crystals.")
            crystal_summary = ""

            bboxes = []
            for n, res in enumerate(raw_results):
                bboxes.append(
                    np.array(res["bounding_box"][1]) - np.array(res["bounding_box"][0])
                )

                nicely_formatted_com = [
                    f"{np.round(com,2)}" for com in res["centre_of_mass"]
                ]
                crystal_summary += (
                    f"Crystal {n+1}: "
                    f"Strength {res['total_count']}; "
                    f"Position (grid boxes) {nicely_formatted_com}; "
                    f"Size (grid boxes) {bboxes[n]};"
                )
            self.ispyb.append_to_comment(crystal_summary)

            raw_centre = np.array([*(raw_results[0]["centre_of_mass"])])
            adjusted_centre = raw_centre - np.array([0.5, 0.5, 0.5])

            # _wait_for_result returns the centre of the grid box, but we want the corner
            xray_centre = self.grid_position_to_motor_position(adjusted_centre)

            bbox_size: list[int] | None = bboxes[0]

            LOGGER.info(
                f"Results recieved from zocalo: {xray_centre}, bounding box size: {bbox_size}"
            )

        except NoDiffractionFound:
            # We move back to the centre if results aren't found
            log_msg = (
                f"Zocalo: No diffraction found, using fallback centre {fallback_xyz}"
            )
            self.ispyb.append_to_comment("Found no diffraction.")
            xray_centre = fallback_xyz
            bbox_size = None
            LOGGER.warning(log_msg)

        self.processing_time = time.time() - self.processing_start_time
        self.ispyb.append_to_comment(
            f"Zocalo processing took {self.processing_time:.2f} s"
        )
        LOGGER.info(f"Zocalo processing took {self.processing_time}s")
        return xray_centre, bbox_size
