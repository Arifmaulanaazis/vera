# VERA

<p align="center">
  <img src="vera.png" alt="VERA Logo" width="120" height="120">
</p>

<h1 align="center">Virtual Execution and Reaction Architecture</h1>

<p align="center">
  <strong>An open-source, extensible, desktop-native visual workflow platform for integrated computational chemistry and bioinformatics research.</strong>
</p>

<p align="center">
  <a href="https://github.com/Arifmaulanaazis/vera/releases"><img src="https://img.shields.io/badge/Download-Windows%20Installer-blue?style=flat-square&logo=windows" alt="Download"></a>
  <a href="https://github.com/Arifmaulanaazis/vera"><img src="https://img.shields.io/badge/GitHub-Repository-black?style=flat-square&logo=github" alt="GitHub"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License: MIT"></a>
</p>

---

## Abstract

VERA (Virtual Execution and Reaction Architecture) is an open-source visual workflow platform engineered for computational chemistry, molecular modeling, and bioinformatics research. Built on a directed acyclic graph (DAG) execution paradigm using Python 3.13 and PySide6 (Qt6), VERA provides **106 specialized processing nodes** organized across **13 functional categories**, covering the complete *in silico* drug discovery pipeline from molecular input and preparation through structure-based virtual screening, molecular dynamics simulation, machine learning, and publication-quality visualization.

The platform implements a formally defined **type-safe port system** with 9 canonical data types and automatic compatibility checking, a **thread-safe asynchronous workflow execution engine** with real-time per-node progress monitoring and subprocess lifecycle management, **atomic workflow serialization** to a JSON-based format (`.vsw`), and a **plugin architecture** enabling community-driven extension of the node library.

> **Citation:** If you use VERA in your research, please cite our paper:
> Azis, A.M. (2026). *VERA: A Visual Node-Based Workflow Platform for Integrated Computational Chemistry and Bioinformatics.* arXiv preprint.

---

## Table of Contents

- [Introduction](#introduction)
- [System Architecture](#system-architecture)
- [Node Library](#node-library)
- [Type System](#type-system)
- [Workflow Execution Engine](#workflow-execution-engine)
- [Plugin Architecture](#plugin-architecture)
- [System Requirements](#system-requirements)
- [Installation](#installation)
  - [Pre-built Installer (Recommended)](#pre-built-installer-recommended)
  - [From Source](#from-source)
  - [Setting Up GROMACS](#setting-up-gromacs)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [Example Workflows](#example-workflows)
- [Technical Specifications](#technical-specifications)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

---

## Introduction

Modern computational chemistry and computer-aided drug design (CADD) rely on an increasingly complex ecosystem of specialized software tools. A typical structure-based virtual screening (SBVS) campaign requires protein structure retrieval and preparation, ligand library curation, molecular docking, post-docking analysis, molecular dynamics validation, and statistical visualization each involving distinct file formats (PDB, PDBQT, SDF, MOL2, GRO, TOP, MDP, XVG, XTC, EDR), command-line interfaces, and execution paradigms.

This fragmentation creates three categories of challenges:

1. **Integration Complexity.** Researchers must develop custom glue code to orchestrate data flow between tools, handle file format conversions, and manage error propagation across tool boundaries.
2. **Reproducibility Deficit.** Experimental protocols existing as undocumented scripts with implicit dependencies make computational experiments difficult to reproduce, share, and audit.
3. **Accessibility Barrier.** The steep learning curve of command-line tools excludes domain scientists medicinal chemists, pharmacologists, toxicologists who possess deep biological intuition but lack programming proficiency.

VERA addresses these challenges by providing a desktop-native, visually rich workflow environment that deeply integrates the most widely used computational chemistry engines into a coherent, type-safe, node-based programming model.

---

## System Architecture

VERA follows a four-layer architecture with strict separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                 User Interface Layer (PySide6/Qt6)          │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────────────┐ │
│  │WorkflowCanvas│  │ Toolbox  │  │  FloatingControls     │ │
│  │(QGraphicsView│  │(Palette) │  │  (Run/Stop/Pause)     │ │
│  └──────┬───────┘  └─────┬────┘  └───────────┬───────────┘ │
└─────────┼────────────────┼────────────────────┼─────────────┘
          │                │                    │
┌─────────▼────────────────▼────────────────────▼─────────────┐
│                    Workflow Engine                           │
│  ┌────────────────┐ ┌──────────────┐ ┌───────────────────┐  │
│  │WorkflowManager │ │DAG Validator  │ │State Serializer   │  │
│  │(Execution Ctrl)│ │(Cycle Detect) │ │(JSON/.vsw)        │  │
│  └────────┬───────┘ └──────────────┘ └───────────────────┘  │
└───────────┼─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│                     Node Framework                          │
│  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐ │
│  │NodeFactory  │ │ BaseNode │ │ PortTypes  │ │PluginMgr   │ │
│  │(Registry)   │ │(Abstract)│ │(TypeCheck) │ │(Dynamic)   │ │
│  └──────┬─────┘ └─────┬────┘ └────────────┘ └────────────┘ │
└─────────┼──────────────┼────────────────────────────────────┘
          │              │
┌─────────▼──────────────▼────────────────────────────────────┐
│                   External Engines                          │
│  AutoDock Vina │ GROMACS │ OpenBabel │ RDKit │ scikit-learn │
│  PubChem │ RCSB PDB                                        │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | File | Lines | Description |
|-----------|------|-------|-------------|
| **VERAApplication** | `core/application.py` | ~879 | Main window orchestrator, theme management, signal routing |
| **WorkflowCanvas** | `core/canvas.py` | ~800 | QGraphicsView-based visual editor with Bézier connections |
| **BaseNode** | `core/nodes.py` | ~1,147 | Abstract base class for all workflow nodes (QGraphicsWidget) |
| **WorkflowManager** | `backend/workflow_manager.py` | ~1,561 | DAG execution engine with topological ordering |
| **NodeFactory** | `nodes/node_factory.py` | ~346 | Centralized node type registry |
| **PortTypes** | `core/port_types.py` | ~101 | Type-safe port system with 9 canonical types |

### Data Flow Model

VERA adopts an **in-memory data transport** model where data flows between nodes as Python objects (RDKit Mol instances, pandas DataFrames, byte arrays) without intermediate file I/O. This design:

- Eliminates serialization/deserialization overhead for large molecular datasets
- Preserves object fidelity (RDKit stereochemistry annotations, property dictionaries)
- Enables zero-copy data sharing between consecutive nodes via Python reference semantics

When external tools require file-based input (e.g., Vina requires PDBQT), nodes internally stage data to a managed temporary directory cleaned up on application exit.

---

## Node Library

VERA ships with **106 built-in nodes** organized into **13 functional categories**:

| Category | Nodes | Key Capabilities |
|----------|:-----:|-------------------|
| **Molecular Docking** | 10 | AutoDock Vina (CPU/GPU), batch docking, grid box search, receptor/ligand preparation |
| **Batch Docking** | 1 | High-throughput AutoDock Vina batch virtual screening |
| **Molecular Dynamics** | 10 | GROMACS minimization, equilibration, production, CHARMM-GUI, analysis, trajectory extraction |
| **Molecular Preparation** | 3 | RDKit/OpenBabel minimization, ETKDG conformer generation |
| **Data I/O** | 22 | SDF/MOL/MOL2/PDB/PDBQT/XYZ/CSV/Excel readers, writers, viewers, databases |
| **Data Manipulation** | 6 | Column selection, row filtering, sorting, deduplication, merging |
| **Machine Learning** | 8 | Train/test split, logistic regression, random forest, SVM, KNN, SVR |
| **Model Evaluation** | 3 | Confusion matrix, classification report, regression metrics |
| **Clustering & DR** | 3 | K-Means, agglomerative clustering, PCA |
| **Visualization** | 23 | 2D structure draw, ProLIF interaction, NGL.js 3D viewer, 20 plot types |
| **Chromatography** | 6 | Time-series reader, smoothing, baseline correction, peak detection, integration |
| **Response Surface** | 3 | DoE preparation, model fitting, 3D surface visualization |
| **ML Model Mgmt** | 4 | Model save/load, testing, prediction |

### Molecular Docking

The **AutoDock Vina Node** automates the complete docking pipeline:

1. RDKit molecules → PDB via `Chem.MolToPDBFile` (with ETKDG 3D embedding if needed)
2. PDB → PDBQT conversion via OpenBabel (`obabel -O output.pdbqt`)
3. Receptor PDBQT sanitization (removal of torsion-tree tags for rigid docking)
4. Vina subprocess execution with configurable grid box, exhaustiveness, and energy range
5. Output PDBQT → RDKit Mol parsing with multi-model support
6. Result aggregation into pandas DataFrame (mode, name, affinity, rmsd_lb, rmsd_ub)

Supports **batch docking** of multiple ligands with per-ligand progress reporting and **GPU acceleration** via Vina-GPU 2.1.

### Molecular Dynamics

The MD subsystem wraps **GROMACS** with dedicated nodes for the complete simulation pipeline:

- **Minimization**: Steepest descent energy minimization (grompp → mdrun)
- **Equilibration**: NVT/NPT equilibration with position restraints
- **Production MD**: GPU-accelerated simulation (`-nb gpu -bonded gpu -pme gpu -pmefft gpu`)
- **Analysis**: Automated RMSD, RMSF, Rg, SASA, H-bonds, potential energy via GROMACS tools
- **Trajectory**: XTC extraction, viewer integration, plotting

Real-time progress monitoring parses `stdout` for step numbers and percentage indicators.

### Visualization

- **2D Structure Draw**: RDKit MolDraw2DCairo with configurable grid layout (300 DPI PNG)
- **ProLIF Interaction**: Protein–ligand interaction fingerprints with interactive HTML visualization
- **NGL.js 3D Viewer**: Embedded WebGL molecular viewer (cartoon, ball-and-stick, surface)
- **20 Plot Types**: Histogram, scatter, line, bar, pie, donut, heatmap, Venn, volcano, box, violin, KDE, hexbin, area, ECDF, radar, bubble, stacked bar, 2D histogram, pair plot

---

## Type System

VERA implements a formally defined type-safe port system with **9 canonical data types** and automatic compatibility checking at connection time:

| Type | Description | Color | Python Type |
|------|-------------|-------|-------------|
| `any` | Universal wildcard | Gray `#A0A0A0` | Any |
| `file` | File system path | Blue `#539CFF` | `str` |
| `string` | Textual data | Orange `#FFB446` | `str` |
| `data` | Tabular data | Green `#8CDC78` | `pandas.DataFrame` |
| `list` | Ordered collection | Violet `#C88CFF` | `list` |
| `molecules` | Chemical structures | Pink-Red `#FF6E8C` | `list[rdkit.Chem.Mol]` |
| `bytes` | Binary blob | Teal `#78C8C8` | `bytes` |
| `image` | Image binary | Orange-Red `#FF8C5A` | `bytes` |
| `model` | ML model object | Light Blue `#5AC8FF` | sklearn estimator |

**Type compatibility rule:**

```
∀ t₁, t₂ ∈ T : t₁ ≈ t₂  ⟺  t₁ = 'any' ∨ t₂ = 'any' ∨ normalize(t₁) = normalize(t₂)
```

A synonym normalization table maps common aliases: `molecule` → `molecules`, `mol` → `molecules`, `sdf` → `file`, `pdb` → `file`, `json` → `data`, etc.

---

## Workflow Execution Engine

The **WorkflowManager** executes workflows through a six-phase pipeline:

1. **Canvas Synchronization** — Extracts current node positions, port signatures, properties, and connection topology from the visual canvas
2. **Graph Sanitization** — Removes connections referencing deleted nodes, non-existent ports, or duplicate edges
3. **DAG Validation** — Verifies non-empty graph, acyclicity (via topological sort), and per-node validation
4. **Topological Ordering** — Computes execution order via Kahn's algorithm in O(|V| + |E|) time
5. **State Snapshot** — Captures graph state under a reentrant lock for thread-safe execution
6. **Threaded Execution** — Daemon thread iterates through ordered nodes, gathering inputs from upstream results

### Concurrency Model

- **Graph state lock**: `threading.RLock` for safe concurrent reads during execution
- **UI thread safety**: All visual updates via Qt signals with queued connections
- **Subprocess tracking**: Active processes registered for hard-stop capability (`process.terminate()` + `process.kill()`)
- **Pause semantics**: `threading.Event` blocking between nodes; current node completes before pause
- **User input pause**: Per-node interactive input requests without global workflow pause

### Workflow Serialization

Workflows are serialized to `.vsw` (VERA Scientific Workflow) files using JSON with:
- **Safe JSON coercion**: Recursive conversion of non-serializable objects (RDKit Mol, numpy arrays)
- **Atomic writes**: Write to `.vsw.tmp` → `os.fsync()` → `os.replace()` to prevent corruption
- **Layout persistence**: Node positions, sizes, and custom titles are preserved

---

## Plugin Architecture

VERA's plugin system enables dynamic extension without modifying the core codebase:

**Discovery**: Plugins in `%APPDATA%/VERA/plugins/` with `manifest.json` metadata.

**Registration API**:
```python
def register(api):
    api.register_node(
        node_type="custom_analysis",
        node_class=CustomAnalysisNode,
        display_name="Custom Analysis",
        description="Performs specialized molecular analysis",
        category="Analysis",
        icon_relpath="icons/analysis.png"
    )
```

**Isolation**: Each plugin loaded via `importlib.util.spec_from_file_location` with temporary `sys.path` injection. Plugin failures are caught and logged without preventing application startup.

**Hot-reload**: Plugin registry can be refreshed without restarting the application.

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Python** | 3.13+ | 3.13.5 |
| **GUI Framework** | PySide6 6.8+ | PySide6 6.10.0 with WebEngine |
| **Operating System** | Windows 10 (64-bit) | Windows 11 (64-bit) |
| **Processor** | Multi-core CPU | Modern CPU with AVX2 support |
| **Memory** | 8 GB RAM | 16 GB RAM |
| **Storage** | 14 GB free | 20+ GB SSD |
| **GPU** (optional) | — | NVIDIA CUDA 12.1+ (for Vina-GPU/GROMACS) |
| **Display** | 1920×1080 | 2560×1440 or higher |

---

## Installation

### Pre-built Installer (Recommended)

1. Download the installer from the [Releases](https://github.com/Arifmaulanaazis/vera/releases) page
2. Run `VERA-Setup-x64.exe`
3. Follow the installation wizard
4. Launch VERA from desktop or Start menu

The installer bundles all dependencies and scientific engines.

---

### From Source

Follow these steps to run VERA directly from the source code.

#### 1. Clone the Repository

```bash
git clone https://github.com/Arifmaulanaazis/vera.git
cd vera
```

#### 2. Create and Activate a Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Or activate (Command Prompt)
.venv\Scripts\activate.bat
```

#### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Compile Qt Resources

```bash
python build_resources.py
```

#### 5. Set Up GROMACS (Required for MD Nodes)

> **Important:** GROMACS binaries are **not included** in this repository because they exceed Git's size limits. You must download and place them manually. See the [Setting Up GROMACS](#setting-up-gromacs) section below.

#### 6. Launch VERA

```bash
python main.py
```

---

### Setting Up GROMACS

GROMACS is required for the **Molecular Dynamics** nodes. The pre-built Windows executables are distributed separately at:

> 🔗 **[https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows)**

Releases are available from **GROMACS 2025.1** through **2026.1** and will continue to be updated with new versions.

#### Download and Installation Steps

1. Go to the [Releases page](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows/releases) of the GROMACS pre-build repository.

2. Download the archive for the version and build type you need:
   - `gromacs_2025.1_cpu.zip` — CPU-only build
   - `gromacs_2025.1_cuda.zip` — CUDA-accelerated build (requires NVIDIA GPU)
   - *(and so on for newer versions)*

3. Extract the contents into the **exact folder path** matching the version inside this repository:

   ```
   vera/
   └── engine/
       └── gromacs/
           ├── gromacs_2025.1_cpu/      ← extract CPU archive here
           │   ├── bin/
           │   ├── lib/
           │   ├── share/
           │   └── GMXRC.bat
           ├── gromacs_2025.1_cuda/     ← extract CUDA archive here
           │   ├── bin/
           │   ├── lib/
           │   ├── share/
           │   └── GMXRC.bat
           ├── gromacs_2025.2_cpu/
           ├── gromacs_2025.2_cuda/
           └── ...
   ```

   > ⚠️ The folder names **must match exactly** (e.g., `gromacs_2025.1_cuda`) because VERA uses these paths to locate the `gmx` executable at runtime.

4. Verify the installation by checking that the executable exists, for example:
   ```
   engine\gromacs\gromacs_2025.1_cuda\bin\gmx.exe
   ```

#### Available Versions

| Version | CPU Build | CUDA Build | Notes |
|---------|:---------:|:----------:|-------|
| 2025.1 | ✅ | ✅ | First available pre-build |
| 2025.2 | ✅ | ✅ | Maintenance release |
| 2026.1 | ✅ | ✅ | Latest stable |
| future | ✅ | ✅ | Added as upstream releases |

> **Note:** If you only plan to run CPU-based MD simulations, the CPU build is sufficient. Use the CUDA build to enable GPU acceleration (`-nb gpu -bonded gpu -pme gpu`).

---

## Project Structure

```
vera/
├── main.py                       # Application entry point
├── vera.py                       # Thin launcher (calls main.py)
├── requirements.txt              # Python dependencies
├── build_resources.py            # Qt resource compiler script
├── vera.ico                      # Application icon
├── vera.png                      # VERA logo
├── LICENSE                       # MIT License
├── README.md                     # This file
├── CONTRIBUTING.md               # Contribution guidelines
│
├── core/                         # Core UI and workflow components
│   ├── application.py            # VERAApplication — main window orchestrator
│   ├── canvas.py                 # WorkflowCanvas — QGraphicsView-based editor
│   ├── nodes.py                  # BaseNode — abstract node base class
│   ├── toolbox.py                # NodeToolbox — drag-and-drop palette
│   ├── properties.py             # Properties panel
│   ├── port_types.py             # PortTypes — type system definitions
│   └── floating_controls.py      # Run/Stop/Pause floating toolbar
│
├── backend/
│   └── workflow_manager.py       # WorkflowManager — DAG execution engine
│
├── nodes/                        # All built-in node implementations
│   ├── node_factory.py           # NodeFactory — registry and loader
│   ├── docking_nodes.py          # AutoDock Vina nodes
│   ├── md_nodes.py               # GROMACS molecular dynamics nodes
│   ├── io_nodes.py               # File I/O nodes (SDF, MOL, PDB, CSV, etc.)
│   ├── data_mod_nodes.py         # DataFrame manipulation nodes
│   ├── visualization_nodes.py    # Plotting and 3D viewer nodes
│   ├── ml_nodes.py               # Machine learning nodes (sklearn)
│   ├── admet_nodes.py            # ADMET/toxicity prediction nodes
│   └── ...                       # Other node modules by category
│
├── UI/                           # Qt dialogs and UI components
├── utils/                        # Logging, theming, external tool helpers
├── theme/                        # QSS stylesheets and icon assets
├── plugins/                      # Plugin framework and documentation
├── web/                          # NGL.js 3D viewer HTML
├── example/                      # Pre-built .vsw workflow files
├── assets/                       # Qt resource manifests
│
├── engine/                       # Bundled external computational engines
│   ├── gromacs/                  # GROMACS builds (contents downloaded separately)
│   │   ├── gromacs_2025.1_cpu/   # ← Place CPU 2025.1 build here
│   │   ├── gromacs_2025.1_cuda/  # ← Place CUDA 2025.1 build here
│   │   ├── gromacs_2025.2_cpu/   # ← Place CPU 2025.2 build here
│   │   ├── gromacs_2025.2_cuda/  # ← Place CUDA 2025.2 build here
│   │   └── gromacs_2026.1_*/     # ← And so on for newer versions
│   ├── openbabel/                # OpenBabel binary (included)
│   ├── vina/                     # AutoDock Vina CPU binary (included)
│   ├── vina_gpu/                 # Vina-GPU 2.1 binary (included)
│   └── vina_split/               # Vina split utility (included)
│
├── AutoDockTools/                # AutoDockTools Python library
├── MolKit/                       # MolKit molecular modelling library
├── PyBabel/                      # PyBabel utility library
└── mglutil/                      # MGLTools utility library
```

> **Note on `engine/gromacs/`:** The GROMACS sub-folders are tracked by Git (so the expected paths exist after cloning), but their **contents** are `.gitignore`d due to binary size. You must manually download and extract the GROMACS pre-builds from [Gromacs-Prebuild-Windows](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows/releases) into the matching folder. All other engines (`openbabel`, `vina`, `vina_gpu`, `vina_split`) are already included in the repository.

---

## Dependencies

### Python Libraries

| Library | Version | License | Purpose |
|---------|---------|---------|---------|
| PySide6 | ≥6.6.0 | LGPL v3 | GUI framework (Qt6 bindings) |
| RDKit | ≥2023.9.1 | BSD | Cheminformatics toolkit |
| ProLIF | ≥2.0.0 | MIT | Protein–ligand interaction fingerprints |
| scikit-learn | ≥1.1.0 | BSD-3 | Machine learning |
| pandas | ≥2.0.0 | BSD-3 | Tabular data manipulation |
| numpy | ≥1.24.0 | BSD-3 | Numerical computation |
| matplotlib | 3.9.4 | PSF | 2D plotting |
| seaborn | 0.13.2 | BSD-3 | Statistical visualization |
| Biopython | ≥1.81 | BSD-3 | Bioinformatics utilities |
| Pillow | 10.0.0 | HPND | Image processing |
| plotly | 5.17.0 | MIT | Interactive plotting |

### External Engines

| Engine | Versions | Integration | Bundled |
|--------|----------|-------------|---------|
| **AutoDock Vina** | 1.1.2, 1.2.3–1.2.7 | Subprocess (stdin/stdout) | ✅ Yes |
| **AutoDock Vina GPU** | 2.1 | Subprocess with CUDA | ✅ Yes |
| **GROMACS** | 2025.1–2026.1+ | Subprocess (grompp + mdrun) | ❌ [Manual download](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows) |
| **OpenBabel** | 3.1.1 | Subprocess (obabel) | ✅ Yes |
| **NGL.js** | 2.2.1 | Embedded QWebEngineView | ✅ Yes |

---

## Example Workflows

### Virtual Screening Pipeline

```
[RCSB PDB] ──► [Receptor Prep] ──► [Grid Box Search] ──┐
                                                        │
[SDF Reader] ──► [Ligand Prep] ─────────────────────── ┤
                                                        ▼
                                               [AutoDock Vina]
                                                    │
                                  ┌─────────────────┼──────────────┐
                                  ▼                 ▼              ▼
                          [Docking Analysis] [ProLIF Interact] [2D Draw]
                                  │
                                  ▼
                       [Filter Rows (Affinity < -7)]
                                  │
                                  ▼
                           [Select Columns]
                                  │
                                  ▼
                            [Table View]
```

### Molecular Dynamics Workflow

```
[CHARMM-GUI Input] ──┬──► [GROMACS Minimization]
                     │              │
[File Input (MDPs)] ─┤              ▼
                     ├──► [GROMACS Equilibration]
                     │              │
                     │              ▼
                     └──► [GROMACS Production MD]
                                    │
                         ┌──────────┼──────────┐
                         ▼          ▼          ▼
                   [MD Analysis] [3D Viewer] [XTC Extract]
                         │
                ┌────────┼────────┬────────┬────────┐
                ▼        ▼        ▼        ▼        ▼
          [RMSD Plot] [RMSF] [Rg Plot] [SASA] [H-Bonds]
```

### QSAR Modeling

```
[SDF Reader] ──► [Descriptor Calc] ──► [Train/Test Split]
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                          [Random Forest]        [SVM Classifier]
                                    │                   │
                                    ▼                   ▼
                          [Confusion Matrix]    [Classification Report]
```

---

## Technical Specifications

| Metric | Value |
|--------|-------|
| Total Python source files | ~35 |
| Lines of code | ~25,000 |
| Built-in node types | 106 |
| Node categories | 13 |
| Port data types | 9 canonical + synonyms |
| External engine integrations | 5 (Vina CPU, Vina GPU, GROMACS, OpenBabel, NGL.js) |
| Web service integrations | 2 (PubChem, RCSB PDB) |
| Supported molecular file formats | 7 (SDF, MOL, MOL2, PDB, PDBQT, XYZ, GRO) |
| Plot types | 20 |
| Theme count | 5 (AMOLED Dark, Dracula, Nord, Win11 Dark, System Default) |
| Workflow format | JSON-based `.vsw` with atomic writes |
| License | MIT |

---

## Contributing

We welcome contributions from the computational chemistry, bioinformatics, and scientific workflow communities:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/your-feature`)
3. **Develop** your enhancement
4. **Test** thoroughly
5. **Submit** a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for a detailed guide covering environment setup, code style, branching conventions, adding new nodes, and the pull request process.

### Development Setup

- Python 3.13.5+
- PySide6 ≥6.6.0 for UI development
- Familiarity with computational chemistry workflows
- Understanding of the DAG-based node execution model

### Plugin Development

See the [Plugin Architecture](#plugin-architecture) section for the registration API. Plugins can add new node types without modifying core VERA code.

---

## License

VERA is distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

```
MIT License

Copyright (c) 2026 Arif Maulana Azis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...
```

---

## Acknowledgments

VERA builds upon the work of the open-source scientific computing community. We gratefully acknowledge:

- **[AutoDock Vina](http://vina.scripps.edu/)** — Molecular docking engine (Eberhardt et al., 2021)
- **[AutoDockTools_py3](https://github.com/Valdes-Tresanco-MS/AutoDockTools_py3)** — Python 3 port of AutoDockTools used for receptor/ligand preparation (Valdes-Tresanco MS et al.)
- **[GROMACS](http://www.gromacs.org/)** — Molecular dynamics simulation (Abraham et al., 2015)
- **[RDKit](https://www.rdkit.org/)** — Cheminformatics toolkit (Landrum, 2006)
- **[OpenBabel](https://openbabel.org/)** — Chemical format conversion (O'Boyle et al., 2011)
- **[ProLIF](https://prolif.readthedocs.io/)** — Interaction fingerprints (Bouysset & Fiorucci, 2021)
- **[MDAnalysis](https://www.mdanalysis.org/)** — Trajectory analysis (Gowers et al., 2016)
- **[scikit-learn](https://scikit-learn.org/)** — Machine learning (Pedregosa et al., 2011)
- **[NGL.js](http://nglviewer.org/)** — 3D molecular visualization (Rose et al., 2018)
- **[PySide6](https://doc.qt.io/qtforpython/)** — Qt6 GUI framework (The Qt Company)
- **[Matplotlib](https://matplotlib.org/)** — 2D plotting (Hunter, 2007)
- **[pandas](https://pandas.pydata.org/)** — Data manipulation
- **[NumPy](https://numpy.org/)** — Numerical computation
- **[SciPy](https://scipy.org/)** — Scientific computing
- **[Biopython](https://biopython.org/)** — Bioinformatics utilities

---

## Contact

- **Website**: [https://vera-desktop-app.netlify.app](https://vera-desktop-app.netlify.app)
- **Email**: titandigitalsoft@gmail.com
- **GitHub**: [https://github.com/Arifmaulanaazis/vera](https://github.com/Arifmaulanaazis/vera)
- **Issues**: [https://github.com/Arifmaulanaazis/vera/issues](https://github.com/Arifmaulanaazis/vera/issues)
- **Documentation**: [https://vera-desktop-app.netlify.app/docs](https://vera-desktop-app.netlify.app/docs)

---

<div align="center">
  <p><strong>apt. Arif Maulana Azis, S.Farm.</strong></p>
  <p><em>Empowering scientific discovery through visual workflow automation</em></p>
</div>