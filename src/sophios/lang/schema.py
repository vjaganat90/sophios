"""Export a JSON Schema for Sophios, for editors.

The schema describes the desugared projection (language spec §2), since JSON
has no YAML tags, and is a deliberate over-approximation — an editor aid, not
a second implementation of the language. The keys Sophios reads on a step, the
construct keys, the `wic:` step-key patterns and the `wic:` block's keys and
value schemas are the parser's own tables, so the two cannot disagree on them.
"""
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .cwl import CWL_VERSIONS
from .parser import Grammar


def wic_schema() -> dict[str, Any]:
    """Build the JSON Schema describing a desugared Sophios document.

    Returned fresh each call, with nothing aliased inside, so the caller may
    annotate or edit the result in place.
    """
    step_entry = _wic_block(Grammar.SIDECAR_STEP_VALUES, 'Metadata for the step this entry names (.wic reference §7).')
    # A `wic: steps:` entry holds its keys directly, under a `wic:` wrapper, or both.
    step_entry['properties']['wic'] = {'$ref': '#/$defs/wicStepBlock'}
    return {
        # 2020-12 is the draft current editors consume; the id is a URN, since nothing publishes a URL for the schema.
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:sophios:schema:lang',
        'title': 'Sophios workflow',
        'description': 'Desugared projection of a Sophios document. '
                       'See docs/wic-reference.md.',
        'type': 'object',
        'properties': {
            'steps': {'$ref': '#/$defs/steps'},
            'wic': {'$ref': '#/$defs/wicBlock'},
            'cwlVersion': {
                'enum': list(CWL_VERSIONS),
                'description': 'Ignored in favour of the substrate version, '
                               'but must be one the toolchain runs (language spec §1).',
            },
        },
        'additionalProperties': True,  # every other key is CWL
        '$defs': {
            'steps': {
                'description': 'A mapping keyed by step name, or a sequence of steps.',
                'oneOf': [
                    {'type': 'object', 'additionalProperties': {'$ref': '#/$defs/stepBody'}},
                    {'type': 'array', 'items': {'$ref': '#/$defs/sequenceStep'}},
                ],
            },
            # A step keyed by name, which is its id. Null is legal: a step may have no body (.wic reference §2.1).
            'stepBody': {'type': ['object', 'null'], **_step({})},
            'sequenceStep': {
                'type': 'object',
                **_step({'id': {'type': 'string', 'minLength': 1}}),  # wic007
                'required': ['id'],
                'description': 'A step written in a sequence, carrying its name in an id: key.',
            },
            # Unconstrained on purpose; `construct` is referenced only so editors offer the construct keys.
            'inputValue': {
                'description': 'An inline literal, edge reference, raw CWL reference, '
                               'unresolved name, or step-input record (.wic reference §3.1).',
                'anyOf': [{'$ref': '#/$defs/construct'}, {}],
            },
            'construct': {
                'type': 'object',
                'minProperties': 1,
                'maxProperties': 1,
                'properties': {key: {} for key in sorted(Grammar.DESUGARED_KEYS)},
                'additionalProperties': False,
            },
            'outputEntry': {
                'description': 'A bare output name, or a name bound to an edge definition.',
                'oneOf': [
                    {'type': 'string'},
                    {'type': 'object', 'minProperties': 1, 'maxProperties': 1},
                ],
            },
            # Null is legal: a bare `wic:` is empty (.wic reference §7).
            'wicBlock': _wic_block(Grammar.SIDECAR_VALUES,
                                   'Compiler metadata. Never emitted to CWL (.wic reference §7).'),
            'wicStepBlock': _wic_block(Grammar.SIDECAR_STEP_VALUES, step_entry['description']),
            'wicStepEntry': step_entry,
        },
    }


def _step(identity: dict[str, Any]) -> dict[str, Any]:
    """A step's own keys after `identity`, its `id:` where it carries one. Any other key is CWL: the object is open."""
    return {
        'properties': {
            **identity,
            'in': {
                'description': 'Input bindings. Each input may be bound only once (.wic reference §3.8).',
                'type': 'object',
                'additionalProperties': {'$ref': '#/$defs/inputValue'},
            },
            'out': {'type': 'array', 'items': {'$ref': '#/$defs/outputEntry'}},
            # Listed for editor completion and left unconstrained: Sophios reads them, CWL owns their shapes.
            **{key: {'description': f'Interpreted by Sophios: {key} (.wic reference §2.2).'}
               for key in sorted(Grammar.INTERPRETED_STEP_KEYS)},
        },
        'additionalProperties': True,
    }


def _wic_block(values: Mapping[str, Mapping[str, Any]], description: str) -> dict[str, Any]:
    """A `wic:` block: `steps:` and one property per key of `values`, with the schema the parser checks it against.

    The block is not passthrough, so it is the one object the schema closes.
    """
    return {
        'type': ['object', 'null'],
        'properties': {
            'steps': {
                'description': 'Per-step metadata, keyed "(index, name)" or by a unique step id.',
                'type': 'object',
                'patternProperties': {pattern.pattern: {'$ref': '#/$defs/wicStepEntry'}
                                      for pattern in (Grammar.WIC_STEP_KEY, Grammar.WIC_STEP_ID)},
                'additionalProperties': False,
            },
            **{key: deepcopy(schema) for key, schema in sorted(values.items())},
        },
        'additionalProperties': False,
        'description': description,
    }
