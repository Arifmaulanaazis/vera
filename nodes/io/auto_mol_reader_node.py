"""AutoMolReaderNode implementation."""

from .common import *  # noqa: F401,F403

class AutoMolReaderNode(_BaseMolReaderNode):
    """Generic molecule reader that detects by extension (SDF/MOL/MOL2/PDB/PDBQT/XYZ)."""

    def __init__(self):
        super().__init__("mol_reader_auto", "Molecule Reader (Auto)")
        self._supported_exts = {".sdf", ".mol", ".mol2", ".pdb", ".ent", ".pdbqt", ".xyz"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_auto(path, logger=self.logger)
