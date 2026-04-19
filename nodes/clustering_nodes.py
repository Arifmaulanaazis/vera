"""
Clustering and dimensionality reduction nodes.

This group includes KMeans, Agglomerative (hierarchical) clustering, and PCA.
Outputs include cluster labels and transformed coordinates for plotting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.nodes import BaseNode
from utils.logging_utils import get_logger


def _as_dataframe(obj: Any):
    try:
        import pandas as pd  # type: ignore
    except Exception:
        return None
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, list) and (len(obj) == 0 or isinstance(obj[0], dict)):
        try:
            return pd.DataFrame(obj)
        except Exception:
            return None
    return None


def _numeric_df(df):
    try:
        return df.select_dtypes(include=["number", "bool"]).astype(float)
    except Exception:
        return df


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


