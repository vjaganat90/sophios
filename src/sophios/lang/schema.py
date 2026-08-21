"""Export a JSON Schema for Sophios, generated from the AST.

The AST is the source of truth. Every key in the exported schema comes from a
field's `Surface` declaration in `nodes.py`, and every construct comes from the
parser's dispatch tables — nothing here restates the shape of a document, so
nothing here can disagree with the parser about it. Add a field to `Step` and
either the schema moves or generation fails; there is no third outcome where
the schema quietly describes last month's language.

**What the schema can and cannot say.** Two limits are structural, not
oversights, and both follow from the language's own design:

*JSON has no YAML tags.* A validator sees a document after loading, so `!ii x`
is invisible to it. The schema therefore describes the **desugared** projection
(§6.1) — the shape `to_json` produces and the shape a YAML language server sees
once Sophios tags are resolved.

*Passthrough is open by definition.* The reference (§1) says anything outside
the interpreted set is copied through untouched, so the schema cannot close any
object that may carry passthrough CWL. That openness is declared in the AST as
`Shape.PASSTHROUGH`, not decided here.

The result is a deliberate over-approximation: everything the parser accepts
validates, and the structural mistakes the parser reports are rejected. It is
an editor aid, not a second implementation of the language.

See docs/sophios_language_reference.md.
"""
from dataclasses import fields
from types import MappingProxyType
from typing import Any, Final, Mapping, final

from .nodes import Document, OutputBinding, Shape, Step, WicSidecar, surface_of
from .parser import Forms, Grammar


@final
class Json:  # pylint: disable=too-few-public-methods  # a namespace, not a type
    """What this module needs to speak JSON Schema, and nothing more.

    The vocabulary being translated belongs to `nodes.Shape`; this namespace
    holds only the target format's own constants.
    """

    #: Draft this schema targets. 2020-12 is what current editors consume.
    DIALECT: Final = 'https://json-schema.org/draft/2020-12/schema'

    #: Stable identifier, so an editor can bind it to `*.wic` by URI.
    SCHEMA_ID: Final = 'https://raw.githubusercontent.com/PolusAI/sophios/master/sophios.schema.json'


#: How each declared shape is expressed in JSON Schema. A read-only view of
#: read-only fragments: callers get copies via `dict(...)` at use, so no caller
#: can reach in and change what every later export produces.
_SHAPE_SCHEMA: Final[Mapping[Shape, Mapping[str, Any]]] = MappingProxyType({
    Shape.INPUT_BINDINGS: {
        'description': 'Input bindings. Each input may be bound only once (§4.2).',
        'type': 'object',
        'additionalProperties': {'$ref': '#/$defs/inputValue'},
    },
    Shape.OUTPUT_BINDINGS: {
        'type': 'array',
        'items': {'$ref': '#/$defs/outputEntry'},
    },
    Shape.STEPS: {'$ref': '#/$defs/steps'},
    Shape.SIDECAR: {'$ref': '#/$defs/wicBlock'},
    Shape.SIDECAR_STEPS: {
        'description': 'Per-step metadata, keyed "(index, name)".',
        'type': 'object',
        'patternProperties': {Grammar.WIC_STEP_KEY_PATTERN: {'$ref': '#/$defs/wicBlock'}},
        'additionalProperties': False,
    },
    Shape.IDENTITY: {'type': 'string', 'minLength': 1},
})


def wic_schema() -> dict[str, Any]:
    """Build the JSON Schema describing a desugared Sophios document.

    Returned fresh each call: the result is mutable, and a shared instance a
    caller edited would corrupt every later export.
    """
    document = _object_schema(Document)
    return {
        '$schema': Json.DIALECT,
        '$id': Json.SCHEMA_ID,
        'title': 'Sophios workflow',
        'description': 'Desugared projection of a Sophios document. '
                       'See docs/sophios_language_reference.md.',
        **document,
        '$defs': _defs(),
    }


def _object_schema(node_type: type, *, omit: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Turn one AST node into a JSON Schema object, field by field.

    Walks `dataclasses.fields` rather than a hand-written list, so a field
    without a `Surface` declaration raises out of `surface_of` instead of being
    quietly left out of the schema.
    """
    properties: dict[str, Any] = {}
    open_object = False

    for declared in fields(node_type):
        form = surface_of(node_type, declared.name)
        if declared.name in omit or form.shape is Shape.INTERNAL:
            continue
        match form.shape:
            case Shape.PASSTHROUGH:
                # Not a key: the licence for every key nobody else claimed.
                open_object = True
            case Shape.INTERPRETED:
                # A closed set of CWL keys, listed for editor completion but
                # left unconstrained — Sophios reads them, CWL owns their shapes.
                for key in sorted(Grammar.INTERPRETED_STEP_KEYS):
                    properties[key] = {'description': f'Interpreted by Sophios: {key} (§4.3).'}
            case _ if form.key is not None:
                properties[form.key] = dict(_SHAPE_SCHEMA[form.shape])
            case _:
                # IDENTITY without a key is carried positionally, not as a key.
                continue

    return {'type': 'object', 'properties': properties, 'additionalProperties': open_object}


def _defs() -> dict[str, Any]:
    """The reusable shapes, each generated from the node it describes."""
    step_body = _step_body()
    return {
        'steps': {
            'description': 'A mapping keyed by step name, or a sequence of steps.',
            'oneOf': [
                {'type': 'object', 'additionalProperties': {'$ref': '#/$defs/stepBody'}},
                {'type': 'array', 'items': {'$ref': '#/$defs/sequenceStep'}},
            ],
        },
        'stepBody': step_body,
        'sequenceStep': _sequence_step(),
        'inputValue': _input_value(),
        'construct': _construct(),
        'outputEntry': _output_entry(),
        'wicBlock': _wic_block(),
    }


def _step_body() -> dict[str, Any]:
    """A step keyed by name. Null is legal: a step may have no body (§3.1)."""
    # `id` is omitted: in this form the step's name is the mapping key.
    body = _object_schema(Step, omit=frozenset({'id'}))
    return {**body, 'type': ['object', 'null']}


def _sequence_step() -> dict[str, Any]:
    """A step written in a sequence, which carries its own `id:`."""
    body = _object_schema(Step)
    return {
        **body,
        'description': 'A step written in a sequence: either it carries id:, '
                       'or it is a single-key mapping naming the step.',
    }


def _output_entry() -> dict[str, Any]:
    """One `out:` entry: a bare name, or a name bound to an edge."""
    identity = _SHAPE_SCHEMA[surface_of(OutputBinding, 'name').shape]
    return {
        'description': 'A bare output name, or a name bound to an edge definition.',
        'oneOf': [
            dict(identity),
            {'type': 'object', 'minProperties': 1, 'maxProperties': 1},
        ],
    }


def _wic_block() -> dict[str, Any]:
    """The `wic:` sidecar. Null is legal: a bare `wic:` is empty (§5)."""
    body = _object_schema(WicSidecar)
    return {
        **body,
        'description': 'Compiler metadata. Never emitted to CWL (§5).',
        'type': ['object', 'null'],
    }


def _input_value() -> dict[str, Any]:
    """One of the five input forms (§4.1).

    Unconstrained on purpose. A mapping whose single key is a construct key is
    a construct; any other value is an inline literal or an unresolved name,
    and the parser accepts all of them. `construct` is referenced so editors
    can offer the four keys as completions.
    """
    return {
        'description': 'An inline literal, edge definition, edge reference, '
                       'raw CWL reference, or unresolved name (§4.1).',
        'anyOf': [{'$ref': '#/$defs/construct'}, {}],
    }


def _construct() -> dict[str, Any]:
    """A desugared Sophios construct: a single-key mapping.

    Derived from the parser's dispatch table, so a construct added there
    appears here without anyone remembering to update a schema.
    """
    return {
        'type': 'object',
        'minProperties': 1,
        'maxProperties': 1,
        'properties': {key: {} for key in sorted(Forms.DESUGARED_KEYS)},
        'additionalProperties': False,
    }
