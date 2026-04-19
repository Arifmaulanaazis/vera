# Contributing to VERA

Thank you for your interest in contributing to **VERA (Virtual Execution and Reaction Architecture)**. VERA is a visual, node-based computational workflow platform for drug discovery and molecular simulation. Your contributions help advance open science and make powerful cheminformatics tools more accessible.

This guide covers everything you need to contribute effectively from setting up your development environment to submitting a pull request.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Project Overview](#project-overview)
3. [Architecture at a Glance](#architecture-at-a-glance)
4. [Development Environment Setup](#development-environment-setup)
   - [Python Desktop Application](#python-desktop-application)
   - [Setting Up GROMACS](#setting-up-gromacs)
   - [Landing Page (Next.js)](#landing-page-nextjs)
5. [Project Structure](#project-structure)
6. [How to Contribute](#how-to-contribute)
   - [Reporting Bugs](#reporting-bugs)
   - [Suggesting Features](#suggesting-features)
   - [Contributing Code](#contributing-code)
7. [Branching and Commit Conventions](#branching-and-commit-conventions)
8. [Contributing a New Node](#contributing-a-new-node)
9. [Contributing a Plugin](#contributing-a-plugin)
10. [Contributing to the Landing Page](#contributing-to-the-landing-page)
11. [Code Style Guidelines](#code-style-guidelines)
12. [Testing](#testing)
13. [Pull Request Process](#pull-request-process)
14. [System Requirements](#system-requirements)

---

## Code of Conduct

We expect all contributors to maintain a respectful, inclusive, and collaborative environment. Please:

- Use welcoming and inclusive language.
- Respect differing viewpoints and experiences.
- Accept constructive criticism graciously.
- Focus on what is best for the community and the scientific mission.

Harassment, discrimination, or disrespectful behavior will not be tolerated.

---

## Project Overview

VERA is composed of two independent sub-projects:

| Sub-project | Technology | Location |
|---|---|---|
| Desktop Application | Python 3.13+, PySide6, RDKit, GROMACS | `/` (root) |
| Landing Page | Next.js 15, TypeScript, Tailwind CSS | `/vera-landing-page/` |

Most contributors will work on the **desktop application**. The landing page is a separate static website and is largely documentation/marketing focused.

---

## Architecture at a Glance

Understanding the core architecture will help you contribute effectively.

```
┌─────────────────────────────────────────────────────┐
│                     UI Layer                        │
│  VERAApplication  ·  WorkflowCanvas  ·  NodeToolbox │
│               (PySide6 / Qt6)                       │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                  Workflow Engine                     │
│    WorkflowManager  ·  DAG Validation  ·  Threads   │
│         (backend/workflow_manager.py)                │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│                   Node Framework                    │
│       BaseNode  ·  NodePort  ·  NodeFactory         │
│          (core/nodes.py, nodes/node_factory.py)     │
└───────────────────────┬─────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────┐
│           External Engines & Libraries              │
│  AutoDock Vina  ·  GROMACS  ·  RDKit  ·  MDAnalysis │
│  scikit-learn   ·  ProLIF   ·  OpenBabel  ·  Plotly │
└─────────────────────────────────────────────────────┘
```

**Key concepts:**

- **Nodes** are the fundamental unit of computation. Each node declares typed input/output ports and implements a `run()` method.
- **Ports** use a strict type system with 9 canonical types: `any`, `file`, `string`, `data`, `list`, `molecules`, `bytes`, `image`, `model`.
- **Workflows** are directed acyclic graphs (DAGs) serialized to `.vsw` files (JSON format).
- **WorkflowManager** validates the DAG, orders nodes topologically, and executes them in threads with pause/resume/stop semantics.
- **In-memory data transport**: RDKit `Mol` objects, pandas `DataFrame`s, and other Python objects flow directly between nodes no intermediate serialization unless an external tool (e.g., GROMACS) requires a file.

---

## Development Environment Setup

### Python Desktop Application

**Prerequisites:**

| Tool | Version |
|---|---|
| Python | 3.13+ |
| pip | Latest |
| Git | Latest |
| Windows | 10 or 11 (64-bit) |

**External tools (optional but required for certain nodes):**

- [AutoDock Vina](https://vina.scripps.edu/) — molecular docking nodes *(bundled in `engine/vina/`)*
- [GROMACS](https://www.gromacs.org/) — molecular dynamics nodes *(must be downloaded separately see below)*
- [OpenBabel](https://openbabel.org/) — molecular conversion nodes *(bundled in `engine/openbabel/`)*

**Installation:**

```bash
# 1. Fork the repository on GitHub and clone your fork
git clone https://github.com/Arifmaulanaazis/vera.git
cd vera

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (Command Prompt):
.venv\Scripts\activate.bat

# 4. Install all dependencies
pip install -r requirements.txt

# 5. Compile Qt resources
python build_resources.py

# 6. Set up GROMACS (see next section)

# 7. Run the application
python main.py
```

**Verifying the setup:** VERA should launch with a splash screen, followed by the main workflow canvas. Open one of the pre-built workflows from the `example/` directory to confirm nodes execute correctly.

---

### Setting Up GROMACS

GROMACS binaries are **not included** in this repository because the executables are too large for Git and are not stored in Git LFS. Only the target folder structure is tracked; the contents must be downloaded and placed manually.

**Download the pre-built Windows executables from:**

> 🔗 **[https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows)**

Releases are available starting from **GROMACS 2025.1** and will continue to be updated as new versions are released.

#### Steps

1. Go to the [Releases page](https://github.com/Arifmaulanaazis/Gromacs-Prebuild-Windows/releases).

2. Download the archive matching the version and build type you need:
   - `gromacs_2025.1_cpu.zip` — CPU-only build (no GPU required)
   - `gromacs_2025.1_cuda.zip` — CUDA-accelerated build (requires NVIDIA GPU + CUDA drivers)
   - ... and so on for newer versions.

3. Extract the archive contents into the **exact matching subfolder** inside your cloned repository:

   ```
   vera/
   └── engine/
       └── gromacs/
           ├── gromacs_2025.1_cpu/      ← extract CPU 2025.1 here
           │   ├── bin/
           │   ├── lib/
           │   ├── share/
           │   └── GMXRC.bat
           ├── gromacs_2025.1_cuda/     ← extract CUDA 2025.1 here
           ├── gromacs_2025.2_cpu/
           ├── gromacs_2025.2_cuda/
           └── gromacs_2026.1_*/
   ```

   > ⚠️ Folder names **must match exactly** (e.g., `gromacs_2025.1_cuda`). VERA locates the `gmx.exe` executable using these hard-coded paths.

4. Verify the executable is in place:
   ```
   engine\gromacs\gromacs_2025.1_cuda\bin\gmx.exe
   ```

> **Note for contributors:** When you run `git status`, the `engine/gromacs/*/` subfolders will appear but their contents will not be staged (they are `.gitignore`d). Only the `.gitkeep` placeholder files are tracked. Never commit GROMACS binaries.

---

### Landing Page (Next.js)

If you are contributing to the landing page:

```bash
cd vera-landing-page
npm install
npm run dev
```

The landing page runs at `http://localhost:3000` by default.

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
├── README.md                     # Project readme
├── CONTRIBUTING.md               # This file
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
│   ├── gromacs/                  # GROMACS builds — contents downloaded separately
│   │   ├── gromacs_2025.1_cpu/   # ← download from Gromacs-Prebuild-Windows
│   │   ├── gromacs_2025.1_cuda/  # ← download from Gromacs-Prebuild-Windows
│   │   ├── gromacs_2025.2_cpu/
│   │   ├── gromacs_2025.2_cuda/
│   │   └── gromacs_2026.1_*/
│   ├── openbabel/                # OpenBabel binary (included in repo)
│   ├── vina/                     # AutoDock Vina CPU binary (included in repo)
│   ├── vina_gpu/                 # Vina-GPU 2.1 binary (included in repo)
│   └── vina_split/               # Vina split utility (included in repo)
│
├── AutoDockTools/                # AutoDockTools Python library
├── MolKit/                       # MolKit molecular modelling library
├── PyBabel/                      # PyBabel utility library
└── mglutil/                      # MGLTools utility library
```

---

## How to Contribute

### Reporting Bugs

Before filing a bug report, please search existing issues to avoid duplicates.

**When filing a bug report, include:**

1. **VERA version** (visible in the About dialog or `main.py` header comment)
2. **Operating system** and version (e.g., Windows 11 Pro 64-bit)
3. **Python version** (`python --version`)
4. **Steps to reproduce** — be precise; include a minimal `.vsw` workflow file if applicable
5. **Expected behavior** — what you expected to happen
6. **Actual behavior** — what actually happened
7. **Error output** — paste the full traceback from the console or log file
8. **Screenshots** — if the issue is visual

Open a bug report at: **[GitHub Issues](https://github.com/Arifmaulanaazis/vera/issues)**

---

### Suggesting Features

Feature requests are welcome. Please open a GitHub Issue with:

1. A clear description of the proposed feature
2. The scientific or workflow use case it addresses
3. Any relevant references (papers, tools, APIs)
4. Whether you are willing to implement it yourself

---

### Contributing Code

1. **Find or create an issue** describing the change you plan to make.
2. **Fork** the repository and create a dedicated branch (see [Branching Conventions](#branching-and-commit-conventions)).
3. **Implement** your change following the code style guidelines.
4. **Test** your change manually using the example workflows and your own test cases.
5. **Submit a pull request** referencing the issue.

---

## Branching and Commit Conventions

### Branch Naming

Use the following prefixes for your branches:

| Prefix | When to use | Example |
|---|---|---|
| `feat/` | New feature or new node | `feat/add-rosetta-docking-node` |
| `fix/` | Bug fix | `fix/canvas-drag-crash` |
| `refactor/` | Code refactoring (no behavior change) | `refactor/workflow-manager-threading` |
| `docs/` | Documentation only | `docs/update-plugin-guide` |
| `chore/` | Build scripts, dependencies, tooling | `chore/update-requirements` |
| `web/` | Landing page changes | `web/add-benchmark-section` |

Always branch off from `main`.

```bash
git checkout main
git pull origin main
git checkout -b feat/add-rosetta-docking-node
```

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <short summary in present tense>

[optional body: explain WHY, not WHAT]

[optional footer: references to issues, breaking changes]
```

**Types:** `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`

**Scope** (optional): the module or area affected, e.g., `canvas`, `workflow-manager`, `docking-nodes`, `landing-page`

**Examples:**

```
feat(docking-nodes): add GPU-accelerated AutoDock-GPU node

fix(canvas): prevent crash when connecting incompatible port types

docs(plugins): clarify manifest.json field requirements

chore: update RDKit to 2025.9.1 in requirements.txt
```

**Rules:**
- Summary line must be 72 characters or fewer.
- Use imperative mood: "add", "fix", "update" not "added", "fixed", "updated".
- Do not end the summary line with a period.
- Reference issues in the footer: `Closes #42` or `Refs #15`.

---

## Contributing a New Node

Adding a new node is the most common contribution to VERA. Follow this guide carefully.

### 1. Choose the Right Module

Place your node implementation in the appropriate file under `nodes/`:

| File | Category |
|---|---|
| `docking_nodes.py` | Molecular docking |
| `md_nodes.py` | Molecular dynamics (GROMACS) |
| `io_nodes.py` | File input/output |
| `data_mod_nodes.py` | DataFrame manipulation |
| `visualization_nodes.py` | Plotting, 3D viewer |
| `ml_nodes.py` | Machine learning (sklearn) |
| `admet_nodes.py` | ADMET/toxicity prediction |
| `prep_nodes.py` | Molecular preparation |

If your node does not fit any existing category, create a new appropriately named file and register it in `nodes/node_factory.py`.

### 2. Subclass BaseNode

```python
from core.nodes import BaseNode

class MyNewNode(BaseNode):
    """One-sentence description of what this node does."""

    NODE_TYPE = "MyNewNode"            # Unique string identifier
    NODE_CATEGORY = "Data Manipulation"  # Must match toolbox category
    NODE_DISPLAY_NAME = "My New Node"  # Label shown in the canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.node_type = self.NODE_TYPE
        self.node_category = self.NODE_CATEGORY
        self.display_name = self.NODE_DISPLAY_NAME

        # Declare input ports
        self.add_input_port("molecules", "molecules")  # (label, type)
        self.add_input_port("threshold", "string")

        # Declare output ports
        self.add_output_port("filtered", "molecules")

        self._setup_default_properties()

    def _setup_default_properties(self):
        """Register configurable properties shown in the properties panel."""
        self.add_property("threshold", "0.5", "Similarity threshold (0–1)")

    def run(self, inputs: dict) -> dict:
        """
        Execute the node.

        Args:
            inputs: dict mapping port label → value from upstream node.

        Returns:
            dict mapping output port label → computed value.

        Raises:
            ValueError: if inputs are invalid.
        """
        molecules = inputs.get("molecules")
        threshold = float(inputs.get("threshold") or self.get_property("threshold"))

        if molecules is None:
            raise ValueError("No molecules received on 'molecules' port.")

        # ... your logic here ...
        filtered = [mol for mol in molecules if mol is not None]

        return {"filtered": filtered}
```

### 3. Port Type Reference

Use only canonical port types. VERA will refuse to connect mismatched types at the canvas level.

| Type | Python object expected |
|---|---|
| `any` | Any Python object (use sparingly) |
| `file` | `str` — absolute file path |
| `string` | `str` — text value |
| `data` | `pandas.DataFrame` |
| `list` | `list` |
| `molecules` | `list[rdkit.Chem.Mol]` |
| `bytes` | `bytes` |
| `image` | `PIL.Image` or `matplotlib.Figure` |
| `model` | Trained sklearn estimator |

Synonyms accepted in source code (normalized internally): `molecule` → `molecules`, `sdf` → `file`, `dataframe` → `data`, `df` → `data`.

### 4. Register the Node

Open `nodes/node_factory.py` and add your class to the node registry:

```python
from nodes.my_module import MyNewNode

# Inside NodeFactory._register_builtin_nodes():
self._register(MyNewNode)
```

The `_register()` method will index the node by `NODE_TYPE` and make it discoverable in the toolbox under `NODE_CATEGORY`.

### 5. Add an Example Workflow

Create a minimal `.vsw` file in `example/` that demonstrates your node in a realistic workflow. Open it in VERA, wire it up, run it successfully, then use **File → Save Workflow** to export the `.vsw` file.

### 6. Checklist Before Submitting

- [ ] Node subclasses `BaseNode` correctly
- [ ] `NODE_TYPE` is globally unique (search the codebase to confirm)
- [ ] `NODE_CATEGORY` matches an existing toolbox category or a new one is justified
- [ ] All ports use canonical types
- [ ] `run()` raises descriptive `ValueError` for invalid inputs
- [ ] Node handles `None` inputs gracefully
- [ ] External tools (Vina, GROMACS) are called via `subprocess` with proper error handling
- [ ] Temporary files are written to the workspace directory and cleaned up
- [ ] Node is registered in `NodeFactory`
- [ ] Example `.vsw` workflow is included

---

## Contributing a Plugin

VERA supports a plugin architecture for distributing third-party nodes without modifying the core codebase. If your contribution is self-contained and domain-specific, consider packaging it as a plugin instead of a built-in node.

Refer to the full plugin development guide at **`plugins/README.md`** for:

- Plugin folder structure and `manifest.json` specification
- Registration API
- Node subclassing within plugins
- Packaging and distribution
- Security considerations

Plugins are installed by placing the plugin folder in the user's VERA plugins directory. They are loaded automatically at startup.

---

## Contributing to the Landing Page

The VERA landing page is a Next.js 15 + TypeScript application located in a separate repository. To contribute:

```bash
cd vera-landing-page
npm install
npm run dev
```

Use the `web/` branch prefix for all landing page branches (e.g., `web/fix-mobile-nav`).

---

## Code Style Guidelines

### Python

- **Style:** Follow [PEP 8](https://peps.python.org/pep-0008/) conventions.
- **Naming:** `snake_case` for functions, methods, and variables; `PascalCase` for classes; `UPPER_SNAKE_CASE` for constants.
- **Line length:** 120 characters maximum.
- **Imports:** Standard library → third-party → local, separated by blank lines.
- **Type hints:** Use type hints for all public method signatures.
- **Comments:** Only comment the *why*, not the *what*. A non-obvious invariant, a workaround, or a hidden constraint these warrant a comment. Obvious code does not.
- **Docstrings:** One-line docstring for classes and `run()` methods. No multi-paragraph docstrings.
- **Error handling:** Raise `ValueError` with a descriptive message for invalid node inputs. Use `RuntimeError` for execution failures in external tools.
- **Subprocess calls:** Always set `capture_output=True`, check `returncode`, and raise on failure with the captured `stderr` in the exception message.

---

## Testing

VERA does not currently have an automated test suite. Testing is performed manually.

**When contributing a new node or bug fix, test the following:**

1. **Happy path:** Run the node with valid inputs in a complete workflow and verify the output is correct.
2. **Edge cases:** Test with empty inputs, `None` values, and boundary values for numeric parameters.
3. **Error propagation:** Confirm that invalid inputs raise a `ValueError` with a clear message visible in the VERA console panel.
4. **Workflow serialization:** Save a workflow containing your node as a `.vsw` file, close VERA, reopen it, load the workflow, and confirm all node parameters were preserved correctly.
5. **Type compatibility:** Attempt to connect incompatible port types in the canvas and confirm VERA rejects the connection.

---

## Pull Request Process

1. **Ensure your branch is up to date** with `main` before opening the PR:

   ```bash
   git fetch origin
   git rebase origin/main
   ```

2. **Write a clear PR description** that includes:
   - What the change does and why
   - Which issue it closes (`Closes #<number>`)
   - How you tested it
   - Screenshots if the change affects the UI

3. **PR title** must follow the same Conventional Commits format as commit messages:
   ```
   feat(docking-nodes): add AutoDock-GPU node with CUDA acceleration
   ```

4. **Keep PRs focused.** One logical change per PR. Large refactors should be discussed in an issue first.

5. **Respond to review feedback** promptly. If a reviewer requests changes, push updates to the same branch do not open a new PR.

6. **Squash trivial fixup commits** before the PR is merged (e.g., "fix typo", "address review comment"). You may squash manually with `git rebase -i origin/main` or request squash-merge at merge time.

7. A PR will be merged once it has at least one approving review from a maintainer and all review comments are resolved.

---

## System Requirements

Ensure your development machine meets these requirements before contributing:

| Component | Minimum | Recommended |
|---|---|---|
| Python | 3.13 | 3.13.5 |
| PySide6 | 6.8.0 | 6.10.0 |
| Operating System | Windows 10 (64-bit) | Windows 11 (64-bit) |
| RAM | 8 GB | 16 GB |
| Storage (free) | 14 GB | 20+ GB SSD |
| GPU (optional) | — | NVIDIA with CUDA 12.1+ |
| Display | 1920×1080 | 2560×1440+ |

---

## Questions?

If you have questions that are not answered by this guide or the existing documentation:

- Open a [GitHub Discussion](https://github.com/Arifmaulanaazis/vera/discussions) for general questions.
- Open a [GitHub Issue](https://github.com/Arifmaulanaazis/vera/issues) for bug reports and feature requests.

Thank you for contributing to VERA. Every improvement whether a new node, a bug fix, better documentation, or a clearer example workflow directly benefits researchers working in computational drug discovery.
