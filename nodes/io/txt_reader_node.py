"""TXTReaderNode implementation."""

from .common import *  # noqa: F401,F403

class TXTReaderNode(BaseNode):
    """Read text files. Can emit as raw string or list of lines (data)."""

    def __init__(self):
        super().__init__("txt_reader", "TXT Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.add_output_port("string", "string")
        self.set_property("file_paths", "")
        self.set_property("mode", "lines")  # lines|text
        self.set_property("encoding", "utf-8")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No TXT files provided")
        mode = (self.get_property("mode") or "lines").lower()
        enc = self.get_property("encoding") or "utf-8"
        texts: List[str] = []
        rows: List[Dict[str, Any]] = []
        for p in paths:
            try:
                content = Path(p).read_text(encoding=enc)
                texts.append(content)
                if mode == "lines":
                    for i, line in enumerate(content.splitlines()):
                        rows.append({"file": str(p), "line_no": i + 1, "line": line})
            except Exception as e:
                self.logger.warning(f"Failed to read {p}: {e}")
        return {
            "string": "\n\n".join(texts),
            "data": rows if mode == "lines" else [{"file": str(p), "text": t} for p, t in zip(paths, texts)],
        }
