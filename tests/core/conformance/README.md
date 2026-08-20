# Conformance corpus

`.wic` files copied from the corpus repositories at fixed commits. Together with
`docs/tutorials/` and `examples/`, this is the set `wic_version` 0.0.1 is
*defined* to accept.

`PINS.json` records the origin and commit each file came from.

## Why these are copied rather than read in place

The design requires the conformance corpus to be pinned:

> A specification validated against a moving branch is not fixed, so at
> specification time the conformance corpus is **pinned** to specific commits.
> The pin is a development-time artifact and does not affect the live E2E runs.
>
> — `design_docs/core-refactor-design.md` §5.6

A test that read the sibling repositories from disk would be checking whatever
those branches happen to say today, and would silently pass on a machine where
they are not checked out at all — which is every CI runner. Neither is a gate.
Copies at a recorded commit are checkable offline and cannot drift underneath
the specification.

The live end-to-end runs against those repositories' default branches are
unaffected and remain the integration test. This is a different job: it asks
whether the *grammar* still accepts what exists, not whether the workflows run.

## Updating a pin

Re-copy the files and update `PINS.json` in the same commit, so the corpus and
its provenance never disagree. Expect to do this deliberately, not routinely: a
pin that moves whenever upstream moves is not a pin.

If a file stops conforming, the default is to fix the file upstream rather than
bend the language (§5.6). A file that can be neither fixed nor accepted is
dropped from the copy with the reason recorded here.

## Exclusions

None. All 68 files parse, round-trip, and validate against the exported schema.
