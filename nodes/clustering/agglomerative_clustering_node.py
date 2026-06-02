"""AgglomerativeClusteringNode implementation."""

from .common import *  # noqa: F401,F403

class AgglomerativeClusteringNode(BaseNode):
    def __init__(self):
        super().__init__("cluster_agglomerative", "Agglomerative Clustering")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("labels", "data")
        self.set_property("n_clusters", 3)
        self.set_property("linkage", "ward")  # ward, complete, average, single
        self.set_property("affinity", "euclidean")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tab = (inputs or {}).get("data")
        df = _as_dataframe(tab)
        if df is None or df.empty:
            raise ValueError("Input table is required for AgglomerativeClustering")
        try:
            from sklearn.cluster import AgglomerativeClustering  # type: ignore
        except Exception as e:
            raise RuntimeError(f"scikit-learn is required: {e}")
        n_clusters = max(1, int(self.get_property("n_clusters") or 3))
        linkage = str(self.get_property("linkage") or "ward")
        affinity = str(self.get_property("affinity") or "euclidean")
        X = _numeric_df(df)
        # sklearn deprecates 'affinity' in favor of 'metric' for newer versions; try both
        try:
            model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage, affinity=affinity)
        except TypeError:
            model = AgglomerativeClustering(n_clusters=n_clusters, linkage=linkage, metric=affinity)
        labels = list(map(int, list(model.fit_predict(X))))
        return {"labels": [{"label": int(l)} for l in labels]}
