"""The Sophios language layer: typed AST, parser, and diagnostics.

This package is the syntax layer of the specification — it answers "is this a
well-formed Sophios document?" without consulting which tools happen to be
installed. Name resolution and type checking are separate, environment-
dependent concerns.

`parse` and `render` are inverses: rendering a parsed document and parsing it
again reproduces the document it started from.

See design_docs/core-refactor-design.md, Spec 1.
"""
from .cwl import CWL_VERSION, CWL_VERSIONS, CwlVersion
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
from ..utils_yaml import Key, Tag
from .parser import Forms, Grammar, ParseResult, parse
from .render import render, to_json
from .versions import KNOWN_VERSIONS, LANG_VERSION, resolve as resolve_lang_version
from .schema import wic_schema
from .spans import SourceSpan

__all__ = [
    'CWL_VERSION',
    'CWL_VERSIONS',
    'CwlVersion',
    'Code',
    'Diagnostic',
    'Diagnostics',
    'KNOWN_VERSIONS',
    'Key',
    'Document',
    'Forms',
    'Grammar',
    'EdgeDef',
    'EdgeRef',
    'InlineLiteral',
    'InputValue',
    'LANG_VERSION',
    'OpaqueCwl',
    'OutputBinding',
    'ParseResult',
    'RawCwlRef',
    'Severity',
    'SourceSpan',
    'Step',
    'StepKey',
    'Tag',
    'UnresolvedName',
    'WicSidecar',
    'parse',
    'render',
    'resolve_lang_version',
    'to_json',
    'wic_schema',
]
