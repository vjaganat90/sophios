"""Reusable workflow interface example for the Sophios Python API."""

from pathlib import Path

from sophios.apis.python import Step, Workflow, cwl


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = REPO_ROOT / "cwl_adapters"


def workflow() -> Workflow:
    """Build a workflow with a formal input and a declared output."""
    echo = Step(ADAPTERS / "echo.cwl")

    workflow_ = Workflow([echo], "reusable_interface_pyapi_py")
    workflow_.add_input("message", cwl.string)
    echo.inputs.message = workflow_.inputs.message
    workflow_.add_output("stdout", echo.outputs.stdout)

    return workflow_


if __name__ == "__main__":
    workflow().write_artifacts()
