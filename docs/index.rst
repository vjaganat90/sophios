Sophios documentation
=====================

Sophios is a Python-first workflow authoring toolkit for turning command-line
tools into portable, inspectable workflows. You describe tool contracts, compose
those tools into a workflow graph, compile the graph to CWL, and then run it
locally or package it for compute-slurm submission.

The recommended learning path starts with the Python API. The ``.wic`` YAML
format remains fully supported, but the docs treat it as an advanced format for
debuggable, headless, standalone, and auditable workflows.

Why Sophios?
------------

Most scientific and data workflows begin as command-line tools plus a shell
script. That works until the workflow needs to be taught, reviewed, reused,
submitted to another machine, or audited months later. Sophios gives that work a
clear structure:

* a ``CommandLineTool`` captures what one tool expects and produces,
* a ``Step`` places that tool inside a workflow,
* a ``Workflow`` declares the graph and public interface,
* compilation emits CWL and job inputs you can inspect,
* compute helpers validate payloads before submission.

The goal is not to hide the workflow. The goal is to make the workflow easier to
explain, easier to test, and easier to trust.

.. toctree::
   :maxdepth: 2
   :caption: Start Here

   overview.md
   installguide.md
   userguide.md

.. toctree::
   :maxdepth: 2
   :caption: Python API

   cwl_builder_sam3.md
   cwl_builder_workflow.md
   compute_payload_workflow.md
   ichnaea_compact_compute.md
   python_api_reference.rst

.. toctree::
   :maxdepth: 2
   :caption: Advanced YAML and Operations

   advanced.md
   tutorials/tutorials.rst
   validation.md

.. toctree::
   :maxdepth: 2
   :caption: Developers

   dev/installguide.md
   dev/devguide.md
   dev/algorithms.md
   dev/codingstandards.md
   dev/gitetiquette.md
   dev/api.rst

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
