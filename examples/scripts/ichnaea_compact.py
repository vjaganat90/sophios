"""An example showcasing Sophios Python API and creating compute Json object
   - onestep autosegmentation workflow
"""
import copy
from pathlib import Path
from typing import Dict
from datetime import datetime

from sophios.apis.python.api import Workflow
from sophios.wic_types import Json

from sophios.apis.python.cwl_builder import CommandLineTool, Input, Inputs, Output, Outputs, cwl
from sophios.compute_payload import ComputeWorkflowPayload, ComputeConfig, ToilConfig, OutputConfig, SlurmConfig
from sophios.compute_submit import submit_compute_payload


def build_autoseg_CLT() -> CommandLineTool:
    """Create the SAM3 autosegmentation CLT using the declarative API."""
    inputs = Inputs(
        input=Input(cwl.directory, position=1).label("Input Zarr dataset").doc("Path to input zarr dataset"),
        output=Input(cwl.directory, position=2).label("Output segmentation Zarr").doc(
            "Path for output segmentation zarr"
        ),
        model=Input(cwl.file, flag="--model", required=False)
        .label("Model override file")
        .doc("Path containing sam3.pt to override baked-in models/sam3"),
        tile_size=Input(cwl.int, flag="--tile-size", required=False)
        .label("Tile size")
        .doc("Tile size for large slices (default 1024)"),
        overlap=Input(cwl.int, flag="--overlap", required=False)
        .label("Tile overlap")
        .doc("Overlap between adjacent tiles in pixels (default 128)"),
        iou_threshold=Input(cwl.float, flag="--iou-threshold", required=False)
        .label("IoU threshold")
        .doc("IoU threshold for matching labels across tiles (default 0.5)"),
        batch_size=Input(cwl.int, flag="--batch-size", required=False)
        .label("Batch size")
        .doc("Number of tiles per GPU forward pass (default 8)"),
        lora_weights=Input(cwl.file, flag="--lora-weights", required=False)
        .label("LoRA weights")
        .doc("Path to LoRA adapter weights (.pt file) - optional"),
        lora_rank=Input(cwl.int, flag="--lora-rank", required=False)
        .label("LoRA rank")
        .doc("LoRA rank used when lora_weights is set (default 16)"),
        lora_alpha=Input(cwl.int, flag="--lora-alpha", required=False)
        .label("LoRA alpha")
        .doc("LoRA alpha scaling factor used when lora_weights is set (default 32)"),
    )
    outputs = Outputs(output=Output(cwl.directory, from_input=inputs.output).label("Output segmentation Zarr"))

    return (
        CommandLineTool("sam3_ome_zarr_autosegmentation", inputs, outputs)
        .describe(
            "SAM3 OME Zarr autosegmentation",
            "Run SAM3 autosegmentation on a zarr volume.\n",
        )
        .edam()
        .gpu(cuda_version_min="11.7", compute_capability="3.0", device_count_min=2)
        .docker("polusai/ichnaea-api:latest")
        .stage(inputs.output, writable=True)
        .stage(inputs.input)
        .resources(cores=4, ram=64000)
        .base_command(
            "/backend/.venv/bin/python",
            "/backend/dagster_pipelines/jobs/autosegmentation/logic.py",
        )
    )


def workflow(input_dicts: Dict[str, str], workflow_name: str) -> Workflow:
    """Build the test workflow and return Workflow object"""
    # =========== BUILD CLT ==========================
    autoseg_clt = build_autoseg_CLT()  # directly building the CLT in memory
    # =========== CREATE A STEP ======================
    autoseg = autoseg_clt.to_step(step_name='autoseg')  # converting the built CLT into a workflow step
    # assign input values to the step
    autoseg.output = input_dicts['output_dir']
    autoseg.input = input_dicts['input_dir']
    autoseg.model = input_dicts['model_file']
    # =========== CREATE A SOPHIOS WORKFLOW ==========
    # arrange steps
    steps = [autoseg]
    # create workflow from steps DAG
    wkflw = Workflow(steps, workflow_name)
    # =========== RETURN SOPHIOS WORKFLOW OBJECT =====
    return wkflw


def create_compute_payload(workflow_id: str, cwl_workflow: Json, cwl_job_inputs: Json) -> ComputeWorkflowPayload:
    """Returns a compute payload object"""
    # =========== BUILD COMPUTE PAYLOAD OBJECT =======
    # Build the compute payload object here
    compute_object = ComputeWorkflowPayload(
        workflow_id=workflow_id,
        cwl_workflow=cwl_workflow,
        cwl_job_inputs=cwl_job_inputs,
        compute_config=ComputeConfig(
            toil=ToilConfig(log_level="INFO"),
            output=OutputConfig.workflow_declared(),
            slurm=SlurmConfig(partition="normal_gpu", cpus_per_task=4)
        )
    )
    # =========== RETURN COMPUTE PAYLOAD OBJECT ======
    return compute_object


def main() -> int:
    """main function to build and run workflows"""
    # NOTE : Everything related to workflow creation aand submission here is in-memory nothing touches disk
    # ========== CONSTANTS ===========================
    # compute URL
    BASE_URL = 'http://127.0.0.1:7998/compute/'

    # ========== INPUTS TO WORKFLOW ==================
    # The main directory constants
    inputs_dir = Path('/projects/collabs/mock_common/')
    input_dicts = {}
    input_dicts['input_dir'] = str(inputs_dir / 'input_directory')
    input_dicts['output_dir'] = str(inputs_dir / 'output_directory_compact')
    input_dicts['model_file'] = str(inputs_dir / 'model_directory' / 'sam3.pt')

    # ========== BUILD WORKFLOW ======================
    autoseg_workflow = workflow(input_dicts, "autoseg_workflow")
    workflow_json = autoseg_workflow.get_cwl_workflow()

    # ========== COMPUTE INPUT =======================
    # workflow Name
    workflow_name = workflow_json['name']
    # adjust workflow name/id to distinguish after submit using a timestamp
    workflow_name = workflow_name + '__' + datetime.now().strftime('%Y_%m_%d_%H.%M.%S') + '__'
    # workflow Inputs
    workflow_inputs = copy.deepcopy(workflow_json['yaml_inputs'])
    # workflow CWL
    workflow_json.pop('name')
    workflow_json.pop('yaml_inputs')
    compiled_cwl_workflow = copy.deepcopy(workflow_json)

    # ========== CONSTRUCT COMPUTE OBJECT ============
    compute_object = create_compute_payload(workflow_name, compiled_cwl_workflow, workflow_inputs)

    # =========  SUBMIT TO COMPUTE ===================
    return submit_compute_payload(compute_object, BASE_URL)


if __name__ == '__main__':
    main()
