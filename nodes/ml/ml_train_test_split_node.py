"""MLTrainTestSplitNode implementation."""

from .common import *  # noqa: F401,F403

class MLTrainTestSplitNode(_InlineTargetSelectorMixin, BaseNode):
    """Split a dataset into train/test sets with optional stratification.

    Inputs:
      - data (data): DataFrame or list-of-dicts
    Outputs:
      - train_data (data)
      - test_data (data)
    """

    def __init__(self):
        super().__init__("ml_train_test_split", "Train/Test Split")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("train_data", "data")
        self.add_output_port("test_data", "data")

        self.set_property("target_column", "")
        self.set_property("test_size", 0.2)
        self.set_property("random_state", 42)
        self.set_property("shuffle", True)
        self.set_property("stratify", True)
        self.set_property("available_columns", [])
        self.set_property("needs_user_action", False)

        self._build_inline_target_selector("Target column (optional for stratify)")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data_obj = (inputs or {}).get("data")
        df, rows = _to_dataframe(data_obj)
        if df is None and not rows:
            raise ValueError("Input 'data' is required and must be a table")

        # Decide if we need target column for stratification
        target = str(self.get_property("target_column") or "").strip()
        want_stratify = bool(self.get_property("stratify"))

        if df is not None:
            # Column selection pause if stratify requested and no target set
            if want_stratify and not target:
                cols = [str(c) for c in list(df.columns)]
                try:
                    self.set_property("available_columns", cols)
                    self.set_property("needs_user_action", True)
                except Exception:
                    pass
                try:
                    self._manager.pause_user_input(self._node_id, "Select target column and click OK to continue.")  # type: ignore[attr-defined]
                except Exception:
                    pass
                return {"train_data": df.iloc[0:0], "test_data": df.iloc[0:0]}  # empty shells

            # Perform split using scikit-learn when available
            try:
                from sklearn.model_selection import train_test_split  # type: ignore
            except Exception as e:
                raise RuntimeError(f"scikit-learn is required: {e}")

            test_size = float(self.get_property("test_size") or 0.2)
            random_state = int(self.get_property("random_state") or 42)
            shuffle = bool(self.get_property("shuffle"))

            if want_stratify and target and target in df.columns:
                y = df[target]
                tr, te = train_test_split(df, test_size=max(0.01, min(0.99, test_size)), random_state=random_state, shuffle=shuffle, stratify=y)
            else:
                tr, te = train_test_split(df, test_size=max(0.01, min(0.99, test_size)), random_state=random_state, shuffle=shuffle)
            try:
                self.report_progress(100, "Split completed")
            except Exception:
                pass
            return {"train_data": tr, "test_data": te}

        # Fallback split for list-of-dicts
        n = len(rows)
        if n <= 1:
            return {"train_data": rows, "test_data": []}
        test_size = float(self.get_property("test_size") or 0.2)
        k = max(1, int(n * max(0.01, min(0.99, test_size))))
        return {"train_data": rows[:-k], "test_data": rows[-k:]}
