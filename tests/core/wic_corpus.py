"""The `.wic` conformance corpus: every file the language is defined to accept.

Two sources, and the distinction matters:

  * **In-repo** — `docs/tutorials/` and `examples/`, read where they live, so a
    tutorial that stops parsing fails the build that broke it.
  * **Pinned** — copies of the `mm-workflows` and `image-workflows` `.wic`
    files, taken at the commits recorded in `conformance/PINS.json`.

The design names all four locations as the set `wic_version` 0.0.1 is defined to
accept, and makes "conformance corpus validated" the gate for Spec 1
(`design_docs/core-refactor-design.md` §3, §5.6). Reading the sibling
repositories from disk would not be that gate: it would check whatever their
branches say today, and would vanish entirely on a machine that does not have
them checked out — which is every CI runner. Hence copies at a fixed commit.

See `conformance/README.md`.
"""
import json
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]

#: Directories read in place.
IN_REPO_DIRS: Final = (REPO_ROOT / 'docs' / 'tutorials', REPO_ROOT / 'examples')

#: Where the pinned copies live, alongside their provenance.
CONFORMANCE_DIR: Final = Path(__file__).resolve().parent / 'conformance'
PINS_FILE: Final = CONFORMANCE_DIR / 'PINS.json'


def _in_repo() -> list[Path]:
    """Every `.wic` that lives in this repository."""
    return sorted(path for directory in IN_REPO_DIRS if directory.is_dir() for path in directory.rglob('*.wic'))


def _pinned() -> list[Path]:
    """Every pinned copy, listed from `PINS.json` rather than globbed.

    Going through the manifest means a file deleted from the tree but still
    recorded fails loudly, instead of quietly shrinking the corpus — which is
    exactly the way a conformance gate stops being one.
    """
    if not PINS_FILE.is_file():
        return []
    pins = json.loads(PINS_FILE.read_text(encoding='utf-8'))
    return [CONFORMANCE_DIR / source / relative
            for source, pin in sorted(pins.items())
            for relative in pin['files']]


#: Everything, sorted so test ids are stable across runs.
CORPUS: Final = tuple(_in_repo() + _pinned())

#: The in-repo half on its own, for tests that need a file's real location.
IN_REPO_CORPUS: Final = tuple(_in_repo())


def corpus_id(path: Path) -> str:
    """Name a corpus file in test output, disambiguating repeated basenames."""
    try:
        return str(path.relative_to(CONFORMANCE_DIR))
    except ValueError:
        return str(path.relative_to(REPO_ROOT))
