"""VinaSplitNode implementation."""

from .common import *  # noqa: F401,F403

class VinaSplitNode(BaseNode):
    """Split a molecules list into individual molecule outputs.

    Inputs:
      - molecules (molecules): list or single RDKit Mol, typically from AutoDock Vina/GPU outputs

    Outputs (dynamic count):
      - molecule_<k> (molecules): single molecule per pin, where k runs from start to start+N-1

    Properties:
      - start_index_1based (int): 1-based start index (1 maps to list index 0). Default 1.
      - num_outputs (int): number of output pins to expose starting from start_index_1based. Default 3.
    """

    def __init__(self):
        super().__init__("vina_split", "Vina Split")
        self.logger = get_logger(__name__)

        # Single input: molecules (accepts list or single)
        self.add_input_port("molecules", "molecules")

        # Properties controlling dynamic outputs
        self.set_property("start_index_1based", 1)
        self.set_property("num_outputs", 3)

        # Build initial output pins
        self._rebuild_output_ports()

    # Headless-safe property setter that rebuilds output pins when relevant properties change
    def set_property(self, key, value):  # type: ignore[override]
        try:
            if hasattr(self, "_created_in_gui_thread") and hasattr(self, "update"):
                try:
                    super().set_property(key, value)
                except Exception:
                    if hasattr(self, "properties"):
                        self.properties[key] = value
            else:
                if hasattr(self, "properties"):
                    self.properties[key] = value
        except Exception:
            pass

        if key in ("num_outputs", "start_index_1based"):
            # Normalize stored values
            try:
                if key == "num_outputs":
                    n = int(value)
                    if n < 1:
                        n = 1
                    if self.get_property("num_outputs") != n and hasattr(self, "properties"):
                        self.properties["num_outputs"] = n
                elif key == "start_index_1based":
                    s = int(value)
                    if s < 1:
                        s = 1
                    if self.get_property("start_index_1based") != s and hasattr(self, "properties"):
                        self.properties["start_index_1based"] = s
            except Exception:
                pass

            # Rebuild dynamic outputs (only in GUI context where ports exist)
            if hasattr(self, "output_ports") and hasattr(self, "add_output_port"):
                self._rebuild_output_ports()

    def _rebuild_output_ports(self) -> None:
        try:
            # Remove existing output ports from the scene and dict
            for p in list(self.output_ports.values()):
                try:
                    if p.scene() is not None:
                        p.scene().removeItem(p)
                except Exception:
                    pass
                try:
                    p.setParentItem(None)
                except Exception:
                    pass
            self.output_ports = {}

            # Compute current labels based on properties
            try:
                start_1 = int(self.get_property("start_index_1based") or 1)
            except Exception:
                start_1 = 1
            if start_1 < 1:
                start_1 = 1
            try:
                num = int(self.get_property("num_outputs") or 1)
            except Exception:
                num = 1
            num = max(1, num)

            # Add outputs molecule_<k> for k in [start_1, start_1+num-1]
            for k in range(start_1, start_1 + num):
                self.add_output_port(f"molecule_{k}", "molecules")

            # Adjust height based on ports (simple heuristic)
            try:
                total_ports = len(self.input_ports) + len(self.output_ports)
                base_h = 120
                self.height = max(base_h, 30 * (total_ports + 1))
                self.setMinimumSize(self.width, self.height)
                self.setMaximumSize(self.width, self.height)
            except Exception:
                pass
            self._update_port_positions()
        except Exception:
            pass

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            # Gather input molecules (accept list or single)
            val = (inputs or {}).get("molecules") if inputs else None
            molecules: list = []
            if val is None:
                pass
            elif isinstance(val, list):
                molecules = [m for m in val if m is not None]
            else:
                molecules = [val]

            if not molecules:
                raise ValueError("Input 'molecules' is required and must contain at least one molecule")

            # Resolve properties
            try:
                start_1 = int(self.get_property("start_index_1based") or 1)
            except Exception:
                start_1 = 1
            if start_1 < 1:
                start_1 = 1
            start_0 = start_1 - 1

            try:
                desired_outputs = int(self.get_property("num_outputs") or 3)
            except Exception:
                desired_outputs = 3
            if desired_outputs < 1:
                desired_outputs = 1

            # Clamp to available molecules
            available_from_start = max(0, len(molecules) - start_0)
            effective_outputs = min(desired_outputs, available_from_start) if available_from_start > 0 else 0

            # If start is beyond available, reset to 1
            if effective_outputs == 0:
                start_1 = 1
                start_0 = 0
                available_from_start = len(molecules)
                effective_outputs = min(desired_outputs, available_from_start)

            # If UI property exceeds available, normalize and rebuild pins
            try:
                if effective_outputs != desired_outputs:
                    self.set_property("num_outputs", effective_outputs)
                # Ensure output pins reflect current start/index range
                self.set_property("start_index_1based", start_1)
            except Exception:
                pass

            # Build outputs: molecule_<k> -> single RDKit Mol (not a list)
            outputs: Dict[str, Any] = {}
            for i in range(effective_outputs):
                k_1 = start_1 + i
                idx = start_0 + i
                if 0 <= idx < len(molecules):
                    outputs[f"molecule_{k_1}"] = molecules[idx]

            return outputs
        except Exception as e:
            self.logger.error(f"Error in VinaSplitNode: {e}")
            raise
