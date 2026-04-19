"""
Response Surface Analysis nodes.

Fit simple response surface models (linear/quadratic/cubic or Gaussian Process)
on tabular data to produce metrics and surface grids for plotting/optimization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _rows_to_dataframe(rows: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if rows is None:
        return None
    try:
        from pandas import DataFrame as _PDDataFrame  # type: ignore
        if isinstance(rows, _PDDataFrame):
            return rows
    except Exception:
        pass
    if isinstance(rows, list) and (len(rows) == 0 or isinstance(rows[0], dict)):
        try:
            return pd.DataFrame(rows)
        except Exception:
            return None
    return None


def _df_to_rows(df: Any) -> List[dict]:
    try:
        return [] if df is None else df.to_dict("records")  # type: ignore
    except Exception:
        return []


class RSAPrepNode(BaseNode):
    """Prepare dataset: filter by label (optional), drop NaN, choose response and factors.

    Inputs:
      - data (data): table with response and factor columns

    Outputs:
      - data (data): processed table
    """

    def __init__(self):
        super().__init__("rsa_prep", "RSA Prepare Dataset")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")

        self.set_property("analysis_mode", "all_labels")  # all_labels|per_label
        self.set_property("label_column", "annotation_label")
        self.set_property("selected_label", "")
        self.set_property("response", "peak_area")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": []}

        import pandas as pd  # type: ignore

        mode = str(self.get_property("analysis_mode") or "all_labels")
        label_col = str(self.get_property("label_column") or "annotation_label")
        selected = str(self.get_property("selected_label") or "").strip()
        response = str(self.get_property("response") or "peak_area")

        if mode == "per_label" and selected:
            if label_col in df.columns:
                df = df[df[label_col].astype(str) == selected]
        # Drop rows with missing response
        if response in df.columns:
            df = df.dropna(subset=[response])
        df = df.reset_index(drop=True)
        return {"data": _df_to_rows(df)}


class RSAFitNode(BaseNode):
    """Fit RSA model (linear/quadratic/cubic/gaussian_rbf) with simple metrics.

    Inputs:
      - data (data): processed table

    Outputs:
      - model (model): fitted estimator or pipeline
      - metrics (data): dict rows with r2, rmse, cv_mean, cv_std
    """

    def __init__(self):
        super().__init__("rsa_fit", "RSA Fit")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("model", "model")
        self.add_output_port("metrics", "data")

        self.set_property("response", "peak_area")
        self.set_property("factors", "")  # comma-separated names; empty → all numeric except response
        self.set_property("model_type", "quadratic")  # linear|quadratic|cubic|gaussian_rbf
        self.set_property("cv_folds", 5)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"model": None, "metrics": []}

        import numpy as np  # type: ignore
        from sklearn.model_selection import cross_val_score  # type: ignore
        from sklearn.metrics import r2_score, mean_squared_error  # type: ignore
        from sklearn.preprocessing import StandardScaler  # type: ignore
        from sklearn.pipeline import Pipeline  # type: ignore
        from sklearn.linear_model import LinearRegression  # type: ignore
        from sklearn.preprocessing import PolynomialFeatures  # type: ignore
        from sklearn.gaussian_process import GaussianProcessRegressor  # type: ignore
        from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C  # type: ignore

        response = str(self.get_property("response") or "peak_area")
        f_list = [s.strip() for s in str(self.get_property("factors") or "").split(",") if s.strip()]

        # Build X, y
        if response not in df.columns:
            return {"model": None, "metrics": []}

        if not f_list:
            # choose numeric columns except response
            import pandas as pd  # type: ignore
            numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            f_list = [c for c in numeric_cols if c != response]
        if not f_list:
            return {"model": None, "metrics": []}

        X = df[f_list].values
        y = df[response].values

        mtype = str(self.get_property("model_type") or "quadratic")
        if mtype == "linear":
            model = Pipeline([("scaler", StandardScaler()), ("reg", LinearRegression())])
        elif mtype == "quadratic":
            model = Pipeline([("scaler", StandardScaler()), ("poly", PolynomialFeatures(degree=2, include_bias=False)), ("reg", LinearRegression())])
        elif mtype == "cubic":
            model = Pipeline([("scaler", StandardScaler()), ("poly", PolynomialFeatures(degree=3, include_bias=False)), ("reg", LinearRegression())])
        else:
            kernel = C(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-2, 1e2))
            model = Pipeline([("scaler", StandardScaler()), ("gpr", GaussianProcessRegressor(kernel=kernel, n_restarts_optimizer=5))])

        # Fit and metrics
        model.fit(X, y)
        y_pred = model.predict(X)
        r2 = float(r2_score(y, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y, y_pred)))

        cv = max(2, int(self.get_property("cv_folds") or 5))
        try:
            cv_scores = cross_val_score(model, X, y, cv=cv, scoring="r2")
            cv_mean = float(cv_scores.mean())
            cv_std = float(cv_scores.std())
        except Exception:
            cv_mean = 0.0
            cv_std = 0.0

        metrics = [{"r2_score": r2, "rmse": rmse, "cv_mean": cv_mean, "cv_std": cv_std, "n_samples": int(len(df)), "n_features": int(len(f_list))}]
        return {"model": model, "metrics": metrics}


class RSASurfaceNode(BaseNode):
    """Generate surface grid Z for first two factors (holding others at mean).

    Inputs:
      - model (model): fitted pipeline
      - data (data): processed table used for factor selection

    Outputs:
      - surface (data): dict with X1, X2, Z, factor1, factor2
    """

    def __init__(self):
        super().__init__("rsa_surface", "RSA Surface")
        self.logger = get_logger(__name__)
        self.add_input_port("model", "model")
        self.add_input_port("data", "data")
        self.add_output_port("surface", "data")

        self.set_property("factors", "")  # empty → auto from numeric columns (excl. response)
        self.set_property("response", "peak_area")
        self.set_property("resolution", 50)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        model = (inputs or {}).get("model")
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if model is None or df is None or len(df) == 0:
            return {"surface": []}

        import numpy as np  # type: ignore
        try:
            import pandas as pd  # type: ignore
        except Exception:
            return {"surface": []}

        response = str(self.get_property("response") or "peak_area")
        f_list = [s.strip() for s in str(self.get_property("factors") or "").split(",") if s.strip()]
        if not f_list:
            numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
            f_list = [c for c in numeric_cols if c != response]
        if len(f_list) < 2:
            return {"surface": []}

        f1, f2 = f_list[0], f_list[1]
        res = max(10, int(self.get_property("resolution") or 50))

        # Prepare ranges and hold others at mean
        mins = df[f_list].min()
        maxs = df[f_list].max()
        means = df[f_list].mean()

        x1_range = np.linspace(float(mins[f1]), float(maxs[f1]), res)
        x2_range = np.linspace(float(mins[f2]), float(maxs[f2]), res)
        X1, X2 = np.meshgrid(x1_range, x2_range)

        grid = []
        for i in range(res * res):
            v = {col: float(means[col]) for col in f_list}
            v[f1] = float(X1.ravel()[i])
            v[f2] = float(X2.ravel()[i])
            grid.append(v)

        grid_df = pd.DataFrame(grid)[f_list]
        try:
            Z = model.predict(grid_df.values)
        except Exception:
            return {"surface": []}

        return {
            "surface": [{
                "X1": X1.tolist(),
                "X2": X2.tolist(),
                "Z": Z.reshape(X1.shape).tolist(),
                "factor1": f1,
                "factor2": f2,
            }]
        }


