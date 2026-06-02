"""ExcelReaderNode implementation."""

from .common import *  # noqa: F401,F403

class ExcelReaderNode(BaseNode):
    """Read one or more Excel files (.xlsx, .xls) into list-of-dicts data."""

    def __init__(self):
        super().__init__("excel_reader", "Excel Reader")
        self.logger = get_logger(__name__)
        self.add_input_port("files", "list")
        self.add_input_port("file", "file")
        self.add_output_port("data", "data")
        self.set_property("file_paths", "")
        self.set_property("sheet", "")  # name or index (int)
        self.set_property("header", True)
        self.set_property("engine", "auto")  # auto/openpyxl/xlrd

    def _read_one(self, path: str) -> List[Dict[str, Any]]:
        sheet = self.get_property("sheet")
        header = 0 if bool(self.get_property("header")) else None
        engine = self.get_property("engine") or "auto"
        kwargs: Dict[str, Any] = {}
        if engine != "auto":
            kwargs["engine"] = engine
        try:
            df = pd.read_excel(path, sheet_name=sheet if sheet not in (None, "") else 0, header=header, **kwargs)
            # If multiple sheets returned as dict of DataFrames, concat
            if isinstance(df, dict):
                import pandas as _pd
                df = _pd.concat(df.values(), ignore_index=True)
            return df.to_dict("records")
        except Exception as e:
            self.logger.warning(f"Failed to read Excel {path}: {e}")
            return []

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        paths = _as_path_list(inputs.get("files") if inputs else None) or _as_path_list(inputs.get("file") if inputs else None)
        if not paths:
            paths = _as_path_list(self.get_property("file_paths"))
        if not paths:
            raise ValueError("No Excel files provided")
        out: List[Dict[str, Any]] = []
        for p in paths:
            out.extend(self._read_one(p))
        return {"data": out, "num_rows": len(out)}
