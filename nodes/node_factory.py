"""
Node factory for creating node instances.
Centralized registry for all available node types.
"""

from typing import Optional, Dict, Type
from core.nodes import BaseNode


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
    
    def _register_built_in_nodes(self):
        """Register built-in node types."""
        # Import all node modules and register them
        try:
            from nodes.docking_nodes import AutoDockVinaNode, AutoDockVinaGPUNode, DockingAnalysisNode, VinaSplitNode, GridSearchNode, ManualGridBoxNode, MergeMoleculeNode, ReceptorPreparationNode, LigandPreparationNode
            from nodes.batch_docking_nodes import AutoDockVinaBatchNode
            self.register_node("autodock_vina", AutoDockVinaNode)
            self.register_node("autodock_vina_gpu", AutoDockVinaGPUNode)
            self.register_node("autodock_vina_batch", AutoDockVinaBatchNode)
            self.register_node("docking_analysis", DockingAnalysisNode)
            self.register_node("vina_split", VinaSplitNode)
            self.register_node("grid_search", GridSearchNode)
            self.register_node("manual_grid_box", ManualGridBoxNode)
            self.register_node("merge_molecule", MergeMoleculeNode)
            # New: receptor preparation
            self.register_node("receptor_preparation", ReceptorPreparationNode)
            # New: ligand preparation
            self.register_node("ligand_preparation", LigandPreparationNode)
        except ImportError:
            pass
        
        try:
            from nodes.minimization_nodes import RDKitMinimizeNode, OpenBabelMinimizeNode, ConformerGenNode
            self.register_node("rdkit_minimize", RDKitMinimizeNode)
            self.register_node("openbabel_minimize", OpenBabelMinimizeNode)
            self.register_node("conformer_gen", ConformerGenNode)
        except ImportError:
            pass
        
        # Machine Learning
        try:
            from nodes.ml_nodes import (
                MLTrainTestSplitNode,
                LogisticRegressionNode,
                RandomForestClassifierNode,
                SVMClassifierNode,
                KNNClassifierNode,
                LinearRegressionNode,
                RandomForestRegressorNode,
                SVRNode,
            )
            self.register_node("ml_train_test_split", MLTrainTestSplitNode)
            self.register_node("ml_logistic_regression", LogisticRegressionNode)
            self.register_node("ml_random_forest_classifier", RandomForestClassifierNode)
            self.register_node("ml_svm_classifier", SVMClassifierNode)
            self.register_node("ml_knn_classifier", KNNClassifierNode)
            self.register_node("ml_linear_regression", LinearRegressionNode)
            self.register_node("ml_random_forest_regressor", RandomForestRegressorNode)
            self.register_node("ml_svr", SVRNode)
        except ImportError:
            pass

        # Evaluation
        try:
            from nodes.evaluation_nodes import (
                ConfusionMatrixNode,
                ClassificationReportNode,
                RegressionMetricsNode,
            )
            self.register_node("eval_confusion_matrix", ConfusionMatrixNode)
            self.register_node("eval_classification_report", ClassificationReportNode)
            self.register_node("eval_regression_metrics", RegressionMetricsNode)
        except ImportError:
            pass

        # Clustering & Dimensionality Reduction
        try:
            from nodes.clustering_nodes import (
                KMeansNode,
                AgglomerativeClusteringNode,
                PCANode,
            )
            self.register_node("cluster_kmeans", KMeansNode)
            self.register_node("cluster_agglomerative", AgglomerativeClusteringNode)
            self.register_node("dim_pca", PCANode)
        except ImportError:
            pass

        try:
            from nodes.md_nodes import (
                GromacsPreparationNode, GromacsMinimizeNode, 
                GromacsEquilibrateNode, GromacsProductionNode, MDAnalysisNode,
                CharmmGUIInputNode, GromacsInputEditorNode, XTCExtractorNode,
                GromacsPlotingNode, GromacsViewerNode
            )
            self.register_node("gromacs_prep", GromacsPreparationNode)
            self.register_node("gromacs_minimize", GromacsMinimizeNode)
            self.register_node("gromacs_equilibrate", GromacsEquilibrateNode)
            self.register_node("gromacs_production", GromacsProductionNode)
            self.register_node("gromacs_analysis", MDAnalysisNode)
            self.register_node("charmm_gui_input", CharmmGUIInputNode)
            self.register_node("gromacs_input_editor", GromacsInputEditorNode)
            self.register_node("xtc_extractor", XTCExtractorNode)
            self.register_node("gromacs_ploting", GromacsPlotingNode)
            self.register_node("gromacs_viewer", GromacsViewerNode)
        except ImportError:
            pass
        
        try:
            from nodes.visualization_nodes import (
                StructureDraw2DNode,
                ProLIFInteractionNode as ProLIFInteractionNodeCls,
                Web3DViewerNode,
            )
            self.register_node("structure_draw_2d", StructureDraw2DNode)
            self.register_node("prolif_interaction", ProLIFInteractionNodeCls)
            self.register_node("web3d_viewer", Web3DViewerNode)
        except ImportError:
            pass

        # Plotting nodes (separate module)
        try:
            from nodes.plot_nodes import (
                HistogramPlotNode,
                ScatterPlotNode,
                LinePlotNode,
                BarPlotNode,
                PiePlotNode,
                DonutPlotNode,
                HeatmapPlotNode,
                Venn2PlotNode,
                VolcanoPlotNode,
                BoxPlotNode,
                ViolinPlotNode,
                KDEPlotNode,
                HexbinPlotNode,
                AreaPlotNode,
                ECDFPlotNode,
                RadarPlotNode,
                BubblePlotNode,
                StackedBarPlotNode,
                Hist2DPlotNode,
                PairPlotNode,
            )
            self.register_node("plot_histogram", HistogramPlotNode)
            self.register_node("plot_scatter", ScatterPlotNode)
            self.register_node("plot_line", LinePlotNode)
            self.register_node("plot_bar", BarPlotNode)
            self.register_node("plot_pie", PiePlotNode)
            self.register_node("plot_donut", DonutPlotNode)
            self.register_node("plot_heatmap", HeatmapPlotNode)
            self.register_node("plot_venn", Venn2PlotNode)
            self.register_node("plot_volcano", VolcanoPlotNode)
            self.register_node("plot_box", BoxPlotNode)
            self.register_node("plot_violin", ViolinPlotNode)
            self.register_node("plot_kde", KDEPlotNode)
            self.register_node("plot_hexbin", HexbinPlotNode)
            self.register_node("plot_area", AreaPlotNode)
            self.register_node("plot_ecdf", ECDFPlotNode)
            self.register_node("plot_radar", RadarPlotNode)
            self.register_node("plot_bubble", BubblePlotNode)
            self.register_node("plot_stacked_bar", StackedBarPlotNode)
            self.register_node("plot_hist2d", Hist2DPlotNode)
            self.register_node("plot_pairplot", PairPlotNode)
        except ImportError:
            pass
        
        try:
            from nodes.data_nodes import PubChemSearchNode, RCSBPDBNode
            self.register_node("pubchem_search", PubChemSearchNode)
            self.register_node("rcsb_pdb", RCSBPDBNode)
        except ImportError:
            pass

        # Data modification / table transforms
        try:
            from nodes.data_mod_nodes import (
                SelectColumnsNode,
                FilterRowsNode,
                SliceRowsNode,
                DropDuplicatesNode,
                SortRowsNode,
                DataframeMergeNode,
            )
            self.register_node("select_columns", SelectColumnsNode)
            self.register_node("filter_rows", FilterRowsNode)
            self.register_node("slice_rows", SliceRowsNode)
            self.register_node("drop_duplicates", DropDuplicatesNode)
            self.register_node("sort_rows", SortRowsNode)
            self.register_node("merge_dataframes", DataframeMergeNode)
        except ImportError:
            pass
        
        
        try:
            from nodes.io_nodes import (
                FolderInputNode,
                FileInputNode,
                FileOutputNode,
                SaveFileSinkNode,
                TableViewNode,
                TextViewerNode,
                ImageViewerNode,
                TextInputNode,
                SaveDataFrameNode,
                SaveMoleculeNode,
                SaveTextNode,
                SaveJsonNode,
                SaveImageNode,
                # New readers
                SDFReaderNode,
                MOLReaderNode,
                MOL2ReaderNode,
                PDBReaderNode,
                PDBQTReaderNode,
                XYZReaderNode,
                AutoMolReaderNode,
                CSVReaderNode,
                ExcelReaderNode,
                TXTReaderNode,
            )
            self.register_node("folder_input", FolderInputNode)
            self.register_node("file_input", FileInputNode)
            self.register_node("file_output", FileOutputNode)
            self.register_node("save_file", SaveFileSinkNode)
            self.register_node("save_dataframe", SaveDataFrameNode)
            self.register_node("save_molecule", SaveMoleculeNode)
            self.register_node("save_text", SaveTextNode)
            self.register_node("save_json", SaveJsonNode)
            self.register_node("save_image", SaveImageNode)
            self.register_node("table_view", TableViewNode)
            self.register_node("text_view", TextViewerNode)
            self.register_node("image_view", ImageViewerNode)
            self.register_node("text_input", TextInputNode)
            # Readers
            self.register_node("sdf_reader", SDFReaderNode)
            self.register_node("mol_reader", MOLReaderNode)
            self.register_node("mol2_reader", MOL2ReaderNode)
            self.register_node("pdb_reader", PDBReaderNode)
            self.register_node("pdbqt_reader", PDBQTReaderNode)
            self.register_node("xyz_reader", XYZReaderNode)
            self.register_node("mol_reader_auto", AutoMolReaderNode)
            self.register_node("csv_reader", CSVReaderNode)
            self.register_node("excel_reader", ExcelReaderNode)
            self.register_node("txt_reader", TXTReaderNode)
        except ImportError:
            pass

        # Chromatography & Spectroscopy
        try:
            from nodes.chromatography_nodes import (
                ChromReaderNode,
                ChromSmoothingNode,
                ChromBaselineNode,
                ChromPeakDetectNode,
                ChromIntegrateNode,
                ChromViewerNode,
            )
            self.register_node("chrom_reader", ChromReaderNode)
            self.register_node("chrom_smoothing", ChromSmoothingNode)
            self.register_node("chrom_baseline", ChromBaselineNode)
            self.register_node("chrom_peak_detect", ChromPeakDetectNode)
            self.register_node("chrom_integrate", ChromIntegrateNode)
            self.register_node("chrom_viewer", ChromViewerNode)
        except ImportError:
            pass

        # Response Surface Analysis
        try:
            from nodes.rsa_nodes import (
                RSAPrepNode,
                RSAFitNode,
                RSASurfaceNode,
            )
            self.register_node("rsa_prep", RSAPrepNode)
            self.register_node("rsa_fit", RSAFitNode)
            self.register_node("rsa_surface", RSASurfaceNode)
        except ImportError:
            pass

        # ML Model Management
        try:
            from nodes.ml_model_nodes import (
                ModelLoadNode,
                ModelSaveNode,
                ModelTestNode,
                ModelPredictNode,
            )
            self.register_node("ml_model_load", ModelLoadNode)
            self.register_node("ml_model_save", ModelSaveNode)
            self.register_node("ml_model_test", ModelTestNode)
            self.register_node("ml_model_predict", ModelPredictNode)
        except ImportError:
            pass

        # SMILES Input (io_nodes)
        try:
            from nodes.io_nodes import SMILESInputNode
            self.register_node("smiles_input", SMILESInputNode)
        except ImportError:
            pass

        # Cheminformatics: Descriptor, Fingerprint, SMARTS Filter
        try:
            from nodes.chem_nodes import (
                MolDescriptorNode,
                MolFingerprintNode,
                SMARTSFilterNode,
            )
            self.register_node("mol_descriptor", MolDescriptorNode)
            self.register_node("mol_fingerprint", MolFingerprintNode)
            self.register_node("smarts_filter", SMARTSFilterNode)
        except ImportError:
            pass

        # Python Script
        try:
            from nodes.script_nodes import PythonScriptNode
            self.register_node("python_script", PythonScriptNode)
        except ImportError:
            pass

        # Utility: Note / Sticky Note
        try:
            from nodes.utility_nodes import NoteNode
            self.register_node("note", NoteNode)
        except ImportError:
            pass

        # Finally, discover and load user plugins
        try:
            from backend.plugin_manager import load_plugins_into_factory
            load_plugins_into_factory(self)
        except Exception:
            # Never let plugin errors break app startup
            pass

# Global factory instance
node_factory = NodeFactory()
