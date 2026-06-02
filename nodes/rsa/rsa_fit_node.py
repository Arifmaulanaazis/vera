"""RSAFitNode implementation."""

from .common import *  # noqa: F401,F403

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
