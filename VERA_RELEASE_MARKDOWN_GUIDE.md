# VERA — GitHub Release Page Markdown Guide

This guide defines the standard format for writing GitHub Release page markdown
for VERA. Every release published on GitHub must follow this structure.

---

## Overview

A VERA release page consists of six sections in this exact order:

1. Release header (version + date)
2. Short description paragraph
3. Highlights
4. Added (grouped by category)
5. Changed
6. Removed
7. Release Summary

---

## Full Template

```markdown
##  vX.Y.Z ( YYYY-MM-DD)

One or two sentences describing what this release delivers at a high level.
Focus on the user-facing value, not implementation details.

---

##  Highlights

*  First major highlight — link to category or feature
*  Second major highlight
*  Third major highlight
*  Fourth major highlight (if applicable)

---

##  Added

###  Category Name

* **Node Display Name** (`node_type`)
  One sentence describing what the node does.
  Supporting details, sub-bullets, or presets:

  * option_a
  * option_b
  * option_c

---

###  Another Category *(New Category)*

* **Node Display Name** (`node_type`)
  Description of what it does.

  * Sub-feature or option
  * Sub-feature or option

---

##  Changed

* Description of an intentional behavior or structural change.
* Another change — keep it brief and user-facing.

---

##  Removed

* Description of what was removed and why.

---

##  Release Summary

* **N new nodes added**
* **N new categories introduced**
* One-line note on a key capability gain
* One-line note on another capability gain
```

---

## Section Rules

### Release Header

```markdown
##  vX.Y.Z ( YYYY-MM-DD)
```

* Use two `#` characters (h2).
* Version follows `v` prefix with no space: `v1.1.0`, `v1.2.0`, `v2.0.0`.
* Date in parentheses, format `YYYY-MM-DD`, always today's actual date.

---

### Description Paragraph

* One or two sentences only.
* Written from the **user's perspective** — what they can now do.
* Bold the names of major new features or categories introduced.
* Do not describe internal implementation details.

**Example:**
```markdown
This release delivers a significant expansion of VERA's capabilities with the
introduction of a dedicated **Cheminformatics toolkit**, integrated **Python
scripting**, and new **workflow utilities**.
```

---

### Highlights

* Four to six bullet points maximum.
* Each bullet starts with a bold noun phrase followed by a short clause.
* Cover every new category or major feature introduced in this release.

**Example:**
```markdown
##  Highlights

*  New **Cheminformatics** category for molecular analysis
*  Built-in **Python scripting** support within workflows
*  New **utility tools** for better workflow organization
*  Expanded node library and toolbox structure
```

---

### Added

Group new nodes under `###` subheadings that match the toolbox category name.
Append `*(New Category)*` after the heading name when the category itself is new.

Each node entry follows this pattern:

```markdown
* **Display Name** (`node_type`)
  One sentence summary — what the user can do with it.
  Optional second sentence for inputs, outputs, or constraints.

  * preset_or_option_a
  * preset_or_option_b
```

Rules:
* `node_type` is always in backticks and matches the registered `node_type` string exactly.
* List presets, fingerprint types, output ports, or color options as sub-bullets.
* Separate each `###` category block with a `---` divider.

---

### Changed

* One bullet per change.
* Use plain prose — no node_type backticks unless a specific node is mentioned.
* Include counts when toolbox structure changes (e.g., `106 → 112 nodes`).

**Example:**
```markdown
##  Changed

* Reorganized `smiles_input` under **Molecular Input/Output**
* Introduced new toolbox sections: Cheminformatics, Scripting, Utilities
* Increased built-in nodes from **106 → 112**
* Expanded functional categories from **13 → 16**
```

---

### Removed

* One bullet per removed item.
* State what was removed and give a brief reason (clarity, deprecation, refactor).
* Omit this section entirely if nothing was removed in the release.

---

### Release Summary

Close every release with a short stat block:

```markdown
##  Release Summary

* **N new nodes added**
* **N new categories introduced**
* One-line capability note
* One-line capability note
```

* Always state node and category counts explicitly.
* Keep bullets to four or fewer.

---

## Versioning Reference

| Change type | Bump |
|-------------|------|
| New node, new category, backward-compatible feature | `MINOR` (1.1.0 → 1.2.0) |
| Bug fix, minor tweak, text or UI change | `PATCH` (1.1.0 → 1.1.1) |
| Breaking `.vsw` format, port types, or plugin API | `MAJOR` (1.1.0 → 2.0.0) |

---

## Checklist Before Publishing

- [ ] Version number matches `core/app_control.py`
- [ ] Date matches today's date in `YYYY-MM-DD` format
- [ ] All new `node_type` values are in backticks and spelled correctly
- [ ] Node and category counts in **Changed** and **Release Summary** are accurate
- [ ] New categories are marked `*(New Category)*` in the `###` heading
- [ ] `---` divider appears after every `###` category block under **Added**
- [ ] **Removed** section is present only if something was actually removed
- [ ] Description paragraph uses bold for every major new feature name
