"""Structured diagnostics.

Parsing reports problems as values rather than raising, so a caller can decide
what to do with them and a malformed document can yield several errors in one
pass instead of one per run. See design_docs/core-refactor-design.md, Spec 1.
"""
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .spans import SourceSpan


class Severity(StrEnum):
    """How much a diagnostic matters."""

    ERROR = 'error'
    WARNING = 'warning'


class Code(StrEnum):
    """Stable identifiers for diagnostics.

    Codes are part of the contract: they can be matched on, suppressed, and
    documented, whereas message wording is free to improve.
    """

    INVALID_YAML = 'wic001'
    NOT_A_MAPPING = 'wic002'
    EXPECTED_MAPPING = 'wic003'
    EXPECTED_SEQUENCE = 'wic004'
    EXPECTED_SCALAR = 'wic005'
    MISSING_STEP_ID = 'wic006'
    EMPTY_STEP_ID = 'wic007'
    MALFORMED_WIC_STEP_KEY = 'wic008'
    UNKNOWN_TAG = 'wic009'
    DUPLICATE_KEY = 'wic010'
    UNRESOLVED_INPUT = 'wic011'
    MISSING_REQUIRED_INPUT = 'wic012'
    SUBWORKFLOW_INVALID = 'wic013'
    SCRIPT_ARGUMENT_MISMATCH = 'wic014'
    CONTAINER_ENGINE_UNAVAILABLE = 'wic015'
    MISSING_INPUT_FILE = 'wic016'


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A single problem, located in source when a location is known.

    Parse-phase diagnostics always carry a span — the parser worked from
    positions, so it has one to give. Compile-phase diagnostics may not: until
    the compiler runs on the AST, a failure often knows which workflow it came
    from but not which line. An honest `None` beats an invented position.
    """

    severity: Severity
    code: Code
    message: str
    span: SourceSpan | None = None

    def __str__(self) -> str:
        prefix = f'{self.span}: ' if self.span is not None else ''
        return f'{prefix}{self.severity} [{self.code}] {self.message}'


class Diagnostics(Sequence[Diagnostic]):
    """An ordered, append-only collection of diagnostics.

    Implemented as a `Sequence` so callers can index, iterate, and take a
    length without reaching for an attribute.
    """

    __slots__ = ('_items',)

    def __init__(self, items: Iterable[Diagnostic] = ()) -> None:
        self._items: list[Diagnostic] = list(items)

    def error(self, code: Code, message: str, span: SourceSpan) -> None:
        """Record an error."""
        self._items.append(Diagnostic(Severity.ERROR, code, message, span))

    def warn(self, code: Code, message: str, span: SourceSpan) -> None:
        """Record a warning."""
        self._items.append(Diagnostic(Severity.WARNING, code, message, span))

    @property
    def has_errors(self) -> bool:
        """Whether any recorded diagnostic is an error."""
        return any(d.severity is Severity.ERROR for d in self._items)

    def __getitem__(self, index: int) -> Diagnostic:  # type: ignore[override]
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self._items)

    def __repr__(self) -> str:
        return f'Diagnostics({self._items!r})'


class SophiosError(Exception):
    """A failure the library reports, never a process it terminates.

    This is the deliverable of the design's §3 exception 1: library code used
    to call `sys.exit(1)`, which meant an embedder's process died and the fuzz
    test had to whitelist `SystemExit`. Every former exit site now raises this
    instead, carrying the same messages as structured diagnostics.

    Carries at least one diagnostic by construction — an error with nothing to
    say is not reportable, so it is unrepresentable.
    """

    def __init__(self, diagnostics: Iterable[Diagnostic]) -> None:
        items = Diagnostics(diagnostics)
        if not len(items):
            raise ValueError('SophiosError requires at least one diagnostic')
        super().__init__('\n'.join(str(d) for d in items))
        self.diagnostics: Diagnostics = items

    @classmethod
    def error(cls, code: Code, *messages: str) -> 'SophiosError':
        """Build from one error, spelled as one or more message lines.

        Multiple lines become multiple diagnostics under the same code, so the
        advice text the exit sites used to print survives verbatim.
        """
        return cls(Diagnostic(Severity.ERROR, code, message) for message in messages)
