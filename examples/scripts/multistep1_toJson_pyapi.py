import json
from pathlib import Path

from sophios.apis.python.workflow import Step, Workflow


REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = REPO_ROOT / "cwl_adapters"


def workflow() -> Workflow:
    """Build a workflow and expose it as a compiled CWL JSON object."""
    touch = Step(ADAPTERS / "touch.cwl")
    touch.inputs.filename = "empty.txt"

    append = Step(ADAPTERS / "append.cwl")
    append.inputs.file = touch.outputs.file
    append.inputs.str = "Hello"

    cat = Step(ADAPTERS / "cat.cwl")
    cat.inputs.file = append.outputs.file

    return Workflow([touch, append, cat], "multistep1_toJson_pyapi_py")


if __name__ == "__main__":
    multistep1 = workflow()
    workflow_json = multistep1.compile_to_cwl().to_dict()
    example_dir = Path(__file__).parent
    with open(example_dir / "ground_truth_multistep1.json", "r", encoding="utf-8") as file:
        ground_truth = json.load(file)
    assert ground_truth == workflow_json
