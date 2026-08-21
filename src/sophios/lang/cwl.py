"""The CWL substrate the Sophios language compiles onto.

The language reference pins Sophios to a specific CWL version and says the two
move together, so the version belongs to the language definition rather than to
whichever module happens to emit a document. Before this module there were six
places that named a version, and two of them disagreed with the other four: a
CommandLineTool generator still emitting `v1.0`, and a schema accepting any
non-empty string at all.

Import `CWL_VERSION` rather than writing a version literal. A test asserts that
no emitting path in the tree carries its own (see `tests/core/test_cwl_version.py`),
because the failure it prevents is silent: a document that declares the wrong
version still looks fine until a runner rejects a feature it should have had.

See docs/sophios_language_reference.md.
"""
from enum import StrEnum
from typing import Final


class CwlVersion(StrEnum):
    """Every version the CWL `CWLVersion` enumeration admits.

    Reproduced from the CWL v1.2 specification so a `cwlVersion` field can be
    validated against the real set instead of "any non-empty string". Sophios
    emits exactly one of these — `CWL_VERSION` — but must still recognise the
    others when reading documents it did not write.

    https://www.commonwl.org/v1.2/Workflow.html#CWLVersion
    """

    DRAFT_2 = 'draft-2'
    DRAFT_3_DEV1 = 'draft-3.dev1'
    DRAFT_3_DEV2 = 'draft-3.dev2'
    DRAFT_3_DEV3 = 'draft-3.dev3'
    DRAFT_3_DEV4 = 'draft-3.dev4'
    DRAFT_3_DEV5 = 'draft-3.dev5'
    DRAFT_3 = 'draft-3'
    DRAFT_4_DEV1 = 'draft-4.dev1'
    DRAFT_4_DEV2 = 'draft-4.dev2'
    DRAFT_4_DEV3 = 'draft-4.dev3'
    V1_0_DEV4 = 'v1.0.dev4'
    V1_0 = 'v1.0'
    V1_1_0_DEV1 = 'v1.1.0-dev1'
    V1_1 = 'v1.1'
    V1_2_0_DEV1 = 'v1.2.0-dev1'
    V1_2_0_DEV2 = 'v1.2.0-dev2'
    V1_2_0_DEV3 = 'v1.2.0-dev3'
    V1_2_0_DEV4 = 'v1.2.0-dev4'
    V1_2_0_DEV5 = 'v1.2.0-dev5'
    V1_2 = 'v1.2'


#: The version Sophios emits. Every generated document declares this one.
#:
#: A plain `str`, deliberately, not the enum member. `CwlVersion` is a
#: `StrEnum`, so it compares and formats like a string — but PyYAML dispatches
#: its representers on exact type, not `isinstance`, and refuses to serialise a
#: subclass it was not told about. Emitting the member would put an object into
#: every generated document that `yaml.safe_dump` cannot write. The enum stays
#: for validation; what gets embedded is the value.
CWL_VERSION: Final[str] = CwlVersion.V1_2.value

#: Every admissible version as plain strings, for JSON Schema `enum` fields.
CWL_VERSIONS: Final[tuple[str, ...]] = tuple(version.value for version in CwlVersion)
