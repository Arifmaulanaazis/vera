"""RSASurfaceNode implementation."""

from .common import *  # noqa: F401,F403

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
