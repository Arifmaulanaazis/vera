# Changelog

All notable changes to VERA (Virtual Execution and Reaction Architecture) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.1] — 2026-04-20

### Fixed

- **SelectColumnsNode**: missing `_lightweight_construction` guard in `__init__` caused Qt widget
  creation to run in headless/validation mode → added guard that initialises all Qt attributes to
  `None` and returns early when running without a display.
- **StackedBarPlotNode**: calling `_finish_png()` without an active matplotlib figure when the
  input table was `None` produced a `ValueError` from matplotlib → node now creates a blank
  "No data" figure before saving so the output port always receives valid PNG bytes.
- **PairPlotNode**: returning raw `b""` on missing data or seaborn error caused downstream
  `image_view` nodes to crash on empty bytes → node now renders a "No data" / "Unable to render"
  placeholder PNG in all error paths.
- **`_to_rows()`** (`data_mod_nodes`): `DataFrame.to_dict(orient="records")` on a MultiIndex
  DataFrame produced tuple column keys that downstream filter/select nodes could not match →
  added `reset_index()` before conversion to flatten multi-level indices into plain columns.
- **`_coerce_number()`** (`data_mod_nodes`): all failure paths returned `(False, 0.0)`, making it
  impossible to distinguish a coercion error from a legitimate zero value → failure paths now
  return `(False, float("nan"))` so callers that skip the boolean check cannot silently use `0.0`
  as if it were a valid number.
- **PythonScriptNode**: scripts that never wrote to `output` produced silent `None` results with
  no indication of the problem → `execute()` now emits a logger warning when the script finishes
  without populating `output["result"]` or `output["result2"]`.

---

## [1.1.0] — 2026-04-20

### Added

#### Molecular Input
- **SMILES Input Node** (`smiles_input`) — Type or paste SMILES strings directly on the canvas (one per line, optional name after space) to produce a `molecules` output without needing a file. Invalid lines are skipped with a warning.

#### Cheminformatics (new category)
- **Mol Descriptor Node** (`mol_descriptor`) — Calculate RDKit molecular descriptors for a list of molecules. Three presets available: `lipinski` (MW, LogP, HBD, HBA, TPSA, RotBonds), `physicochemical` (lipinski + RingCount, AromaticRings, FractionCSP3, MolMR), and `all` (~200 RDKit descriptors). Output is a pandas DataFrame. No external dependencies beyond RDKit.
- **Mol Fingerprint Node** (`mol_fingerprint`) — Generate molecular fingerprints as a bit-vector DataFrame. Supported types: Morgan/ECFP (configurable radius and nBits), MACCS Keys, RDKit fingerprint, Topological Torsion, Atom Pair. Output is a pandas DataFrame with one column per bit (`bit_0`, `bit_1`, …).
- **SMARTS Filter Node** (`smarts_filter`) — Filter a list of molecules by a SMARTS substructure pattern. Produces two output ports: `matched` (molecules that contain the substructure) and `unmatched` (molecules that do not). Pattern is validated at workflow validation time.

#### Scripting (new category)
- **Python Script Node** (`python_script`) — Execute arbitrary Python code inside the workflow. The inline code editor exposes an `inputs` dict (all connected input values by port name) and an `output` dict that the script populates. Two output ports: `result` and `result2`. Script syntax is validated before execution.

#### Utilities (new category)
- **Note Node** (`note`) — A sticky note / comment that can be placed freely on the canvas for workflow documentation. Supports six background colors (yellow, blue, green, red, purple, gray). The note does not participate in DAG execution. Text is editable inline and persisted in the `.vsw` workflow file.

### Changed
- `smiles_input` node moved into the existing **Molecular Input/Output** toolbox category alongside the other molecular readers/writers.
- Toolbox now includes three new sections: **Cheminformatics**, **Scripting**, **Utilities**.
- Built-in node count increased from **106** to **112**.
- Functional category count increased from **13** to **16**.
- README updated: node count, category count, and Technical Specifications table reflect the new totals.

### Removed
- Removed placeholder reference to `admet_nodes.py` from README project structure (file was never implemented; removed to avoid confusion).

---

## [1.0.0] — 2026-04-19

Initial public release of VERA — Virtual Execution and Reaction Architecture.

### Added

#### Core Architecture
- **DAG-based workflow execution engine** (`backend/workflow_manager.py`) — Topological ordering via Kahn's algorithm, thread-safe execution with `threading.RLock`, pause/resume/stop semantics, per-node progress reporting, and subprocess lifecycle management.
- **Visual workflow canvas** (`core/canvas.py`) — `QGraphicsView`-based editor with Bézier connection curves, drag-and-drop node placement, rubber-band multi-selection, pinch-to-zoom (trackpad/touch), and snapshot-based undo/redo (50 levels).
- **Type-safe port system** (`core/port_types.py`) — 9 canonical data types (`any`, `file`, `string`, `data`, `list`, `molecules`, `bytes`, `image`, `model`) with automatic compatibility checking and synonym normalization at connection time.
- **BaseNode** (`core/nodes.py`) — Abstract `QGraphicsWidget`-based node with execution state machine (idle → validating → running → paused → completed/error), inline content area (single `QGraphicsProxyWidget` + `QGridLayout`), interactive edge/corner resizing, floating progress bar, floating error panel, and floating log panel per node.
- **Node Toolbox** (`core/toolbox.py`) — Accordion-style dockable palette with live search/filter, category collapse/expand, drag-to-canvas, and icon rendering.
- **Workflow serialization** — JSON-based `.vsw` format with atomic writes (`tmp → fsync → replace`) and safe coercion of non-serializable objects.
- **Plugin architecture** (`backend/plugin_manager.py`) — Discovery of plugins from `%APPDATA%/VERA/plugins/`, installation from `.zip`/`.bsx` archives or folders, hot-reload without restart, `register(api)` entrypoint API.
- **Recent Projects dialog** — Persisted list of recently opened `.vsw` files shown at startup.
- **Toast notification system** (`core/toast.py`) — Non-blocking in-window toast overlay with status variants (running, paused, success, warning, error, info) and auto-dismiss timers.
- **5 built-in themes** — AMOLED Dark, Dracula, Nord, Win11 Dark, System Default (QSS-based, persisted in `QSettings`).
- **Floating workflow controls** (`core/floating_controls.py`) — Run / Stop / Pause / Resume / Validate / Clear toolbar anchored over the canvas, with per-run progress bar.
- **Validation animation** — Sequential node highlight animation when workflow is validated successfully.

#### Node Library — 106 built-in nodes across 13 categories

**Molecular Docking (10 nodes)**
- `autodock_vina` — AutoDock Vina CPU docking (versions 1.1.2 – 1.2.7); full pipeline: RDKit mol → PDB → PDBQT via OpenBabel → Vina subprocess → multi-pose RDKit Mol + DataFrame output.
- `autodock_vina_gpu` — Vina-GPU 2.1 acceleration via CUDA.
- `autodock_vina_batch` — High-throughput batch docking from a list of molecules with per-ligand progress.
- `docking_analysis` — Parse Vina results; extract best poses, affinity table, RMSD lb/ub.
- `vina_split` — Split a multi-molecule list into individual single-molecule output pins.
- `grid_search` — Estimate docking grid box center and size from input molecules.
- `manual_grid_box` — Manually specify grid box center/size as numeric properties.
- `merge_molecule` — Merge two or more molecules into a single complex.
- `receptor_preparation` — Prepare protein receptor: remove waters/ligands, add hydrogens, assign Gasteiger charges using AutoDockTools.
- `ligand_preparation` — Prepare ligand: de-salt, neutralize, add hydrogens, embed 3D (ETKDG), minimize, assign charges.

**Molecular Dynamics (10 nodes)**
- `charmm_gui_input` — Load and verify CHARMM-GUI output directory.
- `gromacs_input_editor` — Edit MDP parameter files before simulation.
- `gromacs_prep` — Prepare GROMACS topology and coordinate files.
- `gromacs_minimize` — Steepest descent energy minimization (`grompp` + `mdrun`).
- `gromacs_equilibrate` — NVT/NPT equilibration with position restraints.
- `gromacs_production` — Production MD with optional GPU acceleration (`-nb gpu -bonded gpu -pme gpu`).
- `xtc_extractor` — Extract and post-process XTC trajectory files.
- `gromacs_analysis` — Automated RMSD, RMSF, Rg, SASA, H-bonds, potential energy via GROMACS tools.
- `gromacs_ploting` — Plot analysis results (XVG → matplotlib).
- `gromacs_viewer` — Visualize MD trajectories via embedded NGL.js viewer.

**Molecular Minimization (3 nodes)**
- `rdkit_minimize` — MMFF94/UFF force field minimization with RDKit.
- `openbabel_minimize` — Minimization via OpenBabel subprocess.
- `conformer_gen` — ETKDG 3D conformer generation with RDKit.

**Data I/O (22 nodes)**
- Molecular readers: `sdf_reader`, `mol_reader`, `mol2_reader`, `pdb_reader`, `pdbqt_reader`, `xyz_reader`, `mol_reader_auto`.
- Tabular readers: `csv_reader`, `excel_reader`, `txt_reader`.
- General I/O: `file_input`, `folder_input`, `file_output`, `save_file`.
- Savers: `save_dataframe`, `save_molecule`, `save_text`, `save_json`, `save_image`.
- Viewers: `table_view`, `text_view`, `image_view`.
- Input: `text_input`.

**Data Manipulation (6 nodes)**
- `select_columns`, `filter_rows`, `slice_rows`, `drop_duplicates`, `sort_rows`, `merge_dataframes`.

**Machine Learning (8 nodes)**
- `ml_train_test_split` — Stratified or random train/test split.
- `ml_logistic_regression`, `ml_random_forest_classifier`, `ml_svm_classifier`, `ml_knn_classifier` — Classification.
- `ml_linear_regression`, `ml_random_forest_regressor`, `ml_svr` — Regression.

**Model Evaluation (3 nodes)**
- `eval_confusion_matrix`, `eval_classification_report`, `eval_regression_metrics`.

**Clustering & Dimensionality Reduction (3 nodes)**
- `cluster_kmeans`, `cluster_agglomerative`, `dim_pca`.

**Chemical Visualization (3 nodes)**
- `structure_draw_2d` — RDKit `MolDraw2DCairo` 2D structure rendering (300 DPI PNG, grid layout).
- `prolif_interaction` — Protein–ligand interaction fingerprints via ProLIF; interactive HTML output.
- `web3d_viewer` — Embedded NGL.js WebGL 3D viewer (`QWebEngineView`).

**Plotting (20 nodes)**
- `plot_histogram`, `plot_scatter`, `plot_line`, `plot_bar`, `plot_pie`, `plot_donut`, `plot_heatmap`, `plot_venn`, `plot_volcano`, `plot_box`, `plot_violin`, `plot_kde`, `plot_hexbin`, `plot_area`, `plot_ecdf`, `plot_radar`, `plot_bubble`, `plot_stacked_bar`, `plot_hist2d`, `plot_pairplot`.

**Chemical Data Scraping (2 nodes)**
- `pubchem_search` — Search and download molecules from PubChem REST API.
- `rcsb_pdb` — Fetch PDB structure by accession code from RCSB PDB.

**Chromatography and Spectroscopy (6 nodes)**
- `chrom_reader`, `chrom_smoothing`, `chrom_baseline`, `chrom_peak_detect`, `chrom_integrate`, `chrom_viewer`.

**Response Surface Analysis (3 nodes)**
- `rsa_prep`, `rsa_fit`, `rsa_surface`.

**ML Model Management (4 nodes)**
- `ml_model_load`, `ml_model_save`, `ml_model_test`, `ml_model_predict`.

#### External Engine Integrations
- **AutoDock Vina** (CPU, versions 1.1.2 – 1.2.7) — bundled.
- **Vina-GPU 2.1** — bundled.
- **GROMACS** (2025.1 – 2026.1+) — pre-built Windows binaries downloaded separately.
- **OpenBabel 3.1.1** — bundled.
- **NGL.js 2.2.1** — embedded in `QWebEngineView`.

#### Python Dependencies
PySide6 ≥ 6.6.0, RDKit ≥ 2023.9.1, ProLIF ≥ 2.0.0, scikit-learn ≥ 1.1.0, pandas ≥ 2.0.0, numpy ≥ 1.24.0, matplotlib 3.9.4, seaborn 0.13.2, Biopython ≥ 1.81, Pillow 10.0.0, plotly 5.17.0, MDAnalysis, SciPy.

---

[1.1.1]: https://github.com/Arifmaulanaazis/vera/compare/1.1.0...1.1.1
[1.1.0]: https://github.com/Arifmaulanaazis/vera/compare/1.0.0...1.1.0
[1.0.0]: https://github.com/Arifmaulanaazis/vera/releases/tag/1.0.0
