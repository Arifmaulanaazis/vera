# VERA — Developer Contribution Guide

This guide defines the standards and workflows every contributor must follow
when working on VERA. Read it before making any changes to the codebase.

---

## Language

All code comments, documentation, commit messages, and PR descriptions must be
written in clear, professional English with correct grammar.

---

## Documentation Policy

Whenever you perform any of the following actions, you **must** update the
relevant documentation **in the same commit or PR** not afterward, not in a
separate PR:

| Action | Documents to update |
|--------|---------------------|
| Add a new node | `CHANGELOG.md`, `README.md` (node table, Tech Specs), `core/toolbox.py`, `tests/` (new test class) |
| Remove a node | `CHANGELOG.md`, `README.md`, `core/toolbox.py`, `nodes/node_factory.py`, `tests/` (remove its test class) |
| Add a new toolbox category | `CHANGELOG.md`, `README.md` (category table, Tech Specs) |
| Add a new file or module | `CHANGELOG.md`, `README.md` (Project Structure, if relevant) |
| Fix a bug | `CHANGELOG.md` (section `### Fixed`) |
| Change node or engine behavior | `CHANGELOG.md` (section `### Changed`) |
| Remove a feature or file | `CHANGELOG.md` (section `### Removed`), `README.md` |
| Bump a dependency | `CHANGELOG.md`, `README.md` (Dependencies table), `requirements.txt` |
| Bump application version | `CHANGELOG.md`, `core/app_control.py` |

---

## CHANGELOG.md

### Format

Follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Use the sections: `### Added`, `### Changed`, `### Fixed`, `### Removed`.

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Added
- **Feature Name** (`node_type`) brief description of what it does,
  its inputs/outputs, and any dependencies it uses.

### Changed
- Description of the intentional behavior change.

### Fixed
- **NodeName**: description of the symptom → root cause → fix applied.

### Removed
- Description of what was removed and why.
```

### Versioning Rules (Semantic Versioning)

| Type of change | Version bump |
|----------------|-------------|
| New node, new category, new backward-compatible feature | `MINOR` (1.1.0 → 1.2.0) |
| Bug fix, minor tweak, text/UI change | `PATCH` (1.1.0 → 1.1.1) |
| Breaking change: `.vsw` format, port types, or plugin API changes | `MAJOR` (1.1.0 → 2.0.0) |

**IMPORTANT**: Every time you bump the application version, you **must** also update the version string in `core/app_control.py`.

### Writing Guidelines

- Write from the **user's perspective** describe *what they can now do*,
  not how the code works internally.
- Include the `node_type` in backticks whenever an entry mentions a node.
- For new nodes, include: input ports, output ports, and libraries used.
- Use `YYYY-MM-DD` date format. Always use today's date.
- New entries always go **above** older entries (newest at the top).

---

## README.md

### Sections That Must Be Updated

**1. Node Library Table** (around line 138):
```markdown
| **Category Name** | N | short description |
```
- Update the node count for the affected category.
- Add a new row if a new category was created.
- Remove the row if a category was deleted.

**2. Technical Specifications** (around line 563):
```markdown
| Built-in node types | 112 |
| Node categories     | 16  |
```
- Recount nodes and categories every time they change.
- Update `Total Python source files` if files were added or removed.

**3. Project Structure** (around line 403):
- Add an entry for any new significant file or module.
- Remove entries for deleted files.
- Do not list trivial files (test helpers, empty `__init__.py`, etc.).

**4. Dependencies** (around line 470):
- Add any new library required by a new node.
- Update the minimum version if a dependency was upgraded.

### Sections That Do NOT Need Updating

- Abstract, Introduction, System Architecture only change these if there is a
  major architectural shift.
- Example Workflows only change these if an existing workflow is no longer valid.

---

## Adding a New Node

Every new node must satisfy this checklist before it is considered complete.

### Implementation

- [ ] Class placed in the correct module (e.g. chemistry node → `nodes/chem_nodes.py`)
- [ ] Inherits `BaseNode` from `core/nodes.py`
- [ ] Defines a unique `node_type` in snake_case (e.g. `mol_descriptor`)
- [ ] All input/output ports registered in `__init__`
- [ ] `execute()` returns a `dict` with keys matching the output port names
- [ ] `validate()` returns `(bool, str)`
- [ ] `_inline_summary()` returns a list of short summary strings
- [ ] Lightweight construction guard: check `BaseNode._lightweight_construction`
      before creating any Qt widgets (see `TextInputNode` for the pattern)

### Registration

- [ ] Registered in `nodes/node_factory.py` inside a `try/except ImportError` block
- [ ] Added to the correct category in `core/toolbox.py` via `cat.add_node()`

### Testing

- [ ] Test class added in `tests/test_<module>.py` following the pattern in `CONTRIBUTING.md`
- [ ] At minimum: happy path, empty input, missing input raises `ValueError`, one edge case
- [ ] `python -m pytest tests/ -v` passes with **zero failures** (baseline: 308 tests)

### Documentation

- [ ] Entry added to `CHANGELOG.md` with a new version number
- [ ] Version bumped in `core/app_control.py`
- [ ] Node table in `README.md` updated (node count and category description)
- [ ] Technical Specifications in `README.md` updated

### Dependency Rules

- Use **only libraries already listed** in `requirements.txt` unless explicitly
  approved to add a new one.
- Never add a dependency that requires an external server connection, except for
  `pubchem` and `rcsb_pdb` which are already approved.
- All heavy library imports (RDKit, pandas, numpy, sklearn) must be done
  **inside functions** (`execute`, `validate`), not at module level, so that
  import errors do not block application startup.

---

## Fixing a Bug

1. Identify the root cause before writing any code.
2. Change only the code that is relevant to the bug do not refactor other
   things at the same time.
3. Add an entry to `CHANGELOG.md` under `### Fixed`:
   ```
   - **NodeName**: description of the symptom → root cause → fix applied.
   ```
4. Bump the `PATCH` version, unless the fix also includes a new feature
   (in which case bump `MINOR`).

---

## Testing Standards

VERA uses **pytest** with the Qt offscreen platform so tests run headless.

### Running Tests

```bash
python -m pytest tests/ -v
```

All tests must pass before a PR is merged. The expected baseline is **308 passed**.

### Test File Map

| Node module | Test file |
|---|---|
| `core/port_types.py` | `tests/test_port_types.py` |
| `nodes/data_mod_nodes.py` (helpers) | `tests/test_data_mod_helpers.py` |
| `nodes/data_mod_nodes.py` (nodes) | `tests/test_data_mod_nodes.py` |
| `nodes/script_nodes.py` | `tests/test_script_nodes.py` |
| `nodes/plot_nodes.py` (helpers) | `tests/test_plot_helpers.py` |
| `nodes/plot_nodes.py` (nodes) | `tests/test_plot_nodes.py` |
| `nodes/chem_nodes.py` | `tests/test_chem_nodes.py` |
| `nodes/ml_nodes.py` | `tests/test_ml_nodes.py` |
| `nodes/utility_nodes.py` | `tests/test_utility_nodes.py` |
| `nodes/io_nodes.py` (helpers) | `tests/test_io_helpers.py` |

When adding a node to an existing module, add the test class to the corresponding test file.
When adding a **new module**, create `tests/test_<module_name>.py`.

### Fixture Rules

- Use the **`lightweight`** fixture for nodes that check `BaseNode._lightweight_construction` in their `__init__` (e.g., `SelectColumnsNode`, `PythonScriptNode`). This skips all Qt inline widget construction and only exercises `execute()`.
- Use the **`qapp`** fixture for nodes that unconditionally construct Qt widgets in `__init__` (e.g., `FilterRowsNode`, `SortRowsNode`). A real `QApplication` is required, but `QT_QPA_PLATFORM=offscreen` prevents any window from appearing.
- Never use both `qapp` and `lightweight` on the same test — `lightweight` already implies `qapp`.

### What to Test

Every node test class must cover:

1. **Happy path** — valid, representative inputs produce the expected output.
2. **Empty data** — `execute({"data": []})` returns an empty result (not an exception).
3. **Missing required input** — `execute({})` raises `ValueError`.
4. **At least one edge case** specific to the node's logic (boundary value, operator variant, format alias, etc.).

Do **not** test Qt widget state (checked boxes, table row counts, etc.) — those belong to manual testing. Focus on the `execute()` return value and `validate()` return value.

### Naming Convention

- Test class: `TestMyNodeName` (matches the node class name with `Test` prefix).
- Test method: `test_<scenario_in_snake_case>` — describe the *scenario*, not the *assertion*.

---

## Intentional Behavior Changes

If you are deliberately changing how a node or the engine behaves (not a bug fix):

1. Document it in `CHANGELOG.md` under `### Changed`.
2. If the change affects the `.vsw` file format, bump `MAJOR`.
3. If the change renames or changes the type of an existing output port, bump
   `MAJOR` saved workflows may break.

---

## Counting Nodes and Categories

To get an accurate node count, run:

```bash
python -c "
from nodes.node_factory import node_factory
reg = node_factory.get_available_nodes()
print(f'Total nodes: {len(reg)}')
"
```

To count categories:

```bash
grep -c '_add_category(' core/toolbox.py
```

Always use the numbers produced by these commands. Do not guess or copy old
numbers from existing documentation.

---

## About VERA

**VERA** (Virtual Execution and Reaction Architecture) is a visual workflow
platform for computational chemistry and bioinformatics, built with Python 3.13
and PySide6 (Qt6). All computation runs fully offline there is no cloud
service or backend server.

| | |
|-|-|
| Language | Python 3.13 |
| GUI | PySide6 (Qt6) + QWebEngineView for NGL.js |
| Workflow format | `.vsw` (JSON) |
| Plugin directory | `%APPDATA%/VERA/plugins/` |
| External engines | AutoDock Vina (bundled), GROMACS (manual install), OpenBabel (bundled) |