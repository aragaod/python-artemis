import argparse
import atexit
import threading
from dataclasses import asdict
from queue import Queue
from traceback import format_exception
from typing import Callable, Optional, Tuple

from bluesky import RunEngine
from flask import Flask, request
from flask_restful import Api, Resource
from pydantic.dataclasses import dataclass

import artemis.log
from artemis.exceptions import WarningException
from artemis.experiment_plans.experiment_registry import PLAN_REGISTRY, PlanNotFound
from artemis.external_interaction.callbacks.aperture_change_callback import (
    ApertureChangeCallback,
)
from artemis.external_interaction.callbacks.logging_callback import (
    VerbosePlanExecutionLoggingCallback,
)
from artemis.parameters.constants import Actions, Status
from artemis.parameters.internal_parameters import InternalParameters
from artemis.tracing import TRACER

VERBOSE_EVENT_LOGGING: Optional[bool] = None


@dataclass
class Command:
    action: Actions
    experiment: Optional[Callable] = None
    parameters: Optional[InternalParameters] = None


@dataclass
class StatusAndMessage:
    status: str
    message: str = ""

    def __init__(self, status: Status, message: str = "") -> None:
        self.status = status.value
        self.message = message


@dataclass
class ErrorStatusAndMessage(StatusAndMessage):
    exception_type: str = ""

    def __init__(self, exception: Exception) -> None:
        super().__init__(Status.FAILED, repr(exception))
        self.exception_type = type(exception).__name__


class BlueskyRunner:
    command_queue: "Queue[Command]" = Queue()
    current_status: StatusAndMessage = StatusAndMessage(Status.IDLE)
    last_run_aborted: bool = False
    aperture_change_callback = ApertureChangeCallback()
    RE: RunEngine
    skip_startup_connection: bool

    def __init__(self, RE: RunEngine, skip_startup_connection=False) -> None:
        self.RE = RE
        self.skip_startup_connection = skip_startup_connection
        if VERBOSE_EVENT_LOGGING:
            RE.subscribe(VerbosePlanExecutionLoggingCallback())
        RE.subscribe(self.aperture_change_callback)

        if not self.skip_startup_connection:
            for plan_name in PLAN_REGISTRY:
                PLAN_REGISTRY[plan_name]["setup"]()

    def start(
        self, experiment: Callable, parameters: InternalParameters, plan_name: str
    ) -> StatusAndMessage:
        artemis.log.LOGGER.info(f"Started with parameters: {parameters}")

        if self.skip_startup_connection:
            PLAN_REGISTRY[plan_name]["setup"]()

        if (
            self.current_status.status == Status.BUSY.value
            or self.current_status.status == Status.ABORTING.value
        ):
            return StatusAndMessage(Status.FAILED, "Bluesky already running")
        else:
            self.current_status = StatusAndMessage(Status.BUSY)
            self.command_queue.put(Command(Actions.START, experiment, parameters))
            return StatusAndMessage(Status.SUCCESS)

    def stopping_thread(self):
        try:
            self.RE.abort()
            self.current_status = StatusAndMessage(Status.IDLE)
        except Exception as e:
            self.current_status = ErrorStatusAndMessage(e)

    def stop(self) -> StatusAndMessage:
        if self.current_status.status == Status.IDLE.value:
            return StatusAndMessage(Status.FAILED, "Bluesky not running")
        elif self.current_status.status == Status.ABORTING.value:
            return StatusAndMessage(Status.FAILED, "Bluesky already stopping")
        else:
            self.current_status = StatusAndMessage(Status.ABORTING)
            stopping_thread = threading.Thread(target=self.stopping_thread)
            stopping_thread.start()
            self.last_run_aborted = True
            return StatusAndMessage(Status.ABORTING)

    def shutdown(self):
        """Stops the run engine and the loop waiting for messages."""
        print("Shutting down: Stopping the run engine gracefully")
        self.stop()
        self.command_queue.put(Command(Actions.SHUTDOWN))

    def wait_on_queue(self):
        while True:
            command = self.command_queue.get()
            if command.action == Actions.SHUTDOWN:
                return
            elif command.action == Actions.START:
                try:
                    with TRACER.start_span("do_run"):
                        self.RE(command.experiment(command.parameters))

                    self.current_status = StatusAndMessage(
                        Status.IDLE,
                        self.aperture_change_callback.last_selected_aperture,
                    )

                    self.last_run_aborted = False
                except WarningException as exception:
                    artemis.log.LOGGER.warning("Warning Exception", exc_info=True)
                    self.current_status = ErrorStatusAndMessage(exception)
                except Exception as exception:
                    artemis.log.LOGGER.error("Exception on running plan", exc_info=True)

                    if self.last_run_aborted:
                        # Aborting will cause an exception here that we want to swallow
                        self.last_run_aborted = False
                    else:
                        self.current_status = ErrorStatusAndMessage(exception)


class RunExperiment(Resource):
    def __init__(self, runner: BlueskyRunner) -> None:
        super().__init__()
        self.runner: BlueskyRunner = runner

    def put(self, plan_name: str, action: Actions):
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.START.value:
            try:
                experiment_registry_entry = PLAN_REGISTRY.get(plan_name)
                if experiment_registry_entry is None:
                    raise PlanNotFound(
                        f"Experiment plan '{plan_name}' not found in registry."
                    )

                experiment_internal_param_type: InternalParameters = (
                    experiment_registry_entry.get("internal_param_type")
                )
                experiment = experiment_registry_entry.get("run")
                if experiment_internal_param_type is None:
                    raise PlanNotFound(
                        f"Corresponding internal param type for '{plan_name}' not found in registry."
                    )
                if experiment is None:
                    raise PlanNotFound(
                        f"Experiment plan '{plan_name}' has no 'run' method."
                    )

                parameters = experiment_internal_param_type.from_json(request.data)
                if plan_name != parameters.artemis_params.experiment_type:
                    raise PlanNotFound(
                        f"Wrong experiment parameters ({parameters.artemis_params.experiment_type}) "
                        f"for plan endpoint {plan_name}."
                    )
                status_and_message = self.runner.start(
                    experiment, parameters, plan_name
                )
            except Exception as e:
                status_and_message = ErrorStatusAndMessage(e)
                artemis.log.LOGGER.error(format_exception(e))

        elif action == Actions.STOP.value:
            status_and_message = self.runner.stop()
        # no idea why mypy gives an attribute error here but nowhere else for this
        # exact same situation...
        return asdict(status_and_message)  # type: ignore


class StopOrStatus(Resource):
    def __init__(self, runner: BlueskyRunner) -> None:
        super().__init__()
        self.runner: BlueskyRunner = runner

    def put(self, action):
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.STOP.value:
            status_and_message = self.runner.stop()
        return asdict(status_and_message)

    def get(self, **kwargs):
        action = kwargs.get("action")
        status_and_message = StatusAndMessage(Status.FAILED, f"{action} not understood")
        if action == Actions.STATUS.value:
            status_and_message = self.runner.current_status
        return asdict(status_and_message)


def create_app(
    test_config=None, RE: RunEngine = RunEngine({}), skip_startup_connection=False
) -> Tuple[Flask, BlueskyRunner]:
    runner = BlueskyRunner(RE, skip_startup_connection=skip_startup_connection)
    app = Flask(__name__)
    if test_config:
        app.config.update(test_config)
    api = Api(app)
    api.add_resource(
        RunExperiment,
        "/<string:plan_name>/<string:action>",
        resource_class_args=[runner],
    )
    api.add_resource(
        StopOrStatus,
        "/<string:action>",
        resource_class_args=[runner],
    )
    return app, runner


def cli_arg_parse() -> (
    Tuple[Optional[str], Optional[bool], Optional[bool], Optional[bool]]
):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Use dev options, such as local graylog instances and S03",
    )
    parser.add_argument(
        "--verbose-event-logging",
        action="store_true",
        help="Log all bluesky event documents to graylog",
    )
    parser.add_argument(
        "--logging-level",
        type=str,
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Choose overall logging level, defaults to INFO",
    )
    parser.add_argument(
        "--skip-startup-connection",
        action="store_true",
        help="Skip connecting to EPICS PVs on startup",
    )
    args = parser.parse_args()
    return (
        args.logging_level,
        args.verbose_event_logging,
        args.dev,
        args.skip_startup_connection,
    )


if __name__ == "__main__":
    artemis_port = 5005
    (
        logging_level,
        VERBOSE_EVENT_LOGGING,
        dev_mode,
        skip_startup_connection,
    ) = cli_arg_parse()

    artemis.log.set_up_logging_handlers(logging_level, dev_mode)
    app, runner = create_app(skip_startup_connection=skip_startup_connection)
    atexit.register(runner.shutdown)
    flask_thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=artemis_port, debug=True, use_reloader=False
        ),
        daemon=True,
    )
    flask_thread.start()
    artemis.log.LOGGER.info(
        f"Artemis now listening on {artemis_port} ({'IN DEV' if dev_mode else ''})"
    )
    runner.wait_on_queue()
    flask_thread.join()
