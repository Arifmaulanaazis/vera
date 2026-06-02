"""PCANode implementation."""

from .common import *  # noqa: F401,F403

class PCANode(BaseNode):
    """Principal Component Analysis: project to N components and emit coordinates.

    Inputs:
      - data (data): table
    Outputs:
      - components (data): transformed coordinates as list-of-dicts
      - explained_variance (data): list of floats
    """

    def __init__(self):
        super().__init__("dim_pca", "PCA")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("components", "data")
        self.add_output_port("explained_variance", "data")
        self.set_property("n_components", 2)
        self.set_property("standardize", True)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tab = (inputs or {}).get("data")
        df = _as_dataframe(tab)
        if df is None or df.empty:
            raise ValueError("Input table is required for PCA")
        try:
            from sklearn.decomposition import PCA  # type: ignore
            from sklearn.pipeline import make_pipeline  # type: ignore
            from sklearn.preprocessing import StandardScaler  # type: ignore
            import numpy as np  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn is required: {e}")
        n = max(1, int(self.get_property("n_components") or 2))
        X = _numeric_df(df)
        use_std = bool(self.get_property("standardize"))
        if use_std:
            pipe = make_pipeline(StandardScaler(), PCA(n_components=n))
        else:
            pipe = make_pipeline(PCA(n_components=n))
        Xt = pipe.fit_transform(X)
        try:
            # Extract PCA from pipeline
            pca = None
            for step in getattr(pipe, "steps", []):
                if hasattr(step[1], "explained_variance_ratio_"):
                    pca = step[1]
                    break
            ev = list(map(float, list(getattr(pca, "explained_variance_ratio_", [])))) if pca is not None else []
        except Exception:
            ev = []
        rows: List[dict] = []
        try:
            for i in range(len(Xt)):
                r = {f"PC{j+1}": float(Xt[i][j]) for j in range(min(n, len(Xt[i])))}
                r["index"] = i
                rows.append(r)
        except Exception:
            rows = []
        return {"components": rows, "explained_variance": ev}
