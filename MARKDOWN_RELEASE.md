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