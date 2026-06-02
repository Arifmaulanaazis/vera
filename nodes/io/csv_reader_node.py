"""CSVReaderNode implementation."""

from .common import *  # noqa: F401,F403

class CSVReaderNode(BaseNode):
    """Read one or more CSV/TSV files into list-of-dicts data."""

    def __init__(self):
        super().__init__("csv_reader", "CSV/TSV Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.set_property("file_paths", "")
        self.set_property("delimiter", "auto")  # auto, comma, semicolon, tab
        self.set_property("encoding", "utf-8")

    def _detect_sep(self, path: str) -> str:
        ext = Path(path).suffix.lower()
        if ext == ".tsv":
            return "\t"
        if ext in {".csv"}:
            return ","
        # fallback
        return ","

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No CSV/TSV files provided")
        out_rows: List[Dict[str, Any]] = []
        delim = (self.get_property("delimiter") or "auto").lower()
        enc = self.get_property("encoding") or "utf-8"
        for p in paths:
            sep = {"comma": ",", "semicolon": ";", "tab": "\t"}.get(delim)
            if sep is None:
                sep = self._detect_sep(p)
            try:
                df = pd.read_csv(p, sep=sep, encoding=enc)
                out_rows.extend(df.to_dict("records"))
            except Exception as e:
                self.logger.warning(f"Failed to read {p}: {e}")
        return {"data": out_rows, "num_rows": len(out_rows)}
