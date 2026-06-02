"""GromacsPreparationNode implementation."""

from .common import *  # noqa: F401,F403

class GromacsPreparationNode(_BaseGromacsNode):
    """Prepare TPR using provided MDP, structure (GRO), and topology (TOP)."""

    def __init__(self):
        super().__init__("gromacs_prep", "GROMACS Preparation")
        self.add_input_port("input_file", "file")
        self.add_input_port("topology_file", "file")
        self.add_input_port("mdp_file", "file")
        self.add_output_port("tpr_file", "file")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if inputs:
            for key in ("input_file", "topology_file", "mdp_file"):
                if key in inputs and inputs[key]:
                    self.set_property(key, inputs[key])
        tpr = self._prepare_tpr()
        return {"tpr_file": str(tpr)}
