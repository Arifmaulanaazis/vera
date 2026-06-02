"""RSAPrepNode implementation."""

from .common import *  # noqa: F401,F403

class RSAPrepNode(BaseNode):
    """Prepare dataset: filter by label (optional), drop NaN, choose response and factors.

    Inputs:
      - data (data): table with response and factor columns

    Outputs:
      - data (data): processed table
    """

    def __init__(self):
        super().__init__("rsa_prep", "RSA Prepare Dataset")
        self.logger = get_logger(__name__)
        self.add_input_port("data", "data")
        self.add_output_port("data", "data")

        self.set_property("analysis_mode", "all_labels")  # all_labels|per_label
        self.set_property("label_column", "annotation_label")
        self.set_property("selected_label", "")
        self.set_property("response", "peak_area")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rows = (inputs or {}).get("data")
        df = _rows_to_dataframe(rows)
        if df is None or len(df) == 0:
            return {"data": []}

        import pandas as pd  # type: ignore

        mode = str(self.get_property("analysis_mode") or "all_labels")
        label_col = str(self.get_property("label_column") or "annotation_label")
        selected = str(self.get_property("selected_label") or "").strip()
        response = str(self.get_property("response") or "peak_area")

        if mode == "per_label" and selected:
            if label_col in df.columns:
                df = df[df[label_col].astype(str) == selected]
        # Drop rows with missing response
        if response in df.columns:
            df = df.dropna(subset=[response])
        df = df.reset_index(drop=True)
        return {"data": _df_to_rows(df)}
