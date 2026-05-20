# Python Workflow API

The Python Workflow API is the primary way to author Sophios workflows.

This guide documents the core workflow model: load or create tools, place them
in steps, bind inputs and outputs, wrap the steps in a workflow, then compile or
run the result.

The goal is not just to show syntax. The goal is to make the workflow graph
visible in ordinary Python code.

## Scope

This page covers:

- what a `Step` represents,
- what a `Workflow` represents,
- how literal values differ from workflow inputs,
- how a step output becomes a later step input,
- what compilation produces,
- how to compile and inspect workflow artifacts,
- when to run locally,
- when to keep compiled CWL in memory for compute payload construction.

It does not cover every CWL feature. Advanced YAML controls, static dispatch,
and program synthesis are documented separately in
[Advanced YAML and Operations](advanced.md).

## Working Directory Assumption

Most examples in this guide assume you are running from the repository root:

```bash
cd /path/to/sophios
```

That makes checked-in adapter paths such as `cwl_adapters/echo.cwl` resolve
cleanly.

When writing reusable scripts, prefer `Path` objects over fragile string paths:

```python
from pathlib import Path

echo_tool = Path("cwl_adapters") / "echo.cwl"
```

## Step 1: Load a Tool as a Step

A `Step` is a CWL `CommandLineTool` placed inside a workflow context.

```python
from pathlib import Path

from sophios.apis.python import Step


echo = Step(Path("cwl_adapters") / "echo.cwl")
```

At this point, Sophios has loaded the tool contract. It knows the tool has an
input named `message` and an output named `stdout`.

You can inspect the ports:

```python
for input_port in echo.inputs:
    print(input_port.name, input_port.parameter_type)

for output_port in echo.outputs:
    print(output_port.name, output_port.parameter_type)
```

This interface is the contract Sophios uses for validation, binding, edge
inference, and generated CWL.

## Step 2: Bind a Literal Input

Bind a value to a step input:

```python
echo.inputs.message = "hello from Sophios"
```

That assignment does not run the tool. It records a workflow binding:

```text
echo.message <- "hello from Sophios"
```

Sophios will later turn that binding into the appropriate generated CWL job
input.

The older shorthand still works:

```python
echo.message = "hello from Sophios"
```

The docs use the explicit form because it is clearer:

- `step.inputs.<name>` is where values enter a step,
- `step.outputs.<name>` is where values leave a step.

## Step 3: Put Steps in a Workflow

Wrap the step in a workflow:

```python
from sophios.apis.python import Workflow


workflow = Workflow([echo], "hello_python")
```

A workflow has a name and an ordered list of children. Children may be concrete
steps or nested workflows.

Compile without running:

```python
workflow.write_artifacts()
```

Run locally:

```python
workflow.run()
```

The smallest complete example is therefore:

```python
from pathlib import Path

from sophios.apis.python import Step, Workflow


def build_workflow() -> Workflow:
    echo = Step(Path("cwl_adapters") / "echo.cwl")
    echo.inputs.message = "hello from Sophios"
    return Workflow([echo], "hello_python")


if __name__ == "__main__":
    build_workflow().run()
```

This example is intentionally small. It demonstrates the three required
operations for a runnable workflow: load a tool, bind an input, and run a
workflow.

## Step 4: Link Two Steps

Most workflows become useful when one step consumes another step's output.

```python
from pathlib import Path

from sophios.apis.python import Step, Workflow


touch = Step(Path("cwl_adapters") / "touch.cwl")
touch.inputs.filename = "empty.txt"

append = Step(Path("cwl_adapters") / "append.cwl")
append.inputs.file = touch.outputs.file
append.inputs.str = "Hello"

cat = Step(Path("cwl_adapters") / "cat.cwl")
cat.inputs.file = append.outputs.file

workflow = Workflow([touch, append, cat], "multistep_python")
workflow.write_artifacts()
```

Read the bindings as arrows:

```text
touch.outputs.file -> append.inputs.file
append.outputs.file -> cat.inputs.file
```

The Python assignment creates the edge. You do not need to hand-write a CWL
`source` field.

## Linear Edge Inference

The Python API can also use the same edge inference mechanism as `.wic`
workflows. In a linear workflow, if a required step input is not bound, Sophios
passes that missing input to the compiler. The compiler then looks backward
through earlier steps and connects the most recent compatible output.

That means this also works:

```python
touch = Step(Path("cwl_adapters") / "touch.cwl")
touch.inputs.filename = "empty.txt"

append = Step(Path("cwl_adapters") / "append.cwl")
append.inputs.str = "Hello"

cat = Step(Path("cwl_adapters") / "cat.cwl")

workflow = Workflow([touch, append, cat], "multistep_python")
workflow.write_artifacts()
```

Here Sophios infers:

```text
touch.outputs.file -> append.inputs.file
append.outputs.file -> cat.inputs.file
```

Use inference when the workflow is a clear linear chain and the generated graph
is easy to inspect. Prefer explicit bindings when multiple prior outputs could
match, when names matter, or when code review needs to make the data flow
unambiguous.

## Binding Types

There are three common input binding patterns.

| Binding | Python shape | Meaning |
| --- | --- | --- |
| Literal value | `step.inputs.message = "hello"` | The value is known now. |
| Step output | `cat.inputs.file = append.outputs.file` | The value comes from an earlier step. |
| Workflow input | `echo.inputs.message = workflow.inputs.message` | The value will be supplied by the workflow caller. |

This table is one of the most important concepts in the Python API. Most
workflow code is a readable sequence of these bindings.

## Formal Workflow Inputs

Literal inputs are appropriate when a value is fixed for the workflow definition.
Reusable workflows should declare their public interface.

```python
from pathlib import Path

from sophios.apis.python import Step, Workflow, cwl


echo = Step(Path("cwl_adapters") / "echo.cwl")
workflow = Workflow([echo], "say_message")

workflow.add_input("message", cwl.string)
echo.inputs.message = workflow.inputs.message
```

This creates a formal workflow input named `message`. The workflow no longer
hardcodes the message. A caller can provide it at execution or submission time.

Use formal workflow inputs when:

- a value should vary between runs,
- a workflow will be reused,
- workflow structure should be separated from runtime input data,
- a compute payload should carry explicit job inputs.

## Formal Workflow Outputs

Outputs should also be deliberate.

```python
workflow.add_output("captured_stdout", echo.outputs.stdout)
```

That line exposes the step output as part of the workflow's public output
interface.

The namespace form is equivalent:

```python
workflow.outputs.captured_stdout = echo.outputs.stdout
```

Use named workflow outputs when a downstream user, test, or compute service
needs a stable result name.

## What `workflow.yaml` Shows You

Every `Workflow` can render the in-memory Sophios workflow tree:

```python
print(workflow.yaml)
```

This shows the bridge between Python objects and the lower-level Sophios
representation. It is useful when debugging surprising bindings before
compilation.

## Compile Paths

Sophios gives you two common compile paths.

### Write Artifacts to Disk

```python
workflow.write_artifacts()
```

Use this when you want to inspect generated files. Typical artifacts include:

- `autogenerated/<workflow>.cwl`,
- `autogenerated/<workflow>_inputs.yml`,
- intermediate `.wic` workflow trees,
- Graphviz files when graph output is enabled.

This is the best path when generated artifacts need to be reviewed, committed to
a test fixture, or inspected during debugging.

`workflow.compile(write_to_disk=True)` is still available. `write_artifacts()`
is the clearer public method for the common "compile and inspect files" path.

### Keep Compiled CWL in Memory

```python
compiled = workflow.get_cwl_workflow()
```

Use this when the next step is another Python operation, such as packaging a
compute payload.

The returned object contains:

- the compiled CWL workflow fields,
- the workflow name,
- generated `yaml_inputs`.

The compute payload API expects the CWL workflow document and job inputs as
separate pieces. The compute payload guide shows that split in detail.

## Running Locally

Run locally with:

```python
workflow.run()
```

Runtime options can be passed through `run_args_dict`:

```python
workflow.run(
    run_args_dict={
        "cwl_runner": "cwltool",
        "container_engine": "docker",
        "copy_output_files": "yes",
    }
)
```

Local execution is best for:

- smoke-testing small workflows,
- verifying tool contracts,
- checking generated outputs before submission,
- verifying end-to-end behavior in a controlled environment.

If the workflow needs a large container image or special hardware, compile first
and inspect the generated artifacts before attempting a full run.

## Nested Workflows

A workflow can contain another workflow:

```python
preprocess = Workflow([touch, append], "preprocess")
report = Workflow([preprocess, cat], "report")
```

Nested workflows are how large pipelines are split into named components. A
subworkflow can have its own inputs, outputs, tests, and documentation.

Use nesting when a group of steps has a meaningful name:

- "preprocess",
- "segment",
- "measure",
- "summarize",
- "submit".

## Scatter and Conditionals

CWL supports scatter and conditional execution. Sophios exposes those controls
through small step-level settings:

```python
echo.scatter_on(echo.inputs.message, method="dotproduct")
```

```python
echo.when = "$(inputs.message != '')"
```

These features are powerful and should be used with explicit review of the
generated CWL. Scatter changes the shape of values. Conditionals can make
outputs nullable. Both affect downstream type compatibility and runtime
behavior.

The current lightweight `when_pyapi.py` example runs locally, but CWL correctly
warns that outputs from conditional steps may be `null`. That warning is
expected: conditional execution changes the output type contract.

The lightweight `scatter_pyapi.py` example uses a CWL `Any` output because the
array-producing tool is intentionally generic. Sophios treats `Any` as
permissive for explicit Python bindings while keeping compiler edge inference
conservative.

## Generated Files

When you compile or run with disk output enabled, Sophios writes useful
artifacts:

- `autogenerated/<workflow>.cwl`: compiled root CWL workflow.
- `autogenerated/<workflow>_inputs.yml`: generated job inputs.
- `autogenerated/*_tree_raw.wic` and related files: intermediate workflow trees.
- `autogenerated/schemas/`: generated schemas for `.wic` validation.
- `cachedir*`: CWL runner caches and intermediate files.
- `provenance/`: CWL provenance data unless disabled.
- `outdir/`: copied primary outputs when output copying is enabled.
- `error_<workflow>.txt`: tracebacks from compilation or runner startup failures.

These files are the main debugging surface. A serious workflow should be
reviewed through its generated artifacts, not only through the Python code.

## Troubleshooting

When a workflow fails:

- Compile before running. If compilation fails, the issue is in the workflow
  structure or tool contract.
- Inspect `workflow.yaml` to check bindings before compilation.
- Inspect `autogenerated/<workflow>.cwl` and the generated inputs after
  compilation.
- Re-run without quiet settings if you need full CWL runner output.
- Check whether a container image is being pulled.
- Delete `autogenerated/`, `cachedir*`, `outdir/`, and `provenance/` when you
  need a clean local run.
- Replace advanced controls with simpler bindings when isolating a failure.

## Tested Lightweight Examples

The following examples are intended to stay lightweight:

- `examples/scripts/helloworld_pyapi.py`: smallest Python workflow.
- `examples/scripts/multistep1_pyapi.py`: step-to-step file flow.
- `examples/scripts/multistep1_toJson_pyapi.py`: in-memory compiled workflow JSON.
- `examples/scripts/reusable_interface_pyapi.py`: formal workflow inputs and outputs.
- `examples/scripts/scatter_pyapi.py`: scatter over array-valued bindings.
- `examples/scripts/when_pyapi.py`: conditional execution.
- `examples/scripts/cwl_builder_workflow.py`: generated CLTs composed in memory.
- `examples/scripts/compute_payload_workflow.py`: Python workflow to validated compute payload.

The Ichnaea and SAM3 walkthroughs are intentionally larger and are documented as
production-style examples rather than quick smoke tests.

## Next Steps

Continue with:

- [Building a CWL CommandLineTool in Python](cwl_builder_sam3.md) to author tools.
- [Using `cwl_builder` and the Workflow Python API Together](cwl_builder_workflow.md) to build tools in memory and compose them immediately.
- [From Python Workflow to Compute Payload](compute_payload_workflow.md) to submit compiled workflows to compute-slurm.
- [Advanced YAML and Operations](advanced.md) when you need `.wic` files, schema validation, inference controls, or audit-friendly artifacts.
