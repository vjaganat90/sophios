"""Compiled real-workflow fixtures shared across the Nextflow backend suites."""

import pytest

from sophios.api.python.workflow import Step, Workflow
from sophios.wic_types import RoseTree

from .testkit import REPO_ROOT


@pytest.fixture(scope="session")
def unsupported_real_linear_rose() -> RoseTree:
    """Compile the reviewer's real shell/primitive-output workflow."""
    touch = Step(clt_path=REPO_ROOT / "cwl_adapters" / "touch.cwl")
    touch.inputs.filename = "empty.txt"
    append = Step(clt_path=REPO_ROOT / "cwl_adapters" / "append.cwl")
    append.inputs.str = "Hello"
    cat = Step(clt_path=REPO_ROOT / "cwl_adapters" / "cat.cwl")
    return Workflow([touch, append, cat], "wf")._compile().rose


@pytest.fixture(scope="session")
def real_supported_rose() -> RoseTree:
    """Compile a wholly supported two-process workflow through the real API."""
    touch = Step.from_cwl_document(
        {
            "id": "TOUCH",
            "class": "CommandLineTool",
            "cwlVersion": "v1.2",
            "baseCommand": "touch",
            "inputs": {
                "filename": {
                    "type": "string",
                    "inputBinding": {"position": 1},
                }
            },
            "outputs": {
                "result": {
                    "type": "File",
                    "outputBinding": {"glob": "$(inputs.filename)"},
                }
            },
        },
        process_name="touch",
    )
    touch.inputs.filename = "message.txt"
    copy_step = Step.from_cwl_document(
        {
            "id": "COPY",
            "class": "CommandLineTool",
            "cwlVersion": "v1.2",
            "baseCommand": "cp",
            "arguments": [{"position": 2, "valueFrom": "copy.txt"}],
            "inputs": {
                "source": {
                    "type": "File",
                    "inputBinding": {"position": 1},
                }
            },
            "outputs": {
                "result": {
                    "type": "File",
                    "outputBinding": {"glob": "copy.txt"},
                }
            },
        },
        process_name="copy",
    )
    copy_step.inputs.source = touch.outputs.result
    return Workflow([touch, copy_step], "wf")._compile().rose
