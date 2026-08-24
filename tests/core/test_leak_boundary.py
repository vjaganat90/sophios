"""The leak boundary, checked against the real compiler (CR-102, T1.4).

Properties covered:
  P10  passthrough keys survive compilation byte-identically
  P11  no key is both interpreted and passed through
  P12  the interpreted set is exhaustive — the compiler is inert to the rest
  P13  the residue validates as CWL v1.2 under cwltool

These run the actual `compile_workflow`, not the syntax layer, because the
boundary being specified is the compiler's behaviour. The syntax layer's
partition (P11) is checked exhaustively over the declared set as well, since
that is what the schema and the reference derive from.

ONE DOCUMENTED EXCEPTION (CE-05). `$namespaces` is not pure passthrough: the
compiler merges its own `edam` binding over the user's, so a workflow that
binds the `edam` prefix itself loses that binding in the output. Every other
namespace survives, and `$schemas` is append-only. The properties below assert
the behaviour that is true, and the collision is pinned as its own test rather
than papered over by a weaker property.

See design_docs/core-refactor-design.md §5.4.
"""
from pathlib import Path
from typing import Any

import graphviz
import networkx as nx
import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sophios.cli
import sophios.compiler
import sophios.post_compile
from sophios.lang import Grammar, parse
from sophios.wic_types import GraphData, GraphReps, StepId, Yaml, YamlTree

from .test_setup import tools_cwl

#: Step keys the language claims for itself, and therefore not passthrough.
CLAIMED_STEP_KEYS = frozenset({'id', 'in', 'out'}) | Grammar.INTERPRETED_STEP_KEYS

FAST = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)
COMPILED = settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)


def _compile(yml: Yaml) -> Yaml:
    """Compile one in-memory workflow and return the emitted CWL."""
    tree = YamlTree(StepId('leak_boundary', 'global'), yml)
    graph = GraphReps(graphviz.Digraph(name='cluster_leak'), nx.DiGraph(), GraphData('leak'))
    options, graph_settings, tag_paths = sophios.cli.get_dicts_for_compilation()
    info = sophios.compiler.compile_workflow(tree, options, graph_settings, tag_paths,
                                             [], [graph], {}, {}, {}, {},
                                             tools_cwl, True, relative_run_path=True, testing=True)
    compiled: Yaml = info.rose.data.compiled_cwl
    return compiled


def _step(cwl: Yaml) -> Yaml:
    """The single step of a compiled one-step workflow."""
    steps = cwl['steps']
    found: Yaml = next(iter(steps.values())) if isinstance(steps, dict) else steps[0]
    return found


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------

#: Keys that are definitely not claimed by the language. Lowercase ascii,
#: filtered rather than constructed, so the claim set stays the authority.
passthrough_keys = st.text('abcdefghijklmnopqrstuvwxyz_', min_size=3, max_size=12) \
    .filter(lambda k: k not in CLAIMED_STEP_KEYS)

#: JSON-shaped values, byte-comparable after a round trip.
passthrough_values = st.recursive(
    st.one_of(st.integers(min_value=-100, max_value=100), st.booleans(),
              st.text('abc xyz', max_size=8), st.none()),
    lambda children: st.one_of(st.lists(children, max_size=3),
                               st.dictionaries(st.text('abc', min_size=1, max_size=5), children, max_size=3)),
    max_leaves=8,
)


def _touch_workflow(extra_step_keys: dict[str, Any], extra_top_keys: dict[str, Any]) -> Yaml:
    """A minimal real workflow carrying the given passthrough freight."""
    return {
        **extra_top_keys,
        'steps': [{'id': 'touch',
                   'in': {'filename': {'wic_inline_input': 'empty.txt'}},
                   **extra_step_keys}],
    }


# --------------------------------------------------------------------------
# P10 — passthrough fidelity
# --------------------------------------------------------------------------


@pytest.mark.skip_pypi_ci
@pytest.mark.slow
@given(st.dictionaries(passthrough_keys, passthrough_values, min_size=1, max_size=4))
@COMPILED
def test_p10_step_passthrough_is_byte_identical(freight: dict[str, Any]) -> None:
    """P10: a step key outside the claimed set survives compilation unchanged."""
    compiled = _compile(_touch_workflow(freight, {}))
    step = _step(compiled)
    for key, value in freight.items():
        assert step[key] == value, f'{key} was altered by compilation'


@pytest.mark.skip_pypi_ci
@pytest.mark.slow
@given(st.dictionaries(passthrough_keys.filter(lambda k: k not in ('steps', 'wic')),
                       passthrough_values, min_size=1, max_size=3))
@COMPILED
def test_p10_top_level_passthrough_is_byte_identical(freight: dict[str, Any]) -> None:
    """P10: an uninterpreted top-level key survives compilation unchanged."""
    compiled = _compile(_touch_workflow({}, freight))
    for key, value in freight.items():
        assert compiled[key] == value, f'{key} was altered by compilation'


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p10_user_namespaces_survive_except_edam() -> None:
    """P10, qualified: `$namespaces` keeps every user binding but `edam`.

    CE-05. The compiler merges `{'edam': the canonical URL}` over the user's
    mapping, so a user binding of the `edam` prefix specifically is replaced.
    Pinned as the actual behaviour; if merging ever becomes pure passthrough,
    this test should fail and be inverted deliberately, not silently.
    """
    compiled = _compile(_touch_workflow({}, {'$namespaces': {'mine': 'https://mine/', 'edam': 'https://not-edam/'}}))
    assert compiled['$namespaces']['mine'] == 'https://mine/'
    assert compiled['$namespaces']['edam'] == 'https://edamontology.org/'  # user's binding lost


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p10_user_schemas_are_kept_and_appended_to() -> None:
    """`$schemas` is append-only: user entries survive, Sophios adds its own."""
    compiled = _compile(_touch_workflow({}, {'$schemas': ['https://mine/schema.owl']}))
    assert 'https://mine/schema.owl' in compiled['$schemas']


# --------------------------------------------------------------------------
# P11 — the partition is a partition
# --------------------------------------------------------------------------


@pytest.mark.fast
@pytest.mark.parametrize('key', sorted(Grammar.INTERPRETED_STEP_KEYS))
def test_p11_every_declared_key_is_interpreted(key: str) -> None:
    """P11, exhaustive half: each declared key routes to `interpreted`."""
    result = parse(f'steps:\n- id: s\n  {key}: x\n', 'p11.wic')
    assert result.document is not None
    step = result.document.steps[0]
    assert key in dict(step.interpreted)
    assert key not in dict(step.passthrough)


@pytest.mark.fast
@given(passthrough_keys)
@FAST
def test_p11_no_key_lands_on_both_sides(key: str) -> None:
    """P11, generated half: any other key routes to passthrough, never both."""
    result = parse(f'steps:\n- id: s\n  {key}: x\n', 'p11.wic')
    assert result.document is not None
    step = result.document.steps[0]
    interpreted, passthrough = dict(step.interpreted), dict(step.passthrough)
    assert key in passthrough
    assert key not in interpreted
    assert not set(interpreted) & set(passthrough)


# --------------------------------------------------------------------------
# P12 — the compiler is inert outside the declared set
# --------------------------------------------------------------------------


@pytest.mark.skip_pypi_ci
@pytest.mark.slow
@given(passthrough_keys, passthrough_values)
@COMPILED
def test_p12_unknown_keys_change_nothing_else(key: str, value: Any) -> None:
    """P12: adding an uninterpreted key changes exactly that key and nothing
    else in the output — the observable meaning of "not interpreted".
    """
    without = _compile(_touch_workflow({}, {}))
    with_key = _compile(_touch_workflow({key: value}, {}))

    step_without, step_with = _step(without), _step(with_key)
    assert step_with.pop(key) == value
    assert step_with == step_without, f'{key} altered more than itself'


# --------------------------------------------------------------------------
# P13 — the residue is real CWL v1.2
# --------------------------------------------------------------------------

#: Passthrough spelled in CWL vocabulary, because CWL v1.2 itself rejects
#: unknown step fields — arbitrary keys are covered by P10, but a document
#: carrying them is not *valid CWL*, and P13 is about validity.
cwl_passthrough = st.fixed_dictionaries(
    {},
    optional={
        'label': st.text('abc xyz', min_size=1, max_size=20),
        'doc': st.text('abc xyz.', min_size=1, max_size=40),
        'hints': st.just({'LoadListingRequirement': {'loadListing': 'shallow_listing'}}),
    },
)


@pytest.mark.skip_pypi_ci
@pytest.mark.slow
@given(cwl_passthrough)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_p13_residue_validates_as_cwl_v1_2(freight: dict[str, Any]) -> None:
    """P13: strip the Sophios syntax, inline the tools, and cwltool agrees the
    residue is CWL v1.2."""
    import cwltool.main  # pylint: disable=import-outside-toplevel  # expensive; slow lane only

    tree = YamlTree(StepId('leak_boundary', 'global'), _touch_workflow(freight, {}))
    graph = GraphReps(graphviz.Digraph(name='cluster_leak'), nx.DiGraph(), GraphData('leak'))
    options, graph_settings, tag_paths = sophios.cli.get_dicts_for_compilation()
    info = sophios.compiler.compile_workflow(tree, options, graph_settings, tag_paths,
                                             [], [graph], {}, {}, {}, {},
                                             tools_cwl, True, relative_run_path=True, testing=True)
    inlined = sophios.post_compile.cwl_inline_runtag(info.rose).data.compiled_cwl

    target = Path('autogenerated') / 'p13_residue.cwl'
    target.parent.mkdir(exist_ok=True)
    target.write_text(yaml.safe_dump(inlined, sort_keys=False), encoding='utf-8')

    assert cwltool.main.main(['--validate', '--quiet', str(target)]) == 0
    assert inlined['cwlVersion'] == 'v1.2'

# --------------------------------------------------------------------------
# P08 — the --allow_raw_cwl escape hatch still works
# --------------------------------------------------------------------------


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p08_allow_raw_cwl_is_the_difference_between_report_and_compile() -> None:
    """P08: a bare unresolved name is reported without the flag and compiles
    with it — the flag's one-line definition, observed at the boundary."""
    from sophios.lang.diagnostics import Code, SophiosError

    bare: Yaml = {'steps': [{'id': 'touch', 'in': {'filename': 'not_a_workflow_input'}}]}

    with pytest.raises(SophiosError) as caught:
        _compile(bare)
    assert caught.value.diagnostics[0].code is Code.UNRESOLVED_INPUT
    assert '!ii' in caught.value.diagnostics[0].message

    options, graph_settings, tag_paths = sophios.cli.get_dicts_for_compilation()
    options = {**options, 'allow_raw_cwl': True}
    graph = GraphReps(graphviz.Digraph(name='cluster_p08'), nx.DiGraph(), GraphData('p08'))
    info = sophios.compiler.compile_workflow(YamlTree(StepId('p08', 'global'), bare),
                                             options, graph_settings, tag_paths,
                                             [], [graph], {}, {}, {}, {},
                                             tools_cwl, True, relative_run_path=True, testing=True)
    assert info.rose.data.compiled_cwl['class'] == 'Workflow'
