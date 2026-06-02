"""KMeansNode implementation."""

from .common import *  # noqa: F401,F403

class KMeansNode(BaseNode):
    def __init__(self):
        super().__init__("cluster_kmeans", "KMeans Clustering")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("labels", "data")
        self.add_output_port("centers", "data")
        self.set_property("n_clusters", 3)
        self.set_property("init", "k-means++")
        self.set_property("n_init", 10)
        self.set_property("random_state", 42)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tab = (inputs or {}).get("data")
        df = _as_dataframe(tab)
        if df is None or df.empty:
            raise ValueError("Input table is required for KMeans")
        try:
            from sklearn.cluster import KMeans  # type: ignore
            import numpy as np  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn is required: {e}")
        n_clusters = max(1, int(self.get_property("n_clusters") or 3))
        n_init = max(1, int(self.get_property("n_init") or 10))
        init = str(self.get_property("init") or "k-means++")
        rs = int(self.get_property("random_state") or 42)
        X = _numeric_df(df)
        km = KMeans(n_clusters=n_clusters, init=init, n_init=n_init, random_state=rs)
        km.fit(X)
        labels = list(map(int, list(km.labels_)))
        centers = km.cluster_centers_.tolist() if hasattr(km, "cluster_centers_") else []
        return {"labels": [{"label": int(l)} for l in labels], "centers": centers}
