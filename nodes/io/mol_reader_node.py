"""MOLReaderNode implementation."""

from .common import *  # noqa: F401,F403

class MOLReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("mol_reader", "MOL Reader")
        self._supported_exts = {".mol"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_mol(path)
