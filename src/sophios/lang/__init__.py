"""The `.wic` language layer: typed AST, parser, and diagnostics.

This package is the syntax layer of the specification — it answers "is this a
well-formed `.wic` document?" without consulting which tools happen to be
installed. Name resolution and type checking are separate, environment-
dependent concerns.

See design_docs/core-refactor-design.md, Spec 1.
"""
from .diagnostics import Code, Diagnostic, Diagnostics, Severity
from .nodes import (
    Document,
    EdgeDef,
    EdgeRef,
    InlineLiteral,
    InputValue,
    OpaqueCwl,
    OutputBinding,
    RawCwlRef,
    Step,
    StepKey,
    UnresolvedName,
    WicSidecar,
)
from .parser import INTERPRETED_STEP_KEYS, TAG_RAW_CWL, ParseResult, parse
from .spans import SourceSpan

__all__ = [
    'INTERPRETED_STEP_KEYS',
    'TAG_RAW_CWL',
    'Code',
    'Diagnostic',
    'Diagnostics',
    'Document',
    'EdgeDef',
    'EdgeRef',
    'InlineLiteral',
    'InputValue',
    'OpaqueCwl',
    'OutputBinding',
    'ParseResult',
    'RawCwlRef',
    'Severity',
    'SourceSpan',
    'Step',
    'StepKey',
    'UnresolvedName',
    'WicSidecar',
    'parse',
]
