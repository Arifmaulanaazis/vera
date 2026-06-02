"""ChromReaderNode implementation."""

from .common import *  # noqa: F401,F403

class ChromReaderNode(BaseNode):
    """Read chromatography/spectroscopy time series into a standardized table.

    Inputs:
      - file (file) optional: single path
      - files (list) optional: list of paths

    Outputs:
      - data (data): list-of-dicts with columns [x_label, y_label, channel]
    """

    def __init__(self):
        super().__init__("chrom_reader", "Chromatography Reader")
        self.logger = get_logger(__name__)

        self.add_input_port("file", "file")
        self.add_input_port("files", "list")
        self.add_output_port("data", "data")

        self.set_property("instrument", "generic")  # generic|hplc|ir|ms
        self.set_property("x_label", "x")  # e.g., Time (min) or Wavenumber (cm-1)
        self.set_property("y_label", "y")  # e.g., Intensity/Absorbance
        self.set_property("x_column", "")  # override detected
        self.set_property("y_column", "")
        self.set_property("separator", ",")
        self.set_property("encoding", "utf-8")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import os
        import pandas as pd  # type: ignore

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        x_col_override = str(self.get_property("x_column") or "").strip()
        y_col_override = str(self.get_property("y_column") or "").strip()
        sep_prop = str(self.get_property("separator") or ",")
        enc = str(self.get_property("encoding") or "utf-8")
        sep_mapped, sep_kwargs = _map_separator_property(sep_prop)

        files: List[str] = []
        if inputs:
            path = inputs.get("file")
            if isinstance(path, str) and path:
                files.append(path)
            multi = inputs.get("files")
            if isinstance(multi, list):
                for p in multi:
                    if isinstance(p, str):
                        files.append(p)

        if not files:
            # Nothing to read; return empty
            return {"data": []}

        all_rows: List[dict] = []
        for fp in files:
            try:
                ext = os.path.splitext(fp)[1].lower()
                df = None
                if ext in (".csv", ".tsv", ".txt", ".arw"):
                    # Prefer tab for .tsv; for .arw or unknown text, try inference
                    loc_sep = "\t" if ext == ".tsv" else sep_mapped
                    try:
                        df = pd.read_csv(fp, sep=loc_sep, encoding=enc, **sep_kwargs)
                    except Exception:
                        # Fallback attempts with common delimiters
                        df = None
                        fallback_tries = [
                            (None, {"engine": "python"}),
                            (",", {"engine": "python"}),
                            (";", {"engine": "python"}),
                            ("\t", {}),
                            (r"\s+", {"engine": "python"}),
                        ]
                        for f_sep, f_kw in fallback_tries:
                            try:
                                df = pd.read_csv(fp, sep=f_sep, encoding=enc, **f_kw)
                                break
                            except Exception:
                                continue
                        if df is None:
                            raise
                elif ext in (".xlsx", ".xls"):
                    df = pd.read_excel(fp)
                else:
                    # Fallback: try csv with mapped/inferred separator
                    try:
                        df = pd.read_csv(fp, sep=sep_mapped, encoding=enc, **sep_kwargs)
                    except Exception:
                        # Try common delimiters as last resort
                        df = None
                        for f_sep, f_kw in [
                            (None, {"engine": "python"}),
                            (",", {"engine": "python"}),
                            (";", {"engine": "python"}),
                            ("\t", {}),
                            (r"\s+", {"engine": "python"}),
                        ]:
                            try:
                                df = pd.read_csv(fp, sep=f_sep, encoding=enc, **f_kw)
                                break
                            except Exception:
                                continue
                        if df is None:
                            raise

                # Choose columns
                x_col, y_col = _infer_xy_columns(df, x_col_override, y_col_override)
                if not x_col or not y_col:
                    raise ValueError("Could not infer numeric x/y columns")

                df = df[[x_col, y_col]].copy()
                df.columns = [x_label, y_label]
                df = _ensure_numeric(df, x_label, y_label)
                if len(df) == 0:
                    raise ValueError("No numeric data after parsing")
                df["channel"] = str(self.get_property("instrument") or "generic")
                all_rows.extend(_dataframe_to_rows(df))
            except Exception as e:
                self.logger.error(f"Failed to read {fp}: {e}")
                continue

        return {"data": all_rows}
