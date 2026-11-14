"""Typed AST for the Sophios language.

The nodes here are the executable specification of the syntax layer: what a
well-formed Sophios document may contain, independent of which tools happen
to be installed. Every node is frozen (an AST consumers can mutate is not a
specification of anything) and slotted (allocated once per construct).
"""
from dataclasses import dataclass
from datetime import date, datetime
from typing import TypeAlias

from .spans import SourceSpan


@dataclass(frozen=True, slots=True)
class InlineLiteral:
    """`!ii value` — a literal, never an edge.

    `text` is the literal's source spelling when parsed from a plain tagged
    scalar (`!ii 0777`, whose value 511 knows nothing of its spelling), and
    None when parsed from a quoted or block scalar, whose value is its text,
    or built from the desugared form or the Python API. Rendering a parsed
    literal transcribes `text` rather than re-serialising `value`, since
    reconstruction is lossy by nature.
    """

    value: 'OpaqueCwl'
    span: SourceSpan | None = None
    text: str | None = None


@dataclass(frozen=True, slots=True)
class EdgeDef:
    """`!& name` — an explicit edge definition site.

    Legal only where a value comes into being: an output. Reachable only
    through `OutputBinding.edge_def`, not a member of `InputValue`. `!&`
    written in input position is reported as `wic019` instead.
    """

    name: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class EdgeRef:
    """`!* name` — an explicit edge call site."""

    name: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class RawCwlRef:
    """`!cwl expression` — an opaque CWL reference, passed through unresolved.

    The compiler does not attempt to interpret the expression. This is the
    local, visible form of what `--allow_raw_cwl` does globally.
    """

    expression: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class UnresolvedName:
    """A bare string that must resolve to a workflow input.

    If it does not, resolution reports a diagnostic naming both remedies:
    `!ii` for a literal, `!cwl` for a raw CWL reference.
    """

    name: str
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class CwlRecord:
    """`!cwl {source: ..., linkMerge: ...}` — CWL's WorkflowStepInput, at an `in:` position.

    `sources` are the Sophios references its `source` names, in order; each is
    an edge (`!*`) or a workflow input (a bare name). `fields` are the other
    WorkflowStepInput fields, verbatim. The record is the one place a step
    input may say more than where its value comes from.
    """

    sources: tuple[EdgeRef | UnresolvedName, ...] = ()
    fields: tuple[tuple[str, 'OpaqueCwl'], ...] = ()
    span: SourceSpan | None = None

    @property
    def delivers_its_source(self) -> bool:
        """Whether the step input receives its one source's value as it is:
        no merge, no pick and no `valueFrom` stands between them."""
        return len(self.sources) == 1 and not {'linkMerge', 'pickValue', 'valueFrom'} & dict(self.fields).keys()


#: The complete set of forms a step input may take: a literal, an edge
#: reference, a raw CWL reference, an unresolved name, or a step-input
#: record. `EdgeDef` is deliberately not a member — an edge is defined on an
#: output, reachable only through `OutputBinding.edge_def`. Closed by
#: construction, so exhaustive `match` statements over it stay exhaustive.
InputValue: TypeAlias = InlineLiteral | EdgeRef | RawCwlRef | UnresolvedName | CwlRecord

#: CWL that Sophios does not interpret and passes through unchanged: a closed
#: recursive union of what YAML's safe schema can produce, plus the Sophios
#: constructs the passthrough walk preserves. `date`/`datetime` are members
#: because YAML resolves timestamps; their JSON projection is ISO-8601 text
#: (see `render.to_json`).
OpaqueCwl: TypeAlias = (
    None | bool | int | float | str | date | datetime
    | list['OpaqueCwl'] | dict[str, 'OpaqueCwl'] | InputValue
)


@dataclass(frozen=True, slots=True)
class OutputBinding:
    """One entry of a step's `out:` list.

    Either a bare name (`- file`) or a single-key mapping binding that name to
    an edge definition (`- file: !& file_touch`).
    """

    name: str
    edge_def: EdgeDef | None
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class Step:
    """A single workflow step.

    `interpreted` holds the CWL keys Sophios acts upon (`scatter`,
    `scatterMethod`, `when`, `run`); `passthrough` holds everything else,
    preserved verbatim, bar the list form of `requirements` and `hints`: the
    parser reads it as a mapping, unless the list holds an `$import` or
    `$include`, which is held as written.
    """

    id: str
    inputs: tuple[tuple[str, InputValue], ...] = ()
    outputs: tuple[OutputBinding, ...] = ()
    interpreted: tuple[tuple[str, OpaqueCwl], ...] = ()
    passthrough: tuple[tuple[str, OpaqueCwl], ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class StepKey:
    """A `wic:` sidecar step key: `"(1, name)"` for the step at position 1,
    or a bare `"name"` for the one step with that id (`index` is None)."""

    index: int | None
    name: str

    def __str__(self) -> str:
        return self.name if self.index is None else f'({self.index}, {self.name})'


@dataclass(frozen=True, slots=True)
class WicSidecar:
    """The `wic:` metadata block.

    `steps` is normalised to `StepKey`; every other key (`graphviz`,
    `default_implementation`, `namespace`, ...) is retained verbatim, once the
    parser has checked it is a key the block has, with a value of its shape.
    """

    steps: tuple[tuple[StepKey, 'WicSidecar'], ...] = ()
    entries: tuple[tuple[str, OpaqueCwl], ...] = ()
    #: Each `implementations:` body, parsed. Not written back: the bodies stay
    #: in `entries` and are spelled from there.
    implementations: tuple[tuple[str, 'Document'], ...] = ()
    span: SourceSpan | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """A parsed Sophios document.

    `passthrough` carries every top-level key Sophios does not interpret —
    `$namespaces`, `$schemas`, `requirements`, `hints`, and anything else —
    preserved so it can be emitted unchanged, bar the list form of `inputs`,
    `outputs`, `requirements` and `hints`: the parser reads it as a mapping,
    unless the list holds an `$import` or `$include`, which is held as written.
    """

    steps: tuple[Step, ...] = ()
    sidecar: WicSidecar | None = None
    passthrough: tuple[tuple[str, OpaqueCwl], ...] = ()
    span: SourceSpan | None = None
    #: True when `steps:` was written as a mapping rather than a sequence.
    steps_as_mapping: bool = False
    #: Where each entry of `inputs:` and `outputs:` written as a mapping was written: (`inputs` or `outputs`,
    #: its name, its span).
    port_spans: tuple[tuple[str, str, SourceSpan], ...] = ()
