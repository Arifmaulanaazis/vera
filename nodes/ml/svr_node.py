"""SVRNode implementation."""

from .common import *  # noqa: F401,F403

class SVRNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_svr", "SVR")
        self.set_property("kernel", "rbf")
        self.set_property("C", 1.0)
        self.set_property("epsilon", 0.1)
        self.set_property("gamma", "scale")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.svm import SVR  # type: ignore
            return SVR(kernel=str(self.get_property("kernel") or "rbf"), C=float(self.get_property("C") or 1.0), epsilon=float(self.get_property("epsilon") or 0.1), gamma=self.get_property("gamma") or "scale")
        return self._fit_and_predict(ctor, inputs, proba_supported=False)
