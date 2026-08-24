"""Language-version resolution, surfacing, and override (CR-103).

Properties covered:
  P15  the resolved version is the highest that satisfies the source
  P16  no lower version is ever silently selected
  P17  untagged files resolve rather than fail
  P18  every successful compile reports a resolved version
  P19  the artifact annotation is present and keeps the CWL valid
  P20  an explicit setting always beats a file tag
  P21  one compilation yields exactly one version, tree-wide

Exactly one version exists today, so resolution against the real version list
always lands on 0.0.1. The *mechanism* is therefore tested against fabricated
version histories as well — the first real version bump is exactly when nobody
will want to discover the resolver was a stub that worked by coincidence.
"""
from pathlib import Path
import graphviz
import networkx as nx
import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import sophios.cli
import sophios.compiler
import sophios.post_compile
from sophios.lang import KNOWN_VERSIONS, LANG_VERSION, resolve_lang_version
from sophios.lang.diagnostics import Code, SophiosError
from sophios.lang.versions import ANNOTATION_KEY, ANNOTATION_NAMESPACE, ANNOTATION_NAMESPACE_URI
from sophios.wic_types import GraphData, GraphReps, StepId, Yaml, YamlTree

from .test_setup import tools_cwl

FAST = settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow], deadline=None)

#: Fabricated, ordered version histories: what the resolver will face someday.
histories = st.lists(
    st.integers(min_value=0, max_value=40).map(lambda n: f'0.0.{n}'),
    min_size=1, max_size=6, unique=True,
).map(lambda vs: tuple(sorted(vs, key=lambda v: int(v.rsplit('.', 1)[1]))))


def _compile(yml: Yaml, lang_version: str | None = None) -> Yaml:
    """Compile one in-memory workflow and return the emitted CWL."""
    options, graph_settings, tag_paths = sophios.cli.get_dicts_for_compilation()
    if lang_version is not None:
        options['lang_version'] = lang_version
    graph = GraphReps(graphviz.Digraph(name='cluster_v'), nx.DiGraph(), GraphData('v'))
    info = sophios.compiler.compile_workflow(YamlTree(StepId('lang_version', 'global'), yml),
                                             options, graph_settings, tag_paths,
                                             [], [graph], {}, {}, {}, {},
                                             tools_cwl, True, relative_run_path=True, testing=True)
    compiled: Yaml = info.rose.data.compiled_cwl
    return compiled


TOUCH: Yaml = {'steps': [{'id': 'touch', 'in': {'filename': {'wic_inline_input': 'empty.txt'}}}]}


# --------------------------------------------------------------------------
# P15 / P16 / P17 — the resolution rule, over fabricated histories
# --------------------------------------------------------------------------


@pytest.mark.fast
@given(histories)
@FAST
def test_p15_untagged_resolves_to_the_newest(known: tuple[str, ...]) -> None:
    """P15: with nothing to satisfy, the highest known version is chosen."""
    assert resolve_lang_version(None, (), known=known) == known[-1]


@pytest.mark.fast
@given(histories, st.data())
@FAST
def test_p16_no_lower_version_is_silently_selected(known: tuple[str, ...], data: st.DataObject) -> None:
    """P16: a pin is the only thing that moves resolution below the newest,
    and a pin is the author's word, not silence."""
    pin = data.draw(st.sampled_from(known))
    resolved = resolve_lang_version(None, (pin,), known=known)
    assert resolved == pin
    # Order is history position, not string order: '0.0.10' is newer than '0.0.2'.
    untagged = resolve_lang_version(None, (), known=known)
    assert known.index(untagged) >= known.index(resolved)


@pytest.mark.fast
@given(histories)
@FAST
def test_p17_untagged_never_fails(known: tuple[str, ...]) -> None:
    """P17: resolution of an untagged tree cannot fail."""
    resolve_lang_version(None, (), known=known)  # must not raise


@pytest.mark.fast
def test_unknown_versions_are_reported_not_coerced() -> None:
    """Asking for a version that does not exist is an error naming the known
    ones — never a silent fallback to something else."""
    for request, pins in (('9.9.9', ()), (None, ('9.9.9',))):
        with pytest.raises(SophiosError) as caught:
            resolve_lang_version(request, pins)
        assert caught.value.diagnostics[0].code is Code.UNKNOWN_LANG_VERSION
        assert LANG_VERSION in caught.value.diagnostics[0].message


# --------------------------------------------------------------------------
# P20 / P21 — precedence and tree-wide oneness
# --------------------------------------------------------------------------


@pytest.mark.fast
@given(histories, st.data())
@FAST
def test_p20_explicit_beats_any_tag(known: tuple[str, ...], data: st.DataObject) -> None:
    """P20: the explicit setting wins regardless of what the tree pins."""
    explicit = data.draw(st.sampled_from(known))
    pins = tuple(data.draw(st.lists(st.sampled_from(known), max_size=4)))
    assert resolve_lang_version(explicit, pins, known=known) == explicit


@pytest.mark.fast
@given(histories, st.data())
@FAST
def test_p21_one_version_or_a_conflict_report(known: tuple[str, ...], data: st.DataObject) -> None:
    """P21: agreeing pins resolve to their one version; disagreeing pins are
    a reported conflict, never an average or a quiet winner."""
    pins = tuple(data.draw(st.lists(st.sampled_from(known), min_size=1, max_size=4)))
    if len(set(pins)) == 1:
        assert resolve_lang_version(None, pins, known=known) == pins[0]
    else:
        with pytest.raises(SophiosError) as caught:
            resolve_lang_version(None, pins, known=known)
        assert caught.value.diagnostics[0].code is Code.LANG_VERSION_CONFLICT


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p21_conflicting_pins_across_a_tree_are_caught_at_the_root() -> None:
    """P21, integrated: a subworkflow pin that disagrees with the root's is a
    conflict at compile time — the walk sees the whole merged tree."""
    tree: Yaml = {
        'wic': {'lang_version': '0.0.1'},
        'steps': [{'id': 'touch',
                   'in': {'filename': {'wic_inline_input': 'empty.txt'}},
                   'wic': {'lang_version': '9.9.9'}}],
    }
    with pytest.raises(SophiosError) as caught:
        _compile(tree)
    assert caught.value.diagnostics[0].code is Code.UNKNOWN_LANG_VERSION


# --------------------------------------------------------------------------
# P18 / P19 — surfacing
# --------------------------------------------------------------------------


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p18_every_compile_reports_its_version() -> None:
    """P18: the emitted artifact carries the resolved version, and so does the
    tagged and the explicitly-pinned compile."""
    assert _compile(TOUCH)[ANNOTATION_KEY] == LANG_VERSION
    assert _compile({'wic': {'lang_version': '0.0.1'}, **TOUCH})[ANNOTATION_KEY] == '0.0.1'
    assert _compile(TOUCH, lang_version='0.0.1')[ANNOTATION_KEY] == '0.0.1'


@pytest.mark.skip_pypi_ci
@pytest.mark.fast
def test_p18_the_python_api_surfaces_the_version() -> None:
    """P18: `CompiledWorkflow.lang_version` names the version, no digging."""
    from sophios.api.python.tool_builder import CommandLineTool, Input, Inputs, Output, Outputs, cwl
    from sophios.api.python.workflow import Step, Workflow

    emit = (CommandLineTool('emit_text',
                            Inputs(message=Input(cwl.string, position=1)),
                            Outputs(file=Output(cwl.file, glob='stdout.txt')))
            .base_command('echo')
            .stdout('stdout.txt'))
    step = Step(emit)
    step.inputs.message = 'hello'
    compiled = Workflow([step], 'p18_version').compile()
    assert compiled.lang_version == LANG_VERSION
    assert compiled.cwl_workflow[ANNOTATION_KEY] == LANG_VERSION


@pytest.mark.skip_pypi_ci
@pytest.mark.slow
def test_p19_annotation_is_declared_and_the_cwl_stays_valid() -> None:
    """P19: the annotation is a namespaced extension field, its namespace is
    declared, and cwltool still accepts the artifact as CWL v1.2."""
    import cwltool.main  # pylint: disable=import-outside-toplevel  # expensive; slow lane only

    options, graph_settings, tag_paths = sophios.cli.get_dicts_for_compilation()
    graph = GraphReps(graphviz.Digraph(name='cluster_v'), nx.DiGraph(), GraphData('v'))
    info = sophios.compiler.compile_workflow(YamlTree(StepId('lang_version', 'global'), TOUCH),
                                             options, graph_settings, tag_paths,
                                             [], [graph], {}, {}, {}, {},
                                             tools_cwl, True, relative_run_path=True, testing=True)
    inlined = sophios.post_compile.cwl_inline_runtag(info.rose).data.compiled_cwl

    assert inlined[ANNOTATION_KEY] == LANG_VERSION
    assert inlined['$namespaces'][ANNOTATION_NAMESPACE] == ANNOTATION_NAMESPACE_URI

    target = Path('autogenerated') / 'p19_annotated.cwl'
    target.parent.mkdir(exist_ok=True)
    target.write_text(yaml.safe_dump(inlined, sort_keys=False), encoding='utf-8')
    assert cwltool.main.main(['--validate', '--quiet', str(target)]) == 0


# --------------------------------------------------------------------------
# Sanity
# --------------------------------------------------------------------------


@pytest.mark.fast
def test_exactly_one_version_exists_today() -> None:
    """When this fails, versions.py has grown a second entry — go make sure
    the resolution table in the reference (§7) still tells the truth."""
    assert KNOWN_VERSIONS == ('0.0.1',)
    assert LANG_VERSION == '0.0.1'
