"""ManualGridBoxNode implementation."""

from .common import *  # noqa: F401,F403

class ManualGridBoxNode(BaseNode):
    """Manual grid box input for docking.
    
    User directly inputs all center and size coordinates.
    Validates that all 6 parameters are provided before execution.
    
    Outputs:
      - grid_params (data): dict with center_x/y/z and size_x/y/z
    """
    
    def __init__(self):
        super().__init__("manual_grid_box", "Manual Grid Box")
        self.logger = get_logger(__name__)
        
        # Output port
        self.add_output_port("grid_params", "data")
        
        # Properties for grid parameters - all required
        self.set_property("center_x", None)
        self.set_property("center_y", None)
        self.set_property("center_z", None)
        self.set_property("size_x", None)
        self.set_property("size_y", None)
        self.set_property("size_z", None)
        
        # UI setup - create input fields
        try:
            from PySide6.QtWidgets import QLabel, QDoubleSpinBox, QGridLayout
            from PySide6.QtCore import Qt
            
            
            # Resize node to fit inputs
            self.width = 280
            self.height = 300
            self.setMinimumSize(self.width, self.height)
            self.setMaximumSize(self.width, self.height)
            
            # Create spinboxes for all 6 parameters
            self._spin_boxes = {}
            
            layout = self.content_layout
            if layout is not None:
                # Add labels and spin boxes in grid layout
                params = [
                    ("center_x", "Center X:", 0),
                    ("center_y", "Center Y:", 1),
                    ("center_z", "Center Z:", 2),
                    ("size_x", "Size X:", 3),
                    ("size_y", "Size Y:", 4),
                    ("size_z", "Size Z:", 5),
                ]
                
                for prop_name, label_text, row in params:
                    label = QLabel(label_text)
                    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    
                    spinbox = QDoubleSpinBox()
                    spinbox.setRange(-9999.0, 9999.0)
                    spinbox.setDecimals(3)
                    spinbox.setSingleStep(1.0)
                    
                    # Set current value if exists
                    val = self.get_property(prop_name)
                    if val is not None:
                        try:
                            spinbox.setValue(float(val))
                        except:
                            pass
                    else:
                        # Set placeholder value (will show as unset)
                        spinbox.setSpecialValueText("(not set)")
                        spinbox.setValue(spinbox.minimum())
                    
                    # Connect value changed signal
                    def make_handler(name):
                        def handler(value):
                            try:
                                # Only set if not at minimum (our "not set" indicator)
                                if value > spinbox.minimum():
                                    self.set_property(name, value)
                                else:
                                    self.set_property(name, None)
                            except Exception:
                                pass
                        return handler
                    
                    spinbox.valueChanged.connect(make_handler(prop_name))
                    
                    layout.addWidget(label, row, 0)
                    layout.addWidget(spinbox, row, 1)
                    self._spin_boxes[prop_name] = spinbox
                
                layout.setColumnStretch(0, 0)
                layout.setColumnStretch(1, 1)
            
            self._update_port_positions()
        except Exception:
            # Headless mode
            self._spin_boxes = {}

    
    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Validate that all 6 parameters are provided
        params = ["center_x", "center_y", "center_z", "size_x", "size_y", "size_z"]
        missing = []
        values = {}
        
        for param in params:
            val = self.get_property(param)
            if val is None:
                missing.append(param)
            else:
                try:
                    values[param] = float(val)
                except (ValueError, TypeError):
                    missing.append(param)
        
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"Required parameters not provided: {missing_str}. Please configure all grid box parameters.")


        
        # All parameters provided, create grid dict
        grid = {
            "center_x": values["center_x"],
            "center_y": values["center_y"],
            "center_z": values["center_z"],
            "size_x": values["size_x"],
            "size_y": values["size_y"],
            "size_z": values["size_z"],
        }
        
        self.logger.info(f"Manual grid box: {grid}")
        return {"grid_params": grid}
