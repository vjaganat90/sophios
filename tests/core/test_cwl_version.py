"""Properties of the CWL substrate version (CR-102, T1.5).

Properties covered:
  P14  every emitting path declares the one substrate version

The design specifies `.wic` as an abstraction over a single declared CWL version
(`design_docs/core-refactor-design.md` §5.2). At baseline three sites disagreed:
the compiler emitted `v1.2`, a CommandLineTool generator emitted `v1.0`, and the
schema accepted any non-empty string.

P14 is checked statically rather than by compiling something, because the
failure it guards against is silent. A document declaring the wrong version is
still valid YAML and still runs, right up until a runner rejects a feature it
should have supported. A grep-shaped property catches the literal at the moment
someone reintroduces it.
"""
import ast
from pathlib import Path
from typing import Final

import pytest
import yaml

from sophios.lang.cwl import CWL_VERSION, CWL_VERSIONS, CwlVersion
from sophios.python_cwl_adapter import generate_CWL_CommandLineTool

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
SRC: Final = REPO_ROOT / 'src' / 'sophios'

#: The one module allowed to contain version literals: it defines them.
OWNER: Final = SRC / 'lang' / 'cwl.py'

#: Keys that carry a CWL version, in either spelling.
VERSION_KEYS: Final = frozenset({'cwlVersion', 'cwl_version'})


def _python_files() -> list[Path]:
    """Every Python file in the package except the module that owns the values."""
    return sorted(path for path in SRC.rglob('*.py') if path != OWNER)


def _version_constant(node: ast.expr | None) -> ast.Constant | None:
    """The node itself if it is a CWL version string, else None."""
    if isinstance(node, ast.Constant) and node.value in set(CWL_VERSIONS):
        return node
    return None


def _target_name(target: ast.expr) -> str | None:
    """The key or variable a value is being assigned to, if it has a simple name."""
    match target:
        case ast.Subscript(slice=ast.Constant(value=str() as key)):
            return key
        case ast.Name(id=name):
            return name
        case _:
            return None


def _version_literals(tree: ast.AST) -> list[tuple[int, str]]:
    """Find every place a CWL version key is assigned a string literal.

    Covers the four shapes the codebase actually used: subscript assignment
    (`d['cwlVersion'] = ...`), a dict literal entry, an annotated assignment,
    and a plain one.
    """
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        match node:
            case ast.Dict(keys=keys, values=values):
                for key, value in zip(keys, values):
                    constant = _version_constant(value)
                    if constant is not None and isinstance(key, ast.Constant) and key.value in VERSION_KEYS:
                        found.append((constant.lineno, str(constant.value)))
            case ast.Assign(targets=targets, value=value):
                constant = _version_constant(value)
                if constant is not None and any(_target_name(t) in VERSION_KEYS for t in targets):
                    found.append((constant.lineno, str(constant.value)))
            case ast.AnnAssign(target=target, value=value):
                constant = _version_constant(value)
                if constant is not None and _target_name(target) in VERSION_KEYS:
                    found.append((constant.lineno, str(constant.value)))
    return found


# --------------------------------------------------------------------------
# P14
# --------------------------------------------------------------------------


@pytest.mark.fast
@pytest.mark.parametrize('path', _python_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_p14_no_module_carries_its_own_cwl_version(path: Path) -> None:
    """P14: only `lang/cwl.py` spells a CWL version; everyone else imports it.

    A module that hardcodes its own is how `python_cwl_adapter.py` sat on
    `v1.0` while the compiler emitted `v1.2` — the two never had to agree
    because nothing made them.
    """
    literals = _version_literals(ast.parse(path.read_text(encoding='utf-8'), str(path)))
    assert not literals, (
        f'{path.relative_to(REPO_ROOT)} hardcodes a CWL version at '
        f'{[f"line {line}: {value!r}" for line, value in literals]}; '
        f'import CWL_VERSION from sophios.lang.cwl instead'
    )


@pytest.mark.fast
def test_p14_the_scan_can_actually_fail() -> None:
    """The scan detects each shape it claims to, so P14 is not vacuous."""
    shapes = [
        "d['cwlVersion'] = 'v1.0'",
        "d = {'cwlVersion': 'v1.0'}",
        "cwl_version: str = 'v1.0'",
        "cwl_version = 'v1.0'",
    ]
    for source in shapes:
        assert _version_literals(ast.parse(source)), f'scan missed: {source}'


@pytest.mark.fast
def test_p14_the_scan_ignores_unrelated_strings() -> None:
    """A version-shaped string not bound to a version key is not a finding."""
    assert not _version_literals(ast.parse("label = 'v1.0'"))
    assert not _version_literals(ast.parse("d = {'other': 'v1.0'}"))


# --------------------------------------------------------------------------
# Sanity checks
# --------------------------------------------------------------------------


@pytest.mark.fast
def test_the_declared_version_is_v1_2() -> None:
    """§5.2 pins the substrate to CWL v1.2."""
    assert CWL_VERSION == 'v1.2'
    assert CWL_VERSION == CwlVersion.V1_2


@pytest.mark.fast
def test_the_version_serialises_as_a_plain_string() -> None:
    """`CWL_VERSION` must survive a YAML dump unchanged.

    This is the check that matters, and the one that `isinstance(x, str)` does
    not make. PyYAML picks a representer by exact type, so a `StrEnum` member
    compares equal to `'v1.2'`, formats as `v1.2`, and still raises
    `RepresenterError` the moment a generated document is written to disk.
    """
    assert type(CWL_VERSION) is str  # pylint: disable=unidiomatic-typecheck
    assert yaml.safe_dump({'cwlVersion': CWL_VERSION}) == "cwlVersion: v1.2\n"


@pytest.mark.fast
def test_a_generated_tool_declares_v1_2_and_dumps() -> None:
    """The CommandLineTool generator emits v1.2, and its output serialises.

    This generator is the one that was stuck on `v1.0`, and it is also where
    an unserialisable version value would first reach disk.
    """
    tool = generate_CWL_CommandLineTool({}, {})
    assert tool['cwlVersion'] == 'v1.2'
    assert 'cwlVersion: v1.2' in yaml.safe_dump(tool)


@pytest.mark.fast
def test_every_real_cwl_version_is_admitted() -> None:
    """The enum covers the CWL spec's own list, so reading a foreign document
    that legitimately declares an older version is not an error."""
    for version in ('draft-2', 'v1.0', 'v1.1', 'v1.2', 'v1.2.0-dev5'):
        assert version in CWL_VERSIONS
