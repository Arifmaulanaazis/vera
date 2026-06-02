"""
Node factory for creating node instances.
Centralized registry for all available node types.
"""

from __future__ import annotations

from importlib import import_module
from typing import Dict, Optional, Sequence, Type

from core.nodes import BaseNode


NodeRegistration = tuple[str, str]
NodeGroup = tuple[str, Sequence[NodeRegistration]]


BUILT_IN_NODE_GROUPS: tuple[NodeGroup, ...] = (
    (
        "nodes.docking",
        (
            ("autodock_vina", "AutoDockVinaNode"),
            ("autodock_vina_gpu", "AutoDockVinaGPUNode"),
            ("docking_analysis", "DockingAnalysisNode"),
            ("vina_split", "VinaSplitNode"),
            ("grid_search", "GridSearchNode"),
            ("manual_grid_box", "ManualGridBoxNode"),
            ("merge_molecule", "MergeMoleculeNode"),
            ("receptor_preparation", "ReceptorPreparationNode"),
            ("ligand_preparation", "LigandPreparationNode"),
        ),
    ),
    (
        "nodes.batch_docking",
        (("autodock_vina_batch", "AutoDockVinaBatchNode"),),
    ),
    (
        "nodes.minimization",
        (
            ("rdkit_minimize", "RDKitMinimizeNode"),
            ("openbabel_minimize", "OpenBabelMinimizeNode"),
            ("conformer_gen", "ConformerGenNode"),
        ),
    ),
    (
        "nodes.ml",
        (
            ("ml_train_test_split", "MLTrainTestSplitNode"),
            ("ml_logistic_regression", "LogisticRegressionNode"),
            ("ml_random_forest_classifier", "RandomForestClassifierNode"),
            ("ml_svm_classifier", "SVMClassifierNode"),
            ("ml_knn_classifier", "KNNClassifierNode"),
            ("ml_linear_regression", "LinearRegressionNode"),
            ("ml_random_forest_regressor", "RandomForestRegressorNode"),
            ("ml_svr", "SVRNode"),
        ),
    ),
    (
        "nodes.evaluation",
        (
            ("eval_confusion_matrix", "ConfusionMatrixNode"),
            ("eval_classification_report", "ClassificationReportNode"),
            ("eval_regression_metrics", "RegressionMetricsNode"),
        ),
    ),
    (
        "nodes.clustering",
        (
            ("cluster_kmeans", "KMeansNode"),
            ("cluster_agglomerative", "AgglomerativeClusteringNode"),
            ("dim_pca", "PCANode"),
        ),
    ),
    (
        "nodes.md",
        (
            ("gromacs_prep", "GromacsPreparationNode"),
            ("gromacs_minimize", "GromacsMinimizeNode"),
            ("gromacs_equilibrate", "GromacsEquilibrateNode"),
            ("gromacs_production", "GromacsProductionNode"),
            ("gromacs_analysis", "MDAnalysisNode"),
            ("charmm_gui_input", "CharmmGUIInputNode"),
            ("gromacs_input_editor", "GromacsInputEditorNode"),
            ("xtc_extractor", "XTCExtractorNode"),
            ("gromacs_ploting", "GromacsPlotingNode"),
            ("gromacs_viewer", "GromacsViewerNode"),
        ),
    ),
    (
        "nodes.visualization",
        (
            ("structure_draw_2d", "StructureDraw2DNode"),
            ("prolif_interaction", "ProLIFInteractionNode"),
            ("web3d_viewer", "Web3DViewerNode"),
        ),
    ),
    (
        "nodes.plot",
        (
            ("plot_histogram", "HistogramPlotNode"),
            ("plot_scatter", "ScatterPlotNode"),
            ("plot_line", "LinePlotNode"),
            ("plot_bar", "BarPlotNode"),
            ("plot_pie", "PiePlotNode"),
            ("plot_donut", "DonutPlotNode"),
            ("plot_heatmap", "HeatmapPlotNode"),
            ("plot_venn", "Venn2PlotNode"),
            ("plot_volcano", "VolcanoPlotNode"),
            ("plot_box", "BoxPlotNode"),
            ("plot_violin", "ViolinPlotNode"),
            ("plot_kde", "KDEPlotNode"),
            ("plot_hexbin", "HexbinPlotNode"),
            ("plot_area", "AreaPlotNode"),
            ("plot_ecdf", "ECDFPlotNode"),
            ("plot_radar", "RadarPlotNode"),
            ("plot_bubble", "BubblePlotNode"),
            ("plot_stacked_bar", "StackedBarPlotNode"),
            ("plot_hist2d", "Hist2DPlotNode"),
            ("plot_pairplot", "PairPlotNode"),
        ),
    ),
    (
        "nodes.data",
        (
            ("pubchem_search", "PubChemSearchNode"),
            ("rcsb_pdb", "RCSBPDBNode"),
        ),
    ),
    (
        "nodes.data_mod",
        (
            ("select_columns", "SelectColumnsNode"),
            ("filter_rows", "FilterRowsNode"),
            ("slice_rows", "SliceRowsNode"),
            ("drop_duplicates", "DropDuplicatesNode"),
            ("sort_rows", "SortRowsNode"),
            ("merge_dataframes", "DataframeMergeNode"),
        ),
    ),
    (
        "nodes.io",
        (
            ("folder_input", "FolderInputNode"),
            ("file_input", "FileInputNode"),
            ("file_output", "FileOutputNode"),
            ("save_file", "SaveFileSinkNode"),
            ("save_dataframe", "SaveDataFrameNode"),
            ("save_molecule", "SaveMoleculeNode"),
            ("save_text", "SaveTextNode"),
            ("save_json", "SaveJsonNode"),
            ("save_image", "SaveImageNode"),
            ("table_view", "TableViewNode"),
            ("text_view", "TextViewerNode"),
            ("image_view", "ImageViewerNode"),
            ("text_input", "TextInputNode"),
            ("sdf_reader", "SDFReaderNode"),
            ("mol_reader", "MOLReaderNode"),
            ("mol2_reader", "MOL2ReaderNode"),
            ("pdb_reader", "PDBReaderNode"),
            ("pdbqt_reader", "PDBQTReaderNode"),
            ("xyz_reader", "XYZReaderNode"),
            ("mol_reader_auto", "AutoMolReaderNode"),
            ("csv_reader", "CSVReaderNode"),
            ("excel_reader", "ExcelReaderNode"),
            ("txt_reader", "TXTReaderNode"),
            ("smiles_input", "SMILESInputNode"),
        ),
    ),
    (
        "nodes.chromatography",
        (
            ("chrom_reader", "ChromReaderNode"),
            ("chrom_smoothing", "ChromSmoothingNode"),
            ("chrom_baseline", "ChromBaselineNode"),
            ("chrom_peak_detect", "ChromPeakDetectNode"),
            ("chrom_integrate", "ChromIntegrateNode"),
            ("chrom_viewer", "ChromViewerNode"),
        ),
    ),
    (
        "nodes.rsa",
        (
            ("rsa_prep", "RSAPrepNode"),
            ("rsa_fit", "RSAFitNode"),
            ("rsa_surface", "RSASurfaceNode"),
        ),
    ),
    (
        "nodes.ml_model",
        (
            ("ml_model_load", "ModelLoadNode"),
            ("ml_model_save", "ModelSaveNode"),
            ("ml_model_test", "ModelTestNode"),
            ("ml_model_predict", "ModelPredictNode"),
        ),
    ),
    (
        "nodes.chem",
        (
            ("mol_descriptor", "MolDescriptorNode"),
            ("mol_fingerprint", "MolFingerprintNode"),
            ("smarts_filter", "SMARTSFilterNode"),
        ),
    ),
    (
        "nodes.script",
        (("python_script", "PythonScriptNode"),),
    ),
    (
        "nodes.utility",
        (("note", "NoteNode"),),
    ),
)


class NodeFactory:
    """Factory for creating node instances."""

    def __init__(self):
        self._node_registry: Dict[str, Type[BaseNode]] = {}
        self._register_built_in_nodes()

    def register_node(self, node_type: str, node_class: Type[BaseNode]):
        """Register a node type with its class."""
        self._node_registry[node_type] = node_class

    def create_node(self, node_type: str) -> Optional[BaseNode]:
        """Create a node instance of the specified type."""
        node_class = self._node_registry.get(node_type)
        if node_class:
            return node_class()
        return None

    def get_available_nodes(self) -> Dict[str, Type[BaseNode]]:
        """Get all available node types."""
        return self._node_registry.copy()

    def _register_node_group(
        self,
        module_name: str,
        registrations: Sequence[NodeRegistration],
    ) -> None:
        try:
            module = import_module(module_name)
            resolved = [
                (node_type, getattr(module, class_name))
                for node_type, class_name in registrations
            ]
        except (ImportError, AttributeError):
            return

        for node_type, node_class in resolved:
            self.register_node(node_type, node_class)

    def _register_built_in_nodes(self):
        """Register built-in node types."""
        for module_name, registrations in BUILT_IN_NODE_GROUPS:
            self._register_node_group(module_name, registrations)

        try:
            from backend.plugin_manager import load_plugins_into_factory

            load_plugins_into_factory(self)
        except Exception:
            # Never let plugin errors break app startup.
            pass


node_factory = NodeFactory()
