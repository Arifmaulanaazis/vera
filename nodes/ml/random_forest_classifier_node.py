"""RandomForestClassifierNode implementation."""

from .common import *  # noqa: F401,F403

class RandomForestClassifierNode(_BaseEstimatorNode):
    def __init__(self):
        super().__init__("ml_random_forest_classifier", "Random Forest (Classifier)")
        self.set_property("n_estimators", 200)
        self.set_property("max_depth", 0)  # 0 => None
        self.set_property("min_samples_split", 2)
        self.set_property("random_state", 42)

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        def ctor():
            from sklearn.ensemble import RandomForestClassifier  # type: ignore
            md = int(self.get_property("max_depth") or 0)
            return RandomForestClassifier(
                n_estimators=int(self.get_property("n_estimators") or 200),
                max_depth=None if md <= 0 else md,
                min_samples_split=int(self.get_property("min_samples_split") or 2),
                random_state=int(self.get_property("random_state") or 42),
                n_jobs=-1,
            )
        return self._fit_and_predict(ctor, inputs, proba_supported=True)
