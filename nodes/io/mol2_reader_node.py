"""MOL2ReaderNode implementation."""

from .common import *  # noqa: F401,F403

class MOL2ReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("mol2_reader", "MOL2 Reader")
        self._supported_exts = {".mol2"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_mol2(path)
