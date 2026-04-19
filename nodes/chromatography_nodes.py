"""
Chromatography & Spectroscopy nodes.

Provides generic time-series reader, smoothing, baseline correction,
peak detection, integration, and plotting that work for HPLC, IR, and
other instruments with similar time/wavenumber vs intensity outputs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import io

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _rows_to_dataframe(rows: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if rows is None:
        return None
    # rows may be a DataFrame already
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
        if isinstance(rows, _PDDataFrame):
            return rows
    except Exception:
        pass
    # list-of-dicts → DataFrame
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            return pd.DataFrame(rows)
        except Exception:
            return None
    return None


def _dataframe_to_rows(df: Any) -> List[dict]:
    try:
        return [] if df is None else df.to_dict("records")  # type: ignore[attr-defined]
    except Exception:
        return []


def _ensure_numeric(df, x_col: str, y_col: str):
    try:
        import pandas as pd  # type: ignore
        out = df.copy()
        out[x_col] = pd.to_numeric(out[x_col], errors="coerce")
        out[y_col] = pd.to_numeric(out[y_col], errors="coerce")
        out = out.dropna(subset=[x_col, y_col]).reset_index(drop=True)
        return out
    except Exception:
        return df


def _infer_xy_columns(df, x_col_override: str, y_col_override: str):
    """Infer which two columns should be treated as X and Y.

    Priority order:
      1) Explicit overrides if both present in DataFrame.
      2) Heuristic by common header names.
      3) Highest numeric coverage across all columns after coercion.
      4) Fallback to first two columns.
    """
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None, None

    # 1) Explicit overrides
    if (
        x_col_override
        and y_col_override
        and x_col_override in df.columns
        and y_col_override in df.columns
    ):
        return x_col_override, y_col_override

    # 2) Header name heuristics
    cols_lower = {str(c).lower(): c for c in df.columns}
    x_name_candidates = [
        "time",
        "retention time",
        "rt",
        "wavenumber",
        "waveno",
        "cm-1",
        "frequency",
        "mz",
        "m/z",
        "x",
    ]
    y_name_candidates = [
        "intensity",
        "absorbance",
        "signal",
        "response",
        "counts",
        "area",
        "mau",
        "y",
        "value",
    ]
    for xn in x_name_candidates:
        for yn in y_name_candidates:
            if xn in cols_lower and yn in cols_lower:
                return cols_lower[xn], cols_lower[yn]

    # 3) Numeric coverage after coercion
    numeric_score = []
    for c in df.columns:
        try:
            s = pd.to_numeric(df[c], errors="coerce")
            score = int(s.notna().sum())
            numeric_score.append((score, c))
        except Exception:
            continue
    numeric_score.sort(reverse=True)
    top = [c for _score, c in numeric_score if _score > 0]
    if len(top) >= 2:
        return top[0], top[1]

    # 4) Fallback to first two columns
    if len(df.columns) >= 2:
        return df.columns[0], df.columns[1]
    return None, None


def _map_separator_property(sep_prop: str):
    """Map the UI separator property into pandas read_csv arguments.

    Returns (sep_value, extra_kwargs). If sep_value is None, pandas will infer.
    """
    s = (sep_prop or "").strip().lower()
    if s in ("auto", ""):
        return None, {"engine": "python"}
    if s in ("comma", ","):
        return ",", {"engine": "python"}
    if s in ("semicolon", "semi", ";"):
        return ";", {"engine": "python"}
    if s in ("tab", "\t"):
        return "\t", {}
    if s in ("space", "whitespace", "ws"):
        # Use regex sep → requires python engine
        return r"\s+", {"engine": "python"}
    # Custom literal separator
    return s, {"engine": "python"}


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


class ChromSmoothingNode(BaseNode):
    """Smooth a time-series using Savitzky-Golay or moving average.

    Inputs:
      - data (data): list-of-dicts table with columns x_label, y_label

    Outputs:
      - data (data): smoothed series with same columns
    """

    def __init__(self):
        super().__init__("chrom_smoothing", "Chrom Smoothing")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")

        self.set_property("method", "savgol")  # savgol|moving_average
        self.set_property("window_length", 11)
        self.set_property("polyorder", 2)
        self.set_property("ma_window", 5)
        self.set_property("x_label", "x")
        self.set_property("y_label", "y")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": []}

        import numpy as np  # type: ignore
        try:
            import pandas as pd  # type: ignore
        except Exception:
            return {"data": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        method = str(self.get_property("method") or "savgol")
        if method == "savgol":
            try:
                from scipy.signal import savgol_filter  # type: ignore
                wl = int(self.get_property("window_length") or 11)
                po = int(self.get_property("polyorder") or 2)
                wl = max(3, wl | 1)  # make odd and >=3
                y_s = savgol_filter(df[y_label].values.astype(float), wl, max(1, po))
                df[y_label] = y_s
            except Exception as e:
                self.logger.error(f"Savitzky-Golay failed: {e}")
        else:
            # Moving average
            try:
                w = max(1, int(self.get_property("ma_window") or 5))
                df[y_label] = df[y_label].rolling(window=w, min_periods=1, center=True).mean()
            except Exception as e:
                self.logger.error(f"Moving average failed: {e}")

        return {"data": _dataframe_to_rows(df)}


class ChromBaselineNode(BaseNode):
    """Baseline correction using rolling quantile or rolling min.

    Inputs:
      - data (data): list-of-dicts table with columns x_label, y_label

    Outputs:
      - data (data): baseline-corrected series with same columns
      - baseline (data): baseline series
    """

    def __init__(self):
        super().__init__("chrom_baseline", "Chrom Baseline")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")
        self.add_output_port("baseline", "data")

        self.set_property("method", "quantile")  # quantile|min
        self.set_property("window", 51)
        self.set_property("quantile", 0.05)
        self.set_property("x_label", "x")
        self.set_property("y_label", "y")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": [], "baseline": []}

        try:
            import pandas as pd  # type: ignore
        except Exception:
            return {"data": [], "baseline": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        method = str(self.get_property("method") or "quantile")
        window = max(3, int(self.get_property("window") or 51))

        bl = None
        if method == "quantile":
            q = float(self.get_property("quantile") or 0.05)
            try:
                bl = df[y_label].rolling(window=window, min_periods=1, center=True).quantile(q)
            except Exception as e:
                self.logger.error(f"Quantile baseline failed: {e}")
        else:
            try:
                bl = df[y_label].rolling(window=window, min_periods=1, center=True).min()
            except Exception as e:
                self.logger.error(f"Min baseline failed: {e}")

        if bl is None:
            return {"data": _dataframe_to_rows(df), "baseline": []}

        base_df = df[[x_label]].copy()
        base_df["baseline"] = bl.values

        out_df = df.copy()
        try:
            out_df[y_label] = (df[y_label] - bl).clip(lower=0)
        except Exception:
            out_df[y_label] = df[y_label]

        return {"data": _dataframe_to_rows(out_df), "baseline": _dataframe_to_rows(base_df)}


class ChromPeakDetectNode(BaseNode):
    """Detect peaks using scipy.signal.find_peaks.

    Inputs:
      - data (data): list-of-dicts table

    Outputs:
      - peaks (data): table with columns index, x, y, prominence, width
    """

    def __init__(self):
        super().__init__("chrom_peak_detect", "Chrom Peak Detect")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("peaks", "data")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("height", None)
        self.set_property("prominence", 0.0)
        self.set_property("distance", 0)
        self.set_property("width", 0)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"peaks": []}

        import numpy as np  # type: ignore
        from scipy.signal import find_peaks, peak_prominences, peak_widths  # type: ignore

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        series = df[y_label].values.astype(float)
        kw: Dict[str, Any] = {}
        h = self.get_property("height")
        if h is not None:
            try:
                kw["height"] = float(h)
            except Exception:
                pass
        p = float(self.get_property("prominence") or 0.0)
        if p and p > 0:
            kw["prominence"] = p
        d = int(self.get_property("distance") or 0)
        if d and d > 0:
            kw["distance"] = d
        w = int(self.get_property("width") or 0)
        if w and w > 0:
            kw["width"] = w

        idxs, _props = find_peaks(series, **kw)
        if idxs is None or len(idxs) == 0:
            return {"peaks": []}

        prom, _, _ = peak_prominences(series, idxs)
        widths, w_heights, left_ips, right_ips = peak_widths(series, idxs, rel_height=0.5)

        out: List[dict] = []
        for i, idx in enumerate(list(idxs)):
            try:
                out.append({
                    "index": int(idx),
                    "x": float(df.iloc[idx][x_label]),
                    "y": float(df.iloc[idx][y_label]),
                    "prominence": float(prom[i]) if i < len(prom) else None,
                    "width": float(widths[i]) if i < len(widths) else None,
                })
            except Exception:
                pass

        return {"peaks": out}


class ChromIntegrateNode(BaseNode):
    """Integrate areas around peaks or full curve using trapezoidal rule.

    Inputs:
      - data (data): full time-series table
      - peaks (data) optional: detected peaks table

    Outputs:
      - integrals (data): rows with region start/end/x_peak/area
    """

    def __init__(self):
        super().__init__("chrom_integrate", "Chrom Integrate")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_input_port("peaks", "data")
        self.add_output_port("integrals", "data")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("window", 0.1)  # integrate ±window in x-units if peaks provided

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import numpy as np  # type: ignore

        df = _rows_to_dataframe((inputs or {}).get("data"))
        if df is None or len(df) == 0:
            return {"integrals": []}

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        df = _ensure_numeric(df, x_label, y_label)

        peaks_rows = (inputs or {}).get("peaks")
        peaks_df = _rows_to_dataframe(peaks_rows)

        results: List[dict] = []
        if peaks_df is not None and len(peaks_df) > 0 and "x" in peaks_df.columns:
            half = float(self.get_property("window") or 0.1)
            for _, pr in peaks_df.iterrows():
                try:
                    x0 = float(pr["x"]) - half
                    x1 = float(pr["x"]) + half
                except Exception:
                    continue
                seg = df[(df[x_label] >= x0) & (df[x_label] <= x1)]
                if len(seg) < 2:
                    continue
                area = float(np.trapz(seg[y_label].values.astype(float), seg[x_label].values.astype(float)))
                results.append({
                    "x_peak": float(pr.get("x", 0.0)),
                    "start": x0,
                    "end": x1,
                    "area": max(0.0, area),
                })
        else:
            # integrate whole curve
            import numpy as np  # type: ignore
            area = float(np.trapz(df[y_label].values.astype(float), df[x_label].values.astype(float)))
            results.append({"x_peak": None, "start": float(df[x_label].min()), "end": float(df[x_label].max()), "area": max(0.0, area)})

        return {"integrals": results}


class ChromViewerNode(BaseNode):
    """Plot time-series and optional peaks to PNG bytes.

    Inputs:
      - data (data): series
      - peaks (data) optional

    Outputs:
      - image (image): PNG bytes
    """

    def __init__(self):
        super().__init__("chrom_viewer", "Chrom Viewer")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_input_port("peaks", "data")
        self.add_output_port("image", "image")

        self.set_property("x_label", "x")
        self.set_property("y_label", "y")
        self.set_property("title", "Chromatogram/Spectrum")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"image": b""}

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
        import numpy as np  # type: ignore

        peaks_df = _rows_to_dataframe((inputs or {}).get("peaks"))

        x_label = str(self.get_property("x_label") or "x")
        y_label = str(self.get_property("y_label") or "y")
        title = str(self.get_property("title") or "Chromatogram/Spectrum")

        df = _ensure_numeric(df, x_label, y_label)

        fig, ax = plt.subplots(figsize=(7, 4))
        ax.plot(df[x_label].values, df[y_label].values, color="#2E5C8A", lw=1.2)
        if peaks_df is not None and len(peaks_df) > 0 and "x" in peaks_df.columns:
            try:
                ax.scatter(peaks_df["x"].values, peaks_df.get("y", None) if "y" in peaks_df.columns else None, color="#EF4444", s=20, zorder=3, label="Peaks")
                ax.legend(loc="best")
            except Exception:
                pass
        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        ax.set_title(title)
        ax.grid(alpha=0.2)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        return {"image": buf.getvalue()}


