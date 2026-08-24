"""The library reports failures; only the CLI adapter exits (CR-104).

Properties covered:
  P22  compilation never terminates the process
  P23  every failure path produces at least one diagnostic
  P24  CLI exit codes match pre-change behaviour

P22 is enforced two ways. Statically: no core module except the CLI entry
point contains a `sys.exit` call — the same scan shape as P14, because the
failure it guards is equally silent. Dynamically: the fuzz suite compiles
generated documents with no `SystemExit` arm left in its handler, so a
process-killing path is a test failure there rather than a whitelisted event.

P23 holds by construction — `SophiosError` cannot be built with zero
diagnostics — plus one test per converted site proving the site actually
raises it with the messages it used to print.

See design_docs/core-refactor-design.md §3, deliberate exception 1.
"""
import ast as python_ast
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

from sophios import post_compile
from sophios.lang.diagnostics import Code, Diagnostic, Severity, SophiosError
from sophios.python_cwl_adapter import check_args_match_inputs

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
SRC: Final = REPO_ROOT / 'src' / 'sophios'

#: The one module allowed to exit: the CLI adapter. Everything else reports.
CLI_ADAPTER: Final = SRC / 'main.py'

#: The contrib zone is out of scope for the core guarantee; its own entry
#: points (REST server startup and the like) are someone's process to manage.
CONTRIB: Final = SRC / 'contrib'


def _core_files() -> list[Path]:
    """Every core Python file except the CLI adapter."""
    return sorted(path for path in SRC.rglob('*.py')
                  if path != CLI_ADAPTER and CONTRIB not in path.parents)


def _exit_calls(tree: python_ast.AST) -> list[int]:
    """Line numbers of every `sys.exit(...)` / `exit(...)` / `quit(...)` call."""
    found: list[int] = []
    for node in python_ast.walk(tree):
        match node:
            case python_ast.Call(func=python_ast.Attribute(value=python_ast.Name(id='sys'), attr='exit')):
                found.append(node.lineno)
            case python_ast.Call(func=python_ast.Name(id='exit' | 'quit')):
                found.append(node.lineno)
    return found


# --------------------------------------------------------------------------
# P22 — the process is not the library's to terminate
# --------------------------------------------------------------------------


@pytest.mark.fast
@pytest.mark.parametrize('path', _core_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_p22_no_core_module_calls_exit(path: Path) -> None:
    """P22: no core library module contains a process-terminating call.

    The dynamic half of P22 lives in the fuzz suite, whose exception handler
    no longer has a `SystemExit` arm at all.
    """
    lines = _exit_calls(python_ast.parse(path.read_text(encoding='utf-8'), str(path)))
    assert not lines, (
        f'{path.relative_to(REPO_ROOT)} calls exit at lines {lines}; '
        f'raise SophiosError and let the CLI adapter decide the exit code'
    )


@pytest.mark.fast
def test_p22_the_scan_can_actually_fail() -> None:
    """The scan detects each spelling it claims to, so P22 is not vacuous."""
    for source in ('import sys\nsys.exit(1)', 'exit(1)', 'quit()'):
        assert _exit_calls(python_ast.parse(source)), f'scan missed: {source}'


@pytest.mark.fast
def test_p22_the_cli_adapter_is_the_exception() -> None:
    """`main.py` still exits — that is its job, and the scan must not creep
    into forbidding it, or exit codes stop being anyone's responsibility."""
    lines = _exit_calls(python_ast.parse(CLI_ADAPTER.read_text(encoding='utf-8')))
    assert lines, 'main.py no longer exits anywhere; P24 has lost its subject'


# --------------------------------------------------------------------------
# P23 — a failure always has something to say
# --------------------------------------------------------------------------


@pytest.mark.fast
def test_p23_an_error_with_no_diagnostics_is_unrepresentable() -> None:
    """P23 by construction: the exception cannot exist empty."""
    with pytest.raises(ValueError):
        SophiosError([])


@pytest.mark.fast
def test_p23_str_carries_every_message() -> None:
    """What an embedder logs by default includes each diagnostic, so catching
    without inspecting `.diagnostics` still loses nothing."""
    error = SophiosError.error(Code.UNRESOLVED_INPUT, 'first', 'second')
    assert 'first' in str(error) and 'second' in str(error)
    assert len(error.diagnostics) == 2


@pytest.mark.fast
def test_p23_spanless_diagnostics_print_without_a_location() -> None:
    """Compile-phase failures may not know a line; the string form must not
    invent one."""
    diagnostic = Diagnostic(Severity.ERROR, Code.MISSING_INPUT_FILE, 'gone.txt missing')
    assert str(diagnostic) == 'error [wic016] gone.txt missing'


# --- the converted sites, one by one ---------------------------------------


@pytest.mark.fast
def test_script_argument_mismatch_reports(tmp_path: Path) -> None:
    """`python_cwl_adapter` reports the mismatch it used to print-and-exit."""
    module = ModuleType('fake_workflow_script')
    module.inputs = {'expected_arg': int}  # type: ignore[attr-defined]

    with pytest.raises(SophiosError) as caught:
        check_args_match_inputs(module, {'unexpected_arg': 1}, check=True)

    messages = [d.message for d in caught.value.diagnostics]
    assert any('unexpected_arg' in m for m in messages)
    assert any('expected_arg' in m for m in messages)
    assert all(d.code is Code.SCRIPT_ARGUMENT_MISMATCH for d in caught.value.diagnostics)


@pytest.mark.fast
def test_missing_input_file_reports(tmp_path: Path) -> None:
    """`stage_input_files` reports the absent file instead of exiting."""
    inputs = {'in_file': {'class': 'File', 'location': 'does_not_exist.txt'}}

    with pytest.raises(SophiosError) as caught:
        post_compile.stage_input_files(inputs, tmp_path, str(tmp_path / 'out'), throw=True)

    assert caught.value.diagnostics[0].code is Code.MISSING_INPUT_FILE
    assert 'does_not_exist.txt' in caught.value.diagnostics[0].message


@pytest.mark.fast
def test_missing_container_engine_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    """The docker check reports the same installation advice it printed."""
    def command_not_found(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError('docker')

    monkeypatch.setattr(post_compile.sub, 'run', command_not_found)

    with pytest.raises(SophiosError) as caught:
        post_compile.verify_container_engine_config('docker', False)

    assert caught.value.diagnostics[0].code is Code.CONTAINER_ENGINE_UNAVAILABLE
    assert any('--ignore_docker_install' in d.message for d in caught.value.diagnostics)


@pytest.mark.fast
def test_ignored_container_check_stays_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The escape hatch still works: --ignore_docker_install means no report."""
    def command_not_found(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError('docker')

    monkeypatch.setattr(post_compile.sub, 'run', command_not_found)
    post_compile.verify_container_engine_config('docker', True)  # must not raise


# --------------------------------------------------------------------------
# P24 — the CLI still speaks exit codes
# --------------------------------------------------------------------------


@pytest.mark.fast
def test_p24_cli_converts_a_report_to_exit_1(monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    """A reported failure leaves the CLI with the exact old behaviour: the
    messages on stdout, exit code 1, no traceback."""
    from sophios import main as cli

    def reports(*_args: object, **_kwargs: object) -> None:
        raise SophiosError.error(Code.UNRESOLVED_INPUT,
                                 'Warning! Did you forget to use !ii before x in demo.wic?',
                                 'If you want to compile the workflow anyway, use --allow_raw_cwl')

    monkeypatch.setattr(cli, '_main', reports)

    with pytest.raises(SystemExit) as caught:
        cli.main()

    assert caught.value.code == 1
    printed = capsys.readouterr().out
    assert 'Did you forget to use !ii' in printed
    assert '--allow_raw_cwl' in printed


@pytest.mark.fast
def test_p24_success_does_not_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clean run returns instead of raising, exactly as before."""
    from sophios import main as cli
    monkeypatch.setattr(cli, '_main', lambda: None)
    assert cli.main() is None  # type: ignore[func-returns-value]
