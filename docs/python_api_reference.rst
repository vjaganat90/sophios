Python API Reference
====================

This reference documents the public Python surfaces that are intended for user
workflows, tool authoring, compute payload construction, and compute submission.

For guided learning, start with :doc:`userguide`, :doc:`tool_builder_sam3`, and
:doc:`compute_payload_workflow`. Use this page when you need signatures and
member-level detail.

sophios.apis.python.workflow and sophios.apis.python.tool_builder
-----------------------------------------------------------------

Import user-facing workflow and tool-authoring objects from their concrete
modules:

.. code-block:: python

   from sophios.apis.python.workflow import Step, Workflow
   from sophios.apis.python.tool_builder import CommandLineTool, Input, Output

The detailed member documentation lives in the concrete modules below.

sophios.apis.python.workflow
----------------------------

.. automodule:: sophios.apis.python.workflow
   :members:

sophios.apis.python.tool_builder
--------------------------------

.. automodule:: sophios.apis.python.tool_builder
   :members:

sophios.compute_payload
-----------------------

.. automodule:: sophios.compute_payload
   :members:

sophios.compute_submit
----------------------

.. automodule:: sophios.compute_submit
   :members:
