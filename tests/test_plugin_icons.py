from types import SimpleNamespace


def test_floating_picker_uses_plugin_icon_path(qapp, tmp_path, monkeypatch):
    from PySide6.QtGui import QColor, QPixmap

    import backend.plugin_manager as plugin_manager
    import core.canvas as canvas_module
    from backend.plugin_manager import ToolboxNode
    from core.canvas import WorkflowCanvas
    from core.nodes import BaseNode

    class PluginIconProbeNode(BaseNode):
        """Small test node that exposes a data input for compatibility probing."""

        def __init__(self):
            super().__init__("plugin_icon_probe", "Internal Probe Title")
            self.add_input_port("data", "data")

    icon_path = tmp_path / "plugin_icon.png"
    pixmap = QPixmap(48, 48)
    pixmap.fill(QColor("#ff0000"))
    assert pixmap.save(str(icon_path))

    monkeypatch.setattr(
        canvas_module.node_factory,
        "get_available_nodes",
        lambda: {"plugin_icon_probe": PluginIconProbeNode},
    )
    monkeypatch.setattr(
        plugin_manager,
        "get_loaded_toolbox_categories",
        lambda: [
            (
                "External Plugins",
                [
                    ToolboxNode(
                        node_type="plugin_icon_probe",
                        display_name="Plugin Icon Probe",
                        icon_path=icon_path,
                    )
                ],
            )
        ],
    )

    holder = SimpleNamespace(_port_signature_cache={})
    items = WorkflowCanvas._collect_compatible_nodes(holder, from_output=True, data_type="data")

    assert len(items) == 1
    _node_type, display_name, icon = items[0]
    assert display_name == "Plugin Icon Probe"
    center_color = icon.pixmap(48, 48).toImage().pixelColor(24, 24)
    assert center_color == QColor("#ff0000")
