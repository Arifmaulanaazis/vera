##  v1.1.2 ( 2026-06-02)

This patch release improves VERA's developer-facing maintainability by organizing each built-in workflow node into its own file while keeping the existing node library and workflow behavior unchanged.

---

##  Highlights

*  **One-node-per-file layout** makes node implementations easier to browse and maintain
*  **Category packages** group node files under focused folders
*  **Compatibility wrappers** preserve imports such as `nodes.plot_nodes`
*  **Data-driven registry** keeps built-in node loading centralized and easier to extend

---

##  Added

###  Developer Experience

* **Modular node packages** (`nodes/`)
  Each concrete built-in workflow node class now lives in its own file under its category folder.
  Shared imports, helper functions, and internal base classes remain in each package's `common.py`.

  * 110 split node files
  * 18 node category packages
  * Compatibility wrappers for the previous `nodes.*_nodes` module paths

---

##  Changed

* Reorganized **110 built-in node classes** into **18 category packages** without changing node types, ports, execution semantics, or `.vsw` workflow compatibility.
* Simplified `NodeFactory` registration into a data-driven built-in registry while preserving plugin loading.
* Updated README project structure and technical counts to describe the new modular node layout.

---

##  Fixed

* **FloatingNodePicker** now uses external plugin `icon_relpath` metadata, so plugin nodes show the same custom icons in the floating compatible-node picker as they do in the main toolbox.

---

##  Release Summary

* **0 new nodes added**
* **0 new categories introduced**
* 110 node implementations split into individual files
* Existing workflows and import paths remain compatible

---

##  v1.1.1 ( 2026-04-20)

This patch release resolves six stability issues across node execution, data handling, and error reporting — improving robustness in headless environments, multi-index DataFrames, and error-path behaviors throughout the workflow engine.

---

##  Highlights

*  **Headless/validation mode** compatibility fix for `SelectColumnsNode`
*  **StackedBarPlotNode** and **PairPlotNode** now always produce valid PNG output
*  Corrected silent data corruption in **`_coerce_number()`** zero-vs-error ambiguity
*  **PythonScriptNode** now warns when a script finishes without populating `output`

---

##  Fixed

###  Nodes

* **SelectColumnsNode** (`select_columns`)
  Missing `_lightweight_construction` guard in `__init__` caused Qt widget creation to run in headless/validation mode. All Qt attributes are now initialised to `None` and the constructor returns early when no display is available.

---

* **StackedBarPlotNode** (`plot_stacked_bar`)
  Calling `_finish_png()` without an active matplotlib figure when the input table was `None` raised a `ValueError`. The node now creates a blank "No data" figure before saving so the output port always receives valid PNG bytes.

---

* **PairPlotNode** (`plot_pairplot`)
  Returning raw `b""` on missing data or seaborn errors caused downstream `image_view` nodes to crash on empty bytes. All error paths now render a "No data" / "Unable to render" placeholder PNG instead.

---

###  Data Handling

* **`_to_rows()`** (`data_mod_nodes`)
  `DataFrame.to_dict(orient="records")` on a MultiIndex DataFrame produced tuple column keys that downstream filter and select nodes could not match. A `reset_index()` call is now applied before conversion to flatten multi-level indices into plain columns.

* **`_coerce_number()`** (`data_mod_nodes`)
  All failure paths previously returned `(False, 0.0)`, making it impossible to distinguish a coercion error from a legitimate zero value. Failure paths now return `(False, float("nan"))` so callers that skip the boolean check cannot silently treat `0.0` as a valid number.

---

###  Scripting

* **PythonScriptNode** (`python_script`)
  Scripts that never wrote to `output` produced silent `None` results with no indication of the problem. `execute()` now emits a logger warning when the script finishes without populating `output["result"]` or `output["result2"]`.

---

##  Release Summary

* **6 bug fixes across nodes, data handling, and scripting**
* Improved stability in headless and validation-mode environments
* Eliminated silent data corruption in number coercion
* All plot nodes now guarantee valid PNG output on error paths

---

##  v1.1.0 ( 2026-04-20)

This release delivers a significant expansion of VERA’s capabilities with the introduction of a dedicated **Cheminformatics toolkit**, integrated **Python scripting**, and new **workflow utilities**. These additions enable more flexible molecular analysis, custom logic execution, and improved workflow documentation directly within the canvas.

---

##  Highlights

*  New **Cheminformatics** category for molecular analysis
*  Built-in **Python scripting** support within workflows
*  New **utility tools** for better workflow organization
*  Expanded node library and toolbox structure

---

##  Added

###  Molecular Input

* **SMILES Input Node** (`smiles_input`)
  Enter SMILES strings directly on the canvas without requiring file-based input.
  Supports one molecule per line with optional naming. Invalid entries are safely skipped with warnings.

---

###  Cheminformatics *(New Category)*

* **Mol Descriptor Node** (`mol_descriptor`)
  Compute RDKit-based molecular descriptors using three presets:

  * `lipinski`
  * `physicochemical`
  * `all` (~200 descriptors)
    Outputs results as a pandas DataFrame.

* **Mol Fingerprint Node** (`mol_fingerprint`)
  Generate molecular fingerprints with support for:

  * Morgan (ECFP)
  * MACCS Keys
  * RDKit
  * Topological Torsion
  * Atom Pair
    Outputs a bit-vector DataFrame (`bit_0`, `bit_1`, …).

* **SMARTS Filter Node** (`smarts_filter`)
  Filter molecules using SMARTS substructure queries.
  Provides `matched` and `unmatched` outputs with validation at workflow level.

---

###  Scripting *(New Category)*

* **Python Script Node** (`python_script`)
  Execute custom Python code directly within workflows.

  * Access inputs via `inputs` dictionary
  * Define outputs via `output` dictionary
  * Includes syntax validation prior to execution
  * Provides two output channels: `result` and `result2`

---

###  Utilities *(New Category)*

* **Note Node** (`note`)
  Add inline documentation to workflows using configurable sticky notes.

  * छह color options
  * Non-executable (excluded from DAG processing)
  * Persisted within `.vsw` workflow files

---

##  Changed

* Reorganized `smiles_input` under **Molecular Input/Output**
* Introduced new toolbox sections:

  * Cheminformatics
  * Scripting
  * Utilities
* Increased built-in nodes from **106 → 112**
* Expanded functional categories from **13 → 16**
* Updated README to reflect new structure and technical specifications

---

##  Removed

* Removed unused `admet_nodes.py` reference from README to improve clarity

---

##  Release Summary

* **6 new nodes added**
* **3 new categories introduced**
* Enhanced extensibility via scripting
* Expanded molecular analysis capabilities
