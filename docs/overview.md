# Overview

Sophios helps teams turn command-line tools into workflows that are easier to
review, run, validate, and audit.

The guiding idea is simple: most workflow complexity comes from unclear
boundaries. A shell script might know what order commands run in, but it usually
does not make the tool contract, data dependencies, runtime assumptions, or final
execution payload easy to inspect. Sophios makes those boundaries explicit.

The recommended path is Python-first:

```text
Python tool definition
  -> Sophios Step
  -> Sophios Workflow
  -> compiled CWL workflow + job inputs
  -> local run or compute-slurm payload
```

The `.wic` YAML format remains supported and important. It is best introduced
after the Python concepts are clear, as an advanced representation for standalone
files, headless execution, CI, debugging, and audit trails.

## The Problem Sophios Solves

Command-line tools are powerful because they are direct. They are also easy to
compose poorly.

A typical project might have:

- a segmentation command,
- a conversion command,
- a plotting command,
- a post-processing command,
- a Slurm script,
- a half-documented JSON request body,
- and several hidden assumptions about file names, containers, GPUs, or working
  directories.

That can be enough for one person on one machine. It is not enough for a team,
a production service, or an auditable scientific workflow.

Sophios gives that work a structure without forcing every user to hand-write raw
CWL. The structure is deliberately layered:

- Describe each command-line tool as a contract.
- Put each tool in a workflow as a step.
- Bind values, workflow inputs, and upstream outputs explicitly when clarity matters.
- Let the compiler infer straightforward linear edges when the graph is obvious.
- Compile the workflow to CWL.
- Run locally or build a validated compute payload.
- Inspect the generated artifacts when something matters.

This is the difference between "I ran a script" and "I can explain the workflow."

## What You Author

Sophios users mainly author three kinds of objects.

### 1. Tool Contracts

A tool contract says what one command-line tool needs and what it returns.

In Python, this is a `CommandLineTool`:

```python
from sophios.apis.python import CommandLineTool, Input, Inputs, Output, Outputs, cwl

inputs = Inputs(
    message=Input(cwl.string, position=1),
)

outputs = Outputs(
    text_file=Output(cwl.file, glob="stdout.txt"),
)

tool = (
    CommandLineTool("emit_text", inputs, outputs)
    .base_command("echo")
    .stdout("stdout.txt")
)
```

This object is not a workflow yet. It is the contract for one executable unit:

- the command is `echo`,
- it accepts one string input named `message`,
- it writes stdout to `stdout.txt`,
- it exposes that file as an output named `text_file`.

That distinction matters. A tool contract should be understandable before it is
placed inside a workflow.

### 2. Workflow Steps

A `Step` is a tool contract used inside a workflow. A step has inputs you can
bind and outputs that later steps can consume.

```python
from pathlib import Path

from sophios.apis.python import Step

echo = Step(Path("cwl_adapters") / "echo.cwl")
echo.inputs.message = "hello from Sophios"
```

The assignment is a workflow binding. Sophios records that the `message` input
of this step should receive the literal value `"hello from Sophios"`.

Bindings can also connect steps:

```python
cat.inputs.file = echo.outputs.stdout
```

That line means: the `file` input of `cat` comes from the `stdout` output of
`echo`. It is an edge in the workflow graph.

### 3. Workflows

A `Workflow` is an ordered collection of steps and nested workflows.

```python
from sophios.apis.python import Workflow

workflow = Workflow([echo], "hello_python")
workflow.write_artifacts()
```

Compilation checks the Sophios workflow object and emits CWL artifacts. Running
the workflow uses those artifacts with a CWL runner.

```python
workflow.run()
```

For production or service integration, keep the compiled result in memory:

```python
compiled = workflow.get_cwl_workflow()
```

That in-memory compiled object is the bridge to compute payload construction.

## What Sophios Produces

Sophios produces artifacts that can be inspected. This is one of the most
important parts of the system.

Depending on how you compile or run, you may see:

- a root CWL workflow document,
- generated CWL job inputs,
- intermediate `.wic` workflow trees,
- Graphviz sources and diagrams,
- local runner output summaries,
- provenance files,
- compute-slurm payload JSON.

These artifacts make the workflow debuggable and reviewable. They let a
reviewer ask concrete questions:

- Which command ran?
- Which input fed this step?
- Which output became part of the public workflow interface?
- What exactly would be submitted to compute?
- Where did the generated CWL differ from the Python object I expected?

The generated artifacts are not noise. They are evidence.

## Why Python First

Python is the recommended authoring interface because it gives workflow authors
names, functions, imports, tests, static analysis, and refactoring tools. It is
also the most direct way to compose generated tools, reusable helper functions,
and application code.

Python lets teams build workflows incrementally:

1. Start with one tool.
2. Wrap it in a step.
3. Bind one literal input.
4. Compile.
5. Add a second step.
6. Expose formal workflow inputs and outputs.
7. Package for compute only after the workflow is clear.

That progression keeps responsibilities separated. Tool contracts, workflow
edges, runtime inputs, compiled CWL, and compute payloads can each be inspected
at the point where they become relevant.

Python is the authoring layer. CWL is the portable execution target. YAML is the
advanced file representation.

## Why CWL Still Matters

Sophios does not try to replace CWL. It uses CWL as the execution target.

CWL is valuable because it is portable, explicit, and supported by existing
runners. The cost is that raw CWL can be verbose for everyday authoring. Sophios
is the layer above it:

- Python makes workflows easier to author.
- Sophios compiles those workflows into CWL.
- CWL runners execute the compiled result.

This gives you a practical split. Users can work in Python, reviewers can inspect
generated CWL, and execution remains grounded in a workflow standard.

## Where YAML Fits

The `.wic` YAML format is still first-class, but it serves a different role from
the Python API.

Use YAML when you need:

- a workflow that is just a file,
- headless execution from CI or batch scripts,
- a compact artifact for review or archive,
- explicit custom tags for inline inputs and anchors,
- schema-backed editor validation,
- detailed inspection of inference and compiler behavior.

YAML is especially useful for auditability. A `.wic` file can be stored, diffed,
validated, and run without importing a Python module from a project repository.

The docs therefore treat YAML as advanced usage: important, powerful, and best
used when a file-native workflow representation is the right operational shape.

## Local Runs and Compute Submission

Sophios supports two common execution paths.

### Local Execution

Use local execution while developing:

```python
workflow.run()
```

Local runs compile the workflow, invoke a CWL runner, and write output artifacts.
This is the fastest way to smoke-test a small workflow.

### Compute Submission

Use compute payloads when the workflow is ready for a service boundary:

```python
compiled = workflow.get_cwl_workflow()
payload = ComputeWorkflowPayload(
    cwl_workflow={key: value for key, value in compiled.items() if key not in {"name", "yaml_inputs"}},
    cwl_job_inputs=dict(compiled["yaml_inputs"]),
)
compute_json = payload.get_compute_payload()
```

That last call validates the payload before submission. The submission helpers
then send the validated JSON to a compute-slurm endpoint and poll status.

The compute layer is intentionally separate from workflow authoring. A workflow
should be understandable before it becomes a remote job.

## What Makes Sophios Different

Sophios is not just a wrapper around command execution. Its value comes from the
combination of authoring ergonomics and inspectable outputs.

### It is tool-centered

The basic unit is the command-line tool contract. This keeps workflow design
close to the software people already use.

### It is graph-aware

Step outputs can be connected to later step inputs. Sophios can also infer many
linear edges from type and format information, whether the workflow was authored
in Python or `.wic` YAML.

### It is artifact-oriented

Compilation produces files and data structures that can be inspected. This is
essential for debugging, review, CI, and reproducibility.

### It is execution-agnostic at the authoring layer

The same Python-authored workflow can be compiled, run locally, inspected as CWL,
or packaged for compute submission.

### It is honest about advanced complexity

Features like scatter, conditionals, inference rules, namespaces, and static
dispatch are powerful, but they should be used deliberately. The documentation
keeps the base workflow model separate from these advanced controls so their
runtime effects are easier to review.

## What Sophios Is Not

Sophios is not a general-purpose scheduler. It does not replace Docker, Podman,
Slurm, CWL runners, or compute-slurm. It coordinates with those systems.

Sophios is not a magic planner. It can infer some edges and can perform limited
automatic insertion in advanced YAML workflows, but users should still inspect
important generated DAGs and artifacts.

Sophios is not a reason to skip tool design. Clear tool inputs and outputs are
still the foundation of a clear workflow.

## Recommended Adoption Path

For a new project or integration, use this order:

1. Install Sophios and verify that the Python API imports.
2. Build the smallest Python workflow with `Step` and `Workflow`.
3. Bind a step output into a later step input.
4. Declare formal workflow inputs and outputs.
5. Compile and inspect generated CWL.
6. Author a new `CommandLineTool` in Python.
7. Convert the generated tool into a workflow step.
8. Build a compute payload only after the workflow is clear.
9. Use `.wic` YAML for advanced standalone, CI, or audit-focused workflows.

Each stage introduces one responsibility and one artifact boundary. Keep those
boundaries visible in code review and operational runbooks.

## What To Read Next

- [Install Guide](installguide.md): set up Sophios and verify the environment.
- [Python Workflow API](userguide.md): use `Step`, `Workflow`, bindings, inputs, outputs, compile, and run.
- [Building a CWL CommandLineTool in Python](cwl_builder_sam3.md): define tool contracts.
- [Using `cwl_builder` and the Workflow Python API Together](cwl_builder_workflow.md): compose generated tools in memory.
- [From Python Workflow to Compute Payload](compute_payload_workflow.md): package compiled workflows for compute-slurm.
- [Advanced YAML and Operations](advanced.md): use `.wic` files for auditability, CI, debugging, and advanced compiler features.
