"""KNNClassifierNode implementation."""

from .common import *  # noqa: F401,F403

class KNNClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_knn_classifier", "KNN (Classifier)")
        self.set_property("n_neighbors", 5)
        self.set_property("weights", "uniform")
        self.set_property("metric", "minkowski")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.neighbors import KNeighborsClassifier  # type: ignore
            return KNeighborsClassifier(n_neighbors=int(self.get_property("n_neighbors") or 5), weights=str(self.get_property("weights") or "uniform"), metric=str(self.get_property("metric") or "minkowski"))
        return self._fit_and_predict(ctor, inputs, proba_supported=True)
