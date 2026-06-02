"""LinearRegressionNode implementation."""

from .common import *  # noqa: F401,F403

class LinearRegressionNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_linear_regression", "Linear Regression")
        self.set_property("fit_intercept", True)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.linear_model import LinearRegression  # type: ignore
            return LinearRegression(fit_intercept=bool(self.get_property("fit_intercept")))
        # Regressors don't provide predict_proba
        return self._fit_and_predict(ctor, inputs, proba_supported=False)
