"""LogisticRegressionNode implementation."""

from .common import *  # noqa: F401,F403

class LogisticRegressionNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_logistic_regression", "Logistic Regression")
        self.set_property("C", 1.0)
        self.set_property("max_iter", 200)
        self.set_property("solver", "lbfgs")
        self.set_property("penalty", "l2")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.linear_model import LogisticRegression  # type: ignore
            return LogisticRegression(C=float(self.get_property("C") or 1.0), max_iter=int(self.get_property("max_iter") or 200), solver=str(self.get_property("solver") or "lbfgs"), penalty=str(self.get_property("penalty") or "l2"))
        return self._fit_and_predict(ctor, inputs, proba_supported=True)
