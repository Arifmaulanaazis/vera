"""PDBReaderNode implementation."""

from .common import *  # noqa: F401,F403

class PDBReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("pdb_reader", "PDB Reader")
        self._supported_exts = {".pdb", ".ent"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_pdb(path)
