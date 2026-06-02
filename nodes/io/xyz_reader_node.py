"""XYZReaderNode implementation."""

from .common import *  # noqa: F401,F403

class XYZReaderNode(_BaseMolReaderNode):
    """Node for reading XYZ format files into RDKit molecules."""
    
    def __init__(self):
        super().__init__("xyz_reader", "XYZ Reader")
        self._supported_exts = {".xyz"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_xyz(path)
