"""
Tests for nodes/ml_nodes.py

Covers: MLTrainTestSplitNode, LogisticRegressionNode, RandomForestClassifierNode,
SVMClassifierNode, KNNClassifierNode, LinearRegressionNode,
RandomForestRegressorNode, SVRNode.

All tests use real sklearn + pandas — no mocking.
"""

import pytest


# ---------------------------------------------------------------------------
# Shared helpers — build real DataFrames for training
# ---------------------------------------------------------------------------

def _classification_df(n=60):
    """Simple binary classification dataset (pandas DataFrame)."""
    pd = pytest.importorskip("pandas")
    import random
    random.seed(42)
    rows = []
    for i in range(n):
        x1 = float(i) / n
        x2 = float(i % 5) / 5.0
        label = 0 if (x1 + x2) < 1.0 else 1
        rows.append({"x1": x1, "x2": x2, "label": label})
    return pd.DataFrame(rows)


def _regression_df(n=60):
    """Simple regression dataset (pandas DataFrame)."""
    pd = pytest.importorskip("pandas")
    rows = []
    for i in range(n):
        x1 = float(i) / n
        x2 = float(i % 7) / 7.0
        y = 3.0 * x1 + 2.0 * x2 + 0.1
        rows.append({"x1": x1, "x2": x2, "target": y})
    return pd.DataFrame(rows)


def _split_df(df, target_col: str, test_size: float = 0.25):
    """Perform a train/test split using sklearn and return (train_df, test_df)."""
    pytest.importorskip("sklearn")
    from sklearn.model_selection import train_test_split
    tr, te = train_test_split(df, test_size=test_size, random_state=42)
    return tr, te


# ---------------------------------------------------------------------------
# module-level helpers from ml_nodes (pure functions)
# ---------------------------------------------------------------------------

class TestMlNodeHelpers:
    def test_is_dataframe_true(self):
        pd = pytest.importorskip("pandas")
        from nodes.ml_nodes import _is_dataframe
        df = pd.DataFrame({"a": [1, 2]})
        assert _is_dataframe(df) is True

    def test_is_dataframe_false_for_list(self):
        from nodes.ml_nodes import _is_dataframe
        assert _is_dataframe([{"a": 1}]) is False

    def test_is_dataframe_false_for_none(self):
        from nodes.ml_nodes import _is_dataframe
        assert _is_dataframe(None) is False

    def test_to_dataframe_from_list_of_dicts(self):
        pytest.importorskip("pandas")
        from nodes.ml_nodes import _to_dataframe
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        df, _ = _to_dataframe(rows)
        assert df is not None
        assert list(df.columns) == ["a", "b"]

    def test_to_dataframe_from_dataframe(self):
        pd = pytest.importorskip("pandas")
        from nodes.ml_nodes import _to_dataframe
        orig = pd.DataFrame({"x": [1, 2]})
        df, _ = _to_dataframe(orig)
        assert df is orig

    def test_to_dataframe_from_none(self):
        from nodes.ml_nodes import _to_dataframe
        df, rows = _to_dataframe(None)
        assert df is None
        assert rows == []

    def test_numeric_columns_of(self):
        pd = pytest.importorskip("pandas")
        from nodes.ml_nodes import _numeric_columns_of
        df = pd.DataFrame({"x": [1.0, 2.0], "label": ["a", "b"], "flag": [True, False]})
        cols = _numeric_columns_of(df)
        assert "x" in cols
        assert "label" not in cols


# ---------------------------------------------------------------------------
# MLTrainTestSplitNode
# ---------------------------------------------------------------------------

class TestMLTrainTestSplitNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import MLTrainTestSplitNode
        self.node = MLTrainTestSplitNode()

    def test_basic_split_sizes(self):
        df = _classification_df(100)
        self.node.set_property("test_size", 0.2)
        self.node.set_property("stratify", False)
        self.node.set_property("shuffle", True)
        result = self.node.execute({"data": df})
        tr = result["train_data"]
        te = result["test_data"]
        assert len(tr) + len(te) == 100

    def test_test_size_honored(self):
        df = _classification_df(100)
        self.node.set_property("test_size", 0.3)
        self.node.set_property("stratify", False)
        result = self.node.execute({"data": df})
        # 30 ± 2 test rows (sklearn rounding)
        assert 28 <= len(result["test_data"]) <= 32

    def test_no_data_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({"data": None})

    def test_empty_dataframe_raises(self):
        # sklearn raises ValueError when train set would be empty.
        pd = pytest.importorskip("pandas")
        df = pd.DataFrame({"x": [], "y": []})
        self.node.set_property("stratify", False)
        self.node.set_property("test_size", 0.2)
        with pytest.raises(ValueError):
            self.node.execute({"data": df})

    def test_list_of_dicts_fallback(self):
        rows = [{"a": i, "b": i * 2} for i in range(20)]
        self.node.set_property("stratify", False)
        self.node.set_property("test_size", 0.25)
        result = self.node.execute({"data": rows})
        assert len(result["train_data"]) + len(result["test_data"]) == 20

    def test_train_data_is_dataframe(self):
        pd = pytest.importorskip("pandas")
        df = _classification_df(50)
        self.node.set_property("stratify", False)
        result = self.node.execute({"data": df})
        assert isinstance(result["train_data"], pd.DataFrame)

    def test_test_data_is_dataframe(self):
        pd = pytest.importorskip("pandas")
        df = _classification_df(50)
        self.node.set_property("stratify", False)
        result = self.node.execute({"data": df})
        assert isinstance(result["test_data"], pd.DataFrame)


# ---------------------------------------------------------------------------
# LogisticRegressionNode
# ---------------------------------------------------------------------------

class TestLogisticRegressionNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import LogisticRegressionNode
        self.node = LogisticRegressionNode()

    def _inputs(self):
        df = _classification_df(80)
        tr, te = _split_df(df, "label")
        self.node.set_property("target_column", "label")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_returns_predictions_list(self):
        result = self.node.execute(self._inputs())
        assert isinstance(result["predictions"], list)

    def test_predictions_not_empty(self):
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_predictions_have_prediction_key(self):
        result = self.node.execute(self._inputs())
        for row in result["predictions"]:
            assert "prediction" in row

    def test_prediction_values_binary(self):
        result = self.node.execute(self._inputs())
        for row in result["predictions"]:
            assert row["prediction"] in (0, 1)

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "label")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})

    def test_model_has_predict_method(self):
        result = self.node.execute(self._inputs())
        assert hasattr(result["model"], "predict")

    def test_no_test_data_still_returns_model(self):
        df = _classification_df(80)
        tr, _ = _split_df(df, "label")
        self.node.set_property("target_column", "label")
        result = self.node.execute({"train_data": tr, "test_data": None})
        assert result["model"] is not None

    def test_custom_C_parameter(self):
        self.node.set_property("C", 0.1)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_probabilities_present(self):
        result = self.node.execute(self._inputs())
        # Logistic regression supports predict_proba, so probabilities should be populated
        assert "probabilities" in result


# ---------------------------------------------------------------------------
# RandomForestClassifierNode
# ---------------------------------------------------------------------------

class TestRandomForestClassifierNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import RandomForestClassifierNode
        self.node = RandomForestClassifierNode()

    def _inputs(self):
        df = _classification_df(80)
        tr, te = _split_df(df, "label")
        self.node.set_property("target_column", "label")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        self.node.set_property("n_estimators", 10)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        self.node.set_property("n_estimators", 10)
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_prediction_values_binary(self):
        self.node.set_property("n_estimators", 10)
        result = self.node.execute(self._inputs())
        for row in result["predictions"]:
            assert row["prediction"] in (0, 1)

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "label")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})

    def test_custom_n_estimators(self):
        self.node.set_property("n_estimators", 5)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None


# ---------------------------------------------------------------------------
# SVMClassifierNode
# ---------------------------------------------------------------------------

class TestSVMClassifierNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import SVMClassifierNode
        self.node = SVMClassifierNode()

    def _inputs(self):
        df = _classification_df(60)
        tr, te = _split_df(df, "label")
        self.node.set_property("target_column", "label")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_rbf_kernel(self):
        self.node.set_property("kernel", "rbf")
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_linear_kernel(self):
        self.node.set_property("kernel", "linear")
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "label")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})


# ---------------------------------------------------------------------------
# KNNClassifierNode
# ---------------------------------------------------------------------------

class TestKNNClassifierNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import KNNClassifierNode
        self.node = KNNClassifierNode()

    def _inputs(self):
        df = _classification_df(60)
        tr, te = _split_df(df, "label")
        self.node.set_property("target_column", "label")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_custom_n_neighbors(self):
        self.node.set_property("n_neighbors", 3)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "label")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})


# ---------------------------------------------------------------------------
# LinearRegressionNode
# ---------------------------------------------------------------------------

class TestLinearRegressionNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import LinearRegressionNode
        self.node = LinearRegressionNode()

    def _inputs(self):
        df = _regression_df(80)
        tr, te = _split_df(df, "target")
        self.node.set_property("target_column", "target")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_prediction_values_are_float(self):
        result = self.node.execute(self._inputs())
        for row in result["predictions"]:
            pred = row["prediction"]
            assert isinstance(pred, (int, float)), f"Expected numeric prediction, got {type(pred)}"

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "target")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})

    def test_model_has_coef(self):
        result = self.node.execute(self._inputs())
        assert hasattr(result["model"], "coef_")


# ---------------------------------------------------------------------------
# RandomForestRegressorNode
# ---------------------------------------------------------------------------

class TestRandomForestRegressorNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import RandomForestRegressorNode
        self.node = RandomForestRegressorNode()

    def _inputs(self):
        df = _regression_df(80)
        tr, te = _split_df(df, "target")
        self.node.set_property("target_column", "target")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        self.node.set_property("n_estimators", 10)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        self.node.set_property("n_estimators", 10)
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "target")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})


# ---------------------------------------------------------------------------
# SVRNode
# ---------------------------------------------------------------------------

class TestSVRNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("pandas")
        pytest.importorskip("sklearn")
        from nodes.ml_nodes import SVRNode
        self.node = SVRNode()

    def _inputs(self):
        df = _regression_df(60)
        tr, te = _split_df(df, "target")
        self.node.set_property("target_column", "target")
        return {"train_data": tr, "test_data": te}

    def test_returns_model(self):
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_predictions_not_empty(self):
        result = self.node.execute(self._inputs())
        assert len(result["predictions"]) > 0

    def test_rbf_kernel(self):
        self.node.set_property("kernel", "rbf")
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_linear_kernel(self):
        self.node.set_property("kernel", "linear")
        result = self.node.execute(self._inputs())
        assert result["model"] is not None

    def test_no_train_data_raises(self):
        self.node.set_property("target_column", "target")
        with pytest.raises(ValueError):
            self.node.execute({"train_data": None, "test_data": None})

    def test_custom_C_parameter(self):
        self.node.set_property("C", 0.5)
        result = self.node.execute(self._inputs())
        assert result["model"] is not None
