"""PDBQTReaderNode implementation."""

from .common import *  # noqa: F401,F403

class PDBQTReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("pdbqt_reader", "PDBQT Reader")
        self._supported_exts = {".pdbqt"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_pdbqt(path, logger=self.logger)
