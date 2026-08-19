# The `.wic` Language Reference

**Version:** `wic_version` 0.0.1
**Substrate:** CWL v1.2

This is the human-readable definition of the Sophios workflow language. The
executable definition is `sophios.lang` — the typed AST and parser — and the
two are meant to agree. Where they disagree, that is a bug in one of them.

Sophios has **two front-ends that produce the same language**: `.wic` files
written by hand, and the Python API. Both are defined by this document, and
§6 states what each is obliged to do.

---

## 1. What kind of language this is

`.wic` is a **leaky abstraction over CWL, deliberately**. You write shorthand
for the common case and drop into raw CWL for anything the shorthand does not
cover. Sealing the abstraction would mean re-inventing CWL one feature at a
time and asking users to wait.

The abstraction leaks in three ways, and knowing which is which is the whole
point of this document:

| Category | What Sophios does | Examples |
|---|---|---|
| **wic-owned** | Consumes it; never appears in the output | `!ii`, `!&`, `!*`, `!cwl`, the `wic:` block |
| **Interpreted CWL** | Reads it *and acts on it* | `scatter`, `scatterMethod`, `when`, inline `run` |
| **Passthrough CWL** | Copies it out unchanged | `$namespaces`, `$schemas`, `requirements`, `hints`, everything else |

The interpreted set is closed and listed in §4.2. **Anything not in it is
passthrough, by definition.** That rule is what makes the leak a contract
rather than a surprise.

---

## 2. Document structure

A `.wic` document is a YAML mapping. Every key is optional.

```yaml
wic:            # optional  — compiler metadata, never emitted to CWL
steps:          # the workflow's steps
inputs:         # CWL workflow inputs        (passthrough)
outputs:        # CWL workflow outputs       (passthrough)
$namespaces:    # any other CWL key          (passthrough)
```

An empty document is well-formed and carries nothing.

---

## 3. Steps

### 3.1 Three surface forms

All three are long-standing, all remain supported, and **all produce the same
result**. Use whichever reads better.

**Mapping, keyed by step name** — cannot repeat a step name:

```yaml
steps:
  touch:
    in:
      filename: !ii empty.txt
```

**Sequence with `id:`** — required when the same tool appears twice:

```yaml
steps:
- id: append
  in: {str: !ii Hello}
- id: append
  in: {str: !ii World}
```

**Sequence of single-key mappings** — the key is the step name:

```yaml
steps:
- touch:
    in:
      filename: !ii empty.txt
```

A step may have no body at all:

```yaml
steps:
  some_subworkflow.wic:
```

### 3.2 Step keys

| Key | Meaning |
|---|---|
| `in` | Input bindings (§4) |
| `out` | Output bindings (§3.3) |
| `scatter`, `scatterMethod` | Interpreted: Sophios adds `ScatterFeatureRequirement` |
| `when` | Interpreted: Sophios adds `InlineJavascriptRequirement` |
| `run` | Interpreted: an inline CWL tool definition |
| *anything else* | Passthrough |

### 3.3 Outputs

`out:` is a sequence. An entry is either a bare name, or a name bound to an
edge definition:

```yaml
out:
- file                    # just names the output
- file: !& file_touch     # names it and defines an edge
```

---

## 4. Input values

### 4.1 The five forms

A step input is exactly one of these. There is no sixth form.

| Form | Written | Means |
|---|---|---|
| Inline literal | `f: !ii empty.txt` | A literal value. Never an edge. |
| Edge definition | `f: !& name` | Defines an explicit edge at this point |
| Edge reference | `f: !* name` | Consumes an edge defined elsewhere |
| Raw CWL reference | `f: !cwl step/out` | Opaque to Sophios; passed through unresolved |
| Unresolved name | `f: some_input` | Must resolve to a workflow input |

An untagged bare string is an **unresolved name**. If it does not name a
workflow input, you get a diagnostic telling you which of the two remedies you
probably meant — `!ii` for a literal, `!cwl` for a CWL reference.

`!ii` accepts any YAML value, not just scalars:

```yaml
in:
  config: !ii
    pdb_code: 1aki
```

### 4.2 Interpreted CWL keys

The complete set Sophios reads and acts upon:

```
scatter    scatterMethod    when    run
```

Everything else on a step is passthrough.

---

## 5. The `wic:` block

Compiler metadata. Never emitted to CWL.

```yaml
wic:
  graphviz:
    label: Protein-ligand docking
  default_implementation: gromacs
  steps:
    (1, extract):
      wic:
        graphviz:
          label: extract structures
```

Step keys inside `wic: steps:` have the form `(index, name)` — the index is
1-based and matches the step's position. Sophios parses these into a structured
key; you should never have to parse that string yourself.

A bare `wic:` with nothing under it is an empty block, not an error.

---

## 6. How the two front-ends adhere

This is the part that keeps the language single.

### 6.1 Two surface forms per construct

Every wic-owned construct has a **tagged** form and a **desugared** form, and
they are equivalent:

| Construct | Tagged | Desugared |
|---|---|---|
| Inline literal | `!ii value` | `{wic_inline_input: value}` |
| Edge definition | `!& name` | `{wic_anchor: name}` |
| Edge reference | `!* name` | `{wic_alias: name}` |
| Raw CWL reference | `!cwl expr` | `{wic_raw_cwl: expr}` |

The desugared form exists for a specific reason: a YAML constructor that
re-emitted its own tag would fire again when the document is reloaded, so the
loader would not be idempotent. Machine-generated documents therefore use the
desugared spelling.

**Write the tagged form.** The desugared form is what tooling emits.

### 6.2 What each front-end must do

**`.wic` files** are the language as written. They are parsed by
`sophios.lang.parse`, which accepts both spellings above.

**The Python API** (`Workflow`, `Step`) is a second front-end over the same
language. `Workflow.write_wic()` and `.to_wic_yaml()` emit `.wic` documents,
using the desugared spelling and sequence-form steps with explicit `id:`.

Two obligations follow, and both are enforced by tests rather than convention:

1. **Whatever the Python API emits must parse.** An API that produced
   documents its own parser rejects would mean two languages wearing one name.
2. **Both spellings must produce the same result.** `!ii x` and
   `{wic_inline_input: x}` are the same input, so compiling either must give
   the same answer.

The second obligation is checked as a property over generated inputs, not by
example — see `tests/core/test_lang_parser.py`.

### 6.3 What this does *not* cover

This document defines **syntax**: whether a document is well-formed. Two
further questions are deliberately separate because they depend on the
environment, not the language:

- **Resolution** — do the step names refer to tools that exist *here*?
- **Type checking** — do the connected ports have compatible types?

A document can be perfectly well-formed and still fail to resolve on a machine
without the right plugins installed. That is not a language error.

---

## 7. Versioning

`wic_version` starts at **0.0.1**, defined against CWL v1.2. The `.wic` version
and its CWL substrate move together.

The version tag is **optional and expected to stay unused**. An untagged file
is compiled at the highest `wic_version` under which that source actually
compiles — not merely the newest version available. That means:

- A file using only long-standing syntax resolves to the newest version.
- A file using syntax a later version dropped resolves to the newest version
  that still accepts it, and keeps working.
- A file using syntax only a newer version added resolves there automatically,
  with no tag required to adopt a feature.

You need a tag only to pin a file for reproducibility, or where a construct is
valid under two versions with different meanings.

The version Sophios actually chose is always reported — on the command line, on
`CompiledWorkflow`, and as an annotation in the emitted CWL. You should never
have to guess which language your file was read as.
