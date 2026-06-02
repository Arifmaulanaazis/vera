"""SDFReaderNode implementation."""

from .common import *  # noqa: F401,F403

class SDFReaderNode(_BaseMolReaderNode):
    def __init__(self):
        super().__init__("sdf_reader", "SDF Reader")
        self._supported_exts = {".sdf"}

    def _read_one(self, path: str) -> List[Any]:
        return _read_sdf(path)
