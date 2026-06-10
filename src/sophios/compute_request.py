"""Schema-backed compute request objects."""

from dataclasses import dataclass, field, fields as dataclass_fields
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from jsonschema import Draft202012Validator

from .submit import submit
from .wic_types import Json, RawJson


class ComputeRequestValidationError(ValueError):
    """Raised when a compute request does not match the checked-in schema."""


class CompiledWorkflowLike(Protocol):
    """Compiled workflow boundary consumed by the compute request API."""

    @property
    def name(self) -> str:
        """Compiled workflow name."""
        ...

    @property
    def cwl_workflow(self) -> Json:
        """Compiled CWL workflow document."""
        ...

    @property
    def cwl_job_inputs(self) -> Json:
        """Compiled CWL job inputs."""
        ...


def _json_value(value: Any) -> Any:
    return str(value) if isinstance(value, Path) else value


def _nested_mapping(value: Any) -> Json:
    return cast(Json, value.to_mapping())


def _config_mapping(config: Any) -> Json:
    request: Json = {}
    for item in dataclass_fields(config):
        json_key = item.metadata.get("json")
        if json_key is None:
            continue
        value = getattr(config, item.name)
        if value is None:
            continue
        renderer = item.metadata.get("render", _json_value)
        request[str(json_key)] = renderer(value)
    return request


@dataclass(frozen=True, slots=True)
class ToilRuntimeConfig:
    """Schema mirror for `computeConfig.toilConfig`."""

    log_level: str | None = field(default=None, metadata={"json": "logLevel"})

    def to_mapping(self) -> Json:
        """Render the toil configuration."""
        return _config_mapping(self)


@dataclass(frozen=True, slots=True)
class ComputeOutputConfig:
    """Schema mirror for `computeConfig.outputConfig`."""

    mode: str | None = field(default=None, metadata={"json": "mode"})
    output_dir: str | Path | None = field(default=None, metadata={"json": "outputDir"})

    @classmethod
    def service_default(cls) -> "ComputeOutputConfig":
        """Use the service-managed output directory."""
        return cls(mode="serviceDefault")

    @classmethod
    def workflow_declared(cls) -> "ComputeOutputConfig":
        """Preserve the workflow's own output behavior."""
        return cls(mode="workflowDeclared")

    @classmethod
    def user_specified(cls, output_dir: str | Path) -> "ComputeOutputConfig":
        """Use a caller-provided output directory."""
        return cls(mode="userSpecified", output_dir=output_dir)

    @classmethod
    def from_mapping(
        cls,
        *,
        mode: str | None = None,
        outputDir: str | Path | None = None,
    ) -> "ComputeOutputConfig":
        """Construct from schema-shaped mapping field names."""
        return cls(mode=mode, output_dir=outputDir)

    def to_mapping(self) -> Json:
        """Render the output configuration."""
        request = _config_mapping(self)
        if request.get("mode") == "userSpecified" and "outputDir" not in request:
            raise ValueError("userSpecified output mode requires output_dir")
        return request


@dataclass(frozen=True, slots=True)
class SlurmJobConfig:  # pylint: disable=too-many-instance-attributes
    """Schema mirror for `computeConfig.slurmConfig`."""

    job_name: str | None = field(default=None, metadata={"json": "jobName"})
    partition: str | None = field(default=None, metadata={"json": "partition"})
    slurm_job_gpu_count: int | None = field(default=None, metadata={"json": "slurmJobGpuCount"})
    cpus_per_task: int | None = field(default=None, metadata={"json": "cpusPerTask"})
    nodes: int | None = field(default=None, metadata={"json": "nodes"})
    tasks_per_node: int | None = field(default=None, metadata={"json": "tasksPerNode"})
    output: str | None = field(default=None, metadata={"json": "output"})
    error: str | None = field(default=None, metadata={"json": "error"})
    time_limit: str | None = field(default=None, metadata={"json": "time"})
    memory: str | None = field(default=None, metadata={"json": "memory"})

    def to_mapping(self) -> Json:
        """Render the SLURM configuration."""
        return _config_mapping(self)


@dataclass(frozen=True, slots=True)
class ComputeExecutionConfig:
    """Schema mirror for `computeConfig`."""

    toil: ToilRuntimeConfig | None = field(default=None, metadata={"json": "toilConfig", "render": _nested_mapping})
    output: ComputeOutputConfig | None = field(
        default=None, metadata={"json": "outputConfig", "render": _nested_mapping})
    slurm: SlurmJobConfig | None = field(default=None, metadata={"json": "slurmConfig", "render": _nested_mapping})

    def to_mapping(self) -> Json:
        """Render nested compute configuration."""
        return _config_mapping(self)


@dataclass(slots=True)
class ComputeRequest:
    """Schema-backed compute-slurm submission request."""

    cwl_workflow: Json
    cwl_job_inputs: Json
    workflow_id: str | None = None
    jobs: Json = field(default_factory=dict)
    compute_config: ComputeExecutionConfig | None = None

    @classmethod
    def from_compiled(
        cls,
        compiled: CompiledWorkflowLike,
        *,
        workflow_id: str | None = None,
        jobs: Mapping[str, Any] | None = None,
        compute_config: ComputeExecutionConfig | None = None,
    ) -> "ComputeRequest":
        """Create a compute request from a compiled workflow boundary object."""
        return cls(
            cwl_workflow=dict(compiled.cwl_workflow),
            cwl_job_inputs=dict(compiled.cwl_job_inputs),
            workflow_id=workflow_id or compiled.name,
            jobs=dict(jobs or {}),
            compute_config=compute_config,
        )

    def resolved_workflow_id(self) -> str | None:
        """Return the workflow id used for request status polling."""
        workflow_id = self.workflow_id or self.cwl_workflow.get("id")
        return workflow_id if isinstance(workflow_id, str) and workflow_id else None

    def to_mapping(self) -> Json:
        """Render and validate the compute request as a Python mapping."""
        request: Json = {
            "cwlWorkflow": self.cwl_workflow,
            "cwlJobInputs": self.cwl_job_inputs,
            "jobs": dict(self.jobs),
        }
        workflow_id = self.resolved_workflow_id()
        if workflow_id is not None:
            request["id"] = workflow_id
        if self.compute_config is not None:
            compute_config = self.compute_config.to_mapping()
            if compute_config:
                request["computeConfig"] = compute_config
        return validate_compute_request(request)

    def to_json(self, *, indent: int | None = None, sort_keys: bool = False) -> RawJson:
        """Render and validate the compute request as serialized JSON text."""
        return json.dumps(self.to_mapping(), indent=indent, sort_keys=sort_keys)


def validate_compute_request(request: Mapping[str, Any]) -> Json:
    """Validate a compute request mapping against the checked-in schema."""
    request_mapping: Json = dict(request)
    try:
        _validator().validate(request_mapping)
    except Exception as exc:  # pragma: no cover - schema library formats the message
        raise ComputeRequestValidationError(str(exc)) from exc
    return request_mapping


def submit_compute_request(
    request: ComputeRequest,
    submit_url: str,
    *,
    timeout: tuple[int, int] = (5, 30),
    poll_interval_seconds: int = 15,
    log_path: str | Path | None = None,
) -> int:
    """Submit a typed compute request through the generic JSON submitter."""
    return submit(
        request.to_json(),
        submit_url,
        submission_id=request.resolved_workflow_id(),
        timeout=timeout,
        poll_interval_seconds=poll_interval_seconds,
        log_path=log_path,
    )


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema_path = Path(__file__).with_name("compute_request_schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "CompiledWorkflowLike",
    "ComputeExecutionConfig",
    "ComputeOutputConfig",
    "ComputeRequest",
    "ComputeRequestValidationError",
    "RawJson",
    "SlurmJobConfig",
    "ToilRuntimeConfig",
    "submit_compute_request",
    "validate_compute_request",
]
