## VERA Plugin Development Guide

This document explains how to develop, package, install, and maintain plugins for VERA. Plugins allow end‑users to add new nodes to the application without rebuilding or open‑sourcing the main app. Once installed, plugin nodes appear in the toolbox and can be used like built‑in nodes.


## Key Concepts

- **Plugin**: A folder (or zip archive) containing a `manifest.json` and a Python entry module with a `register(api)` function. The entry registers nodes into VERA.
- **Node**: A computational unit that appears in the toolbox and can be placed on the workflow canvas. Nodes must subclass `core.nodes.BaseNode` and implement `execute(self, inputs)`.
- **Registry**: The node registry collects both built‑in and plugin nodes. Plugins are loaded after built‑ins so they can safely extend the system.


## Where Plugins Are Stored

User plugins are installed to a per‑user directory:

- Windows: `%APPDATA%/VERA/plugins`
- Linux/macOS: `~/.vera/plugins`

Each plugin has its own subfolder under this root directory.


## Plugin Folder Structure

The recommended structure for a plugin is:

```
<plugins_root>/<plugin_id>/
  manifest.json            # Required metadata
  <entry_module>.py        # Required (declared in manifest)
  icons/                   # Optional assets (e.g., PNG icons)
  ... other files ...
```

Notes:
- `<plugin_id>` must be unique across all installed plugins.
- The entry module path is relative to the plugin folder and defined by `entry_module` in `manifest.json`.
- Icons (if provided) should be referenced via relative paths (e.g., `icons/my_node.png`).


## Manifest Reference (manifest.json)

Required file `manifest.json` in the plugin root. Example:

```json
{
  "id": "hello_vera",
  "name": "Hello VERA",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Example plugin that adds a Hello World node",
  "entry_module": "hello_vera.py"
}
```

Fields:
- `id` (string, required): Unique plugin identifier; used as the installation folder name.
- `name` (string, required): Human‑readable name shown in the Plugins menu.
- `version` (string, required): Plugin version (Semantic Versioning recommended).
- `author` (string, optional): Author or organization.
- `description` (string, optional): Short description for the Plugins menu.
- `entry_module` (string, required): Python file in the plugin folder that defines `register(api)`.


## Entry Module and Registration API

The entry module must define a function:

```python
def register(api):
    # Use api.register_node(...) to register nodes into VERA
    ...
```

Registration method:

```python
api.register_node(
    node_type: str,
    node_class: type,
    display_name: str,
    description: str = "",
    category: str = "Plugins",
    icon_relpath: str | None = None,
)
```

Parameters:
- `node_type`: A globally unique string identifying the node in workflows (e.g., `hello_world`).
- `node_class`: A Python class that subclasses `core.nodes.BaseNode`.
- `display_name`: The label displayed in the toolbox.
- `description`: Optional tooltip/help text for the toolbox entry.
- `category`: Toolbox category where the node appears (new or existing). Defaults to `Plugins`.
- `icon_relpath`: Optional relative path to a custom icon in the plugin folder. If omitted, a themed fallback icon is generated.


## Building a Node (Subclassing BaseNode)

Every node must inherit from `core.nodes.BaseNode` and typically:

1. Set a unique `node_type` and a human‑readable `title` in `__init__`.
2. Add input/output ports via `add_input_port(name, data_type)` and `add_output_port(name, data_type)`.
3. Implement `execute(self, inputs) -> dict` that returns a mapping from output port names to values.
4. Optionally use `set_property/get_property` to persist node settings or show inline summaries.
5. Optionally call `set_node_size(width, height)` to adjust the node footprint.

Minimal example:

```python
from core.nodes import BaseNode


class HelloWorldNode(BaseNode):
    def __init__(self):
        super().__init__(node_type="hello_world", title="Hello World")
        self.add_input_port("name", data_type="string")
        self.add_output_port("greeting", data_type="string")
        self.set_property("name", "World")
        self.set_node_size(220, 120)

    def execute(self, inputs=None):
        name = None
        if isinstance(inputs, dict):
            v = inputs.get("name")
            if isinstance(v, (list, tuple)):
                name = v[0] if v else None
            else:
                name = v
        if not name:
            name = self.get_property("name", "World")
        greeting = f"Hello, {name}!"
        self.set_property("greeting", greeting)
        return {"greeting": greeting}


def register(api):
    api.register_node(
        node_type="hello_world",
        node_class=HelloWorldNode,
        display_name="Hello World",
        description="Emit a greeting string for the given name",
        category="Examples",
        icon_relpath="icons/hello.png",
    )
```

Notes:
- `inputs` is a dict mapping input port names to their incoming values. For multi‑edge inputs your node may receive lists/tuples.
- Return a dict mapping output port names to the produced values.
- Use `validate(self)` to optionally implement configuration validation and return `(bool, message)`.
- Avoid creating Qt widgets in `execute`; it may run in a worker context. Keep UI work inside the main GUI thread or via `on_result`.


## Ports and Data Types

- Define ports with:
  - `self.add_input_port(name, data_type="any")`
  - `self.add_output_port(name, data_type="any")`
- Common data types: `string`, `any`. Domain‑specific types may be used for better compatibility with built‑in nodes.
- Port connections are validated by type compatibility. If unsure, use `any`, then refine as needed.


## Icons and Visuals

- If `icon_relpath` is provided during registration, the toolbox uses that image.
- Recommended icon format: 48×48 PNG with transparent background.
- If no icon is provided, VERA will generate a styled fallback icon.


## Packaging & Distribution

Distribute your plugin as either:

1) A folder containing `manifest.json`, entry module, and assets.

2) A `.zip` (or `.bsx`) archive. The archive can:
- Contain the plugin files at the root, or
- Contain a single top‑level directory with the files inside.

The installer scans the archive to locate `manifest.json` automatically.


## Installation

Inside VERA:

- Open `Plugins → Add Plugin…`
  - Choose a `.zip/.bsx` archive to install from a package, OR
  - Choose a folder containing `manifest.json` to install from a directory.
- After installation, select `Plugins → Reload Plugins` to activate.
- Use `Plugins → Open Plugins Folder` to open the installation directory in the system file explorer.

Manual install (advanced): Copy your plugin folder to the plugins root path (see “Where Plugins Are Stored”), then `Reload Plugins` in the app.


## Updating and Uninstalling

- To update, reinstall from a new folder or archive with the same `id`; the installer replaces the existing plugin directory.
- To uninstall manually, delete the plugin folder under the plugins root, then `Reload Plugins`.


## Troubleshooting

- If a plugin fails to load, it still appears under the Plugins menu but may not have a success indicator.
- Common issues:
  - `manifest.json` missing or invalid
  - `entry_module` missing or cannot be imported
  - `register(api)` not defined or raised an exception
  - Syntax or import errors inside the plugin entry module or node files
- Fix the issue and run `Plugins → Reload Plugins`.


## Advanced Capabilities

- Node properties: Persist settings with `set_property/get_property`; they are saved in workflows.
- Logs & progress (GUI): Within the GUI context, nodes may call `set_progress(percent, message)` to show a progress bar, or `append_log_line(text)` to show logs below the node. Ensure these are used in the GUI thread.
- Headless execution (worker): The workflow engine executes `execute()` in a context that disallows creating Qt widgets. Keep `execute()` pure and CPU/I/O bound.
- External processes: Manage external processes carefully and ensure they are terminated on stop. For complex needs, prefer Python libraries that allow cancellation.


## Security Considerations

- Plugins are Python code executed inside the application process. Only install plugins from trusted sources.
- Avoid using `eval/exec` on untrusted data within your plugin.
- Do not ship secrets in your plugin code. Use environment variables or user settings for credentials.


## Versioning & Compatibility

- Use Semantic Versioning (`MAJOR.MINOR.PATCH`).
- The Plugins menu shows the plugin name and version (e.g., `My Plugin v1.2.3`).
- Keep `node_type` stable across versions to preserve workflow compatibility.


## Best Practices Checklist

- Use a unique, descriptive `node_type` (e.g., `myorg_csv_cleaner`).
- Keep `execute()` deterministic and side‑effect free where possible.
- Validate user inputs early (`validate()`), fail fast with clear messages.
- Avoid blocking the GUI thread; use non‑GUI operations in `execute()`.
- Return small/structured results; store heavy content on disk and return references if needed.
- Provide helpful `display_name`, `description`, and an icon for great UX.


## Quick Tutorial: Hello World Plugin

1) Create the folder:

```
hello_vera/
  manifest.json
  hello_vera.py
  icons/hello.png   # optional
```

2) Add `manifest.json`:

```json
{
  "id": "hello_vera",
  "name": "Hello VERA",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Example plugin that adds a Hello World node",
  "entry_module": "hello_vera.py"
}
```

3) Add `hello_vera.py` (see Minimal example above). Ensure ports use `string` if you want string compatibility.

4) Install:

```bash
# Option A: Zip the folder and install via Plugins → Add Plugin…
zip -r hello_vera.zip hello_vera

# Option B: Copy folder into the plugins directory manually
```

5) In VERA, run `Plugins → Reload Plugins`. Open the toolbox; your node appears under the “Examples” category.


## FAQ

- 
Q: Can a plugin define multiple nodes?

  A: Yes. Call `api.register_node(...)` for each node in `register(api)`.

- 
Q: Can I add a new toolbox category?

  A: Yes. Set the `category` parameter to a new name; it will appear as a separate section.

- 
Q: How can I debug my plugin?

  A: Use `print()` and exception tracebacks in your plugin code while developing. After fixing issues, use `Plugins → Reload Plugins` to re‑load.

- 
Q: Do I need to recompile the app to update a plugin?

  A: No. Plugins are loaded at runtime. Reinstall or replace the plugin files, then `Reload Plugins`.


---

For questions or feedback about the plugin system, please contact the VERA team.


