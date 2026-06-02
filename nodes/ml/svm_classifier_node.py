"""SVMClassifierNode implementation."""

from .common import *  # noqa: F401,F403

class SVMClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_svm_classifier", "SVM (Classifier)")
        self.set_property("kernel", "rbf")
        self.set_property("C", 1.0)
        self.set_property("gamma", "scale")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.svm import SVC  # type: ignore
            return SVC(kernel=str(self.get_property("kernel") or "rbf"), C=float(self.get_property("C") or 1.0), gamma=self.get_property("gamma") or "scale", probability=True)
        return self._fit_and_predict(ctor, inputs, proba_supported=True)
