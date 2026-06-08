"""Compiled workflow boundary objects for the public workflow API."""

from dataclasses import dataclass

from sophios.wic_types import Json


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    """Compiled CWL workflow plus its generated job inputs."""

    name: str
    cwl_workflow: Json
    cwl_job_inputs: Json

    def to_dict(self) -> Json:
        """Render the legacy combined dictionary shape.

        The public boundary is the named attributes on this object. This helper
        keeps older callers working while they migrate away from the historical
        ``{"name", "yaml_inputs", ...cwl}`` mapping.
        """
        return {
            "name": self.name,
            "yaml_inputs": dict(self.cwl_job_inputs),
            **dict(self.cwl_workflow),
        }
