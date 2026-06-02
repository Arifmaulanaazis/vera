"""
Tests for nodes/chem_nodes.py

Covers MolDescriptorNode, MolFingerprintNode, and SMARTSFilterNode.
All tests use real RDKit molecules â€” no mocking.
"""

import pytest


# ---------------------------------------------------------------------------
# Shared helper â€” build real RDKit molecules from SMILES
# ---------------------------------------------------------------------------

def _mol(smiles: str):
    """Return an RDKit Mol from SMILES, or skip if RDKit unavailable."""
    rdkit = pytest.importorskip("rdkit")
    from rdkit import Chem
    m = Chem.MolFromSmiles(smiles)
    if m is None:
        pytest.skip(f"RDKit could not parse SMILES: {smiles}")
    return m


def _mols(*smiles_list):
    """Return a list of real RDKit Mol objects."""
    return [_mol(s) for s in smiles_list]


# ---------------------------------------------------------------------------
# MolDescriptorNode
# ---------------------------------------------------------------------------

class TestMolDescriptorNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("rdkit")
        pytest.importorskip("pandas")
        from nodes.chem import MolDescriptorNode
        self.node = MolDescriptorNode()

    def test_lipinski_preset_returns_dataframe(self):
        self.node.set_property("preset", "lipinski")
        mols = _mols("c1ccccc1", "CC(=O)O", "CCO")
        result = self.node.execute({"molecules": mols})
        import pandas as pd
        assert isinstance(result["data"], pd.DataFrame)
        assert len(result["data"]) == 3

    def test_lipinski_columns_present(self):
        self.node.set_property("preset", "lipinski")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        for col in ("MolWt", "MolLogP", "NumHDonors", "NumHAcceptors", "TPSA", "NumRotatableBonds"):
            assert col in df.columns, f"Missing column: {col}"

    def test_physicochemical_preset(self):
        self.node.set_property("preset", "physicochemical")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        for col in ("RingCount", "NumAromaticRings", "FractionCSP3", "MolMR"):
            assert col in df.columns, f"Missing column: {col}"

    def test_all_preset_returns_many_columns(self):
        self.node.set_property("preset", "all")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        # RDKit has ~200 descriptors; "all" should produce at least 100 columns
        assert df.shape[1] > 100

    def test_name_column_present(self):
        self.node.set_property("preset", "lipinski")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        assert "name" in result["data"].columns

    def test_no_molecules_raises(self):
        with pytest.raises(ValueError, match="No molecules"):
            self.node.execute({"molecules": []})

    def test_none_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({"molecules": None})

    def test_missing_key_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_validate_returns_true(self):
        ok, msg = self.node.validate()
        assert ok is True

    def test_single_molecule_one_row(self):
        self.node.set_property("preset", "lipinski")
        mols = _mols("CCO")
        result = self.node.execute({"molecules": mols})
        assert len(result["data"]) == 1

    def test_descriptor_values_are_numeric(self):
        self.node.set_property("preset", "lipinski")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        mw = df["MolWt"].iloc[0]
        assert isinstance(mw, (int, float))
        assert mw > 0

    def test_custom_preset_with_descriptors(self):
        self.node.set_property("preset", "custom")
        self.node.set_property("custom_descriptors", "MolWt, MolLogP")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        assert "MolWt" in df.columns
        assert "MolLogP" in df.columns


# ---------------------------------------------------------------------------
# MolFingerprintNode
# ---------------------------------------------------------------------------

class TestMolFingerprintNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("rdkit")
        pytest.importorskip("pandas")
        from nodes.chem import MolFingerprintNode
        self.node = MolFingerprintNode()

    def test_morgan_returns_dataframe(self):
        self.node.set_property("fp_type", "Morgan")
        self.node.set_property("n_bits", 512)
        mols = _mols("c1ccccc1", "CCO")
        result = self.node.execute({"molecules": mols})
        import pandas as pd
        assert isinstance(result["data"], pd.DataFrame)
        assert len(result["data"]) == 2

    def test_morgan_bit_columns(self):
        self.node.set_property("fp_type", "Morgan")
        self.node.set_property("n_bits", 64)
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        # Should have 'name' + 64 bit columns
        assert "bit_0" in df.columns
        assert "bit_63" in df.columns
        assert "name" in df.columns

    def test_maccs_fingerprint(self):
        self.node.set_property("fp_type", "MACCS")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        assert len(df) == 1
        # MACCS keys has 167 bits
        assert "bit_0" in df.columns

    def test_rdkit_fingerprint(self):
        self.node.set_property("fp_type", "RDKit")
        self.node.set_property("n_bits", 256)
        mols = _mols("CCO")
        result = self.node.execute({"molecules": mols})
        assert len(result["data"]) == 1

    def test_topologicaltorsion_fingerprint(self):
        # TopologicalTorsion BitVect may not exist in all RDKit builds.
        # The node either returns a DataFrame or raises ValueError â€” both are valid.
        from rdkit.Chem import rdMolDescriptors
        self.node.set_property("fp_type", "TopologicalTorsion")
        mols = _mols("c1ccccc1CC")
        if not hasattr(rdMolDescriptors, "GetTopologicalTorsionFingerprintAsBitVect"):
            with pytest.raises(ValueError):
                self.node.execute({"molecules": mols})
        else:
            result = self.node.execute({"molecules": mols})
            assert len(result["data"]) == 1

    def test_atompair_fingerprint(self):
        # AtomPair BitVect may not exist in all RDKit builds.
        from rdkit.Chem import rdMolDescriptors
        self.node.set_property("fp_type", "AtomPair")
        mols = _mols("c1ccccc1")
        if not hasattr(rdMolDescriptors, "GetAtomPairFingerprintAsBitVect"):
            with pytest.raises(ValueError):
                self.node.execute({"molecules": mols})
        else:
            result = self.node.execute({"molecules": mols})
            assert len(result["data"]) == 1

    def test_bit_values_are_0_or_1(self):
        self.node.set_property("fp_type", "Morgan")
        self.node.set_property("n_bits", 64)
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        for col in [c for c in df.columns if c.startswith("bit_")]:
            val = df[col].iloc[0]
            assert val in (0, 1), f"Bit column {col} has unexpected value {val}"

    def test_no_molecules_raises(self):
        with pytest.raises(ValueError, match="No molecules"):
            self.node.execute({"molecules": []})

    def test_none_input_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({"molecules": None})

    def test_missing_key_raises(self):
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_validate_valid_nbits(self):
        self.node.set_property("n_bits", 2048)
        ok, msg = self.node.validate()
        assert ok is True

    def test_validate_zero_nbits_fails(self):
        self.node.set_property("n_bits", 0)
        ok, msg = self.node.validate()
        assert ok is False

    def test_different_molecules_give_different_fps(self):
        self.node.set_property("fp_type", "Morgan")
        self.node.set_property("n_bits", 512)
        # Benzene and ethanol should give different Morgan fingerprints
        mols = _mols("c1ccccc1", "CCO")
        result = self.node.execute({"molecules": mols})
        df = result["data"]
        row0 = list(df.iloc[0][[c for c in df.columns if c.startswith("bit_")]])
        row1 = list(df.iloc[1][[c for c in df.columns if c.startswith("bit_")]])
        assert row0 != row1, "Expected different fingerprints for benzene and ethanol"


# ---------------------------------------------------------------------------
# SMARTSFilterNode
# ---------------------------------------------------------------------------

class TestSMARTSFilterNode:
    @pytest.fixture(autouse=True)
    def setup(self, lightweight):
        pytest.importorskip("rdkit")
        from nodes.chem import SMARTSFilterNode
        self.node = SMARTSFilterNode()

    def _aromatic_mols(self):
        """Return a list with benzene, toluene, and ethanol."""
        return _mols("c1ccccc1", "Cc1ccccc1", "CCO")

    def test_aromatic_ring_filter_matched(self):
        self.node.set_property("smarts", "c1ccccc1")
        result = self.node.execute({"molecules": self._aromatic_mols()})
        assert len(result["matched"]) == 2

    def test_aromatic_ring_filter_unmatched(self):
        self.node.set_property("smarts", "c1ccccc1")
        result = self.node.execute({"molecules": self._aromatic_mols()})
        assert len(result["unmatched"]) == 1

    def test_matched_plus_unmatched_equals_total(self):
        self.node.set_property("smarts", "c1ccccc1")
        mols = self._aromatic_mols()
        result = self.node.execute({"molecules": mols})
        assert len(result["matched"]) + len(result["unmatched"]) == len(mols)

    def test_hydroxyl_filter(self):
        self.node.set_property("smarts", "[OX2H]")
        mols = _mols("CCO", "c1ccccc1", "CC(O)C")
        result = self.node.execute({"molecules": mols})
        # ethanol and isopropanol have -OH
        assert len(result["matched"]) == 2
        assert len(result["unmatched"]) == 1

    def test_no_match_everything_goes_to_unmatched(self):
        self.node.set_property("smarts", "[Fe]")
        mols = _mols("c1ccccc1", "CCO")
        result = self.node.execute({"molecules": mols})
        assert len(result["matched"]) == 0
        assert len(result["unmatched"]) == 2

    def test_all_match(self):
        self.node.set_property("smarts", "[C,c]")  # any carbon
        mols = _mols("c1ccccc1", "CCO", "CC(=O)O")
        result = self.node.execute({"molecules": mols})
        assert len(result["matched"]) == 3
        assert len(result["unmatched"]) == 0

    def test_no_molecules_raises(self):
        self.node.set_property("smarts", "c1ccccc1")
        with pytest.raises(ValueError, match="No molecules"):
            self.node.execute({"molecules": []})

    def test_empty_molecules_list_raises(self):
        self.node.set_property("smarts", "c1ccccc1")
        with pytest.raises(ValueError):
            self.node.execute({})

    def test_empty_smarts_raises(self):
        self.node.set_property("smarts", "")
        mols = _mols("c1ccccc1")
        with pytest.raises(ValueError, match="SMARTS"):
            self.node.execute({"molecules": mols})

    def test_invalid_smarts_raises(self):
        self.node.set_property("smarts", "not_a_smarts!!!@@##")
        mols = _mols("c1ccccc1")
        with pytest.raises(ValueError, match="Invalid"):
            self.node.execute({"molecules": mols})

    def test_validate_valid_smarts(self):
        self.node.set_property("smarts", "c1ccccc1")
        ok, msg = self.node.validate()
        assert ok is True

    def test_validate_empty_smarts_fails(self):
        self.node.set_property("smarts", "")
        ok, msg = self.node.validate()
        assert ok is False
        assert "empty" in msg.lower() or "smarts" in msg.lower()

    def test_validate_invalid_smarts_fails(self):
        self.node.set_property("smarts", "$$$$invalid")
        ok, msg = self.node.validate()
        assert ok is False

    def test_single_molecule_match(self):
        self.node.set_property("smarts", "c1ccccc1")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        assert len(result["matched"]) == 1
        assert len(result["unmatched"]) == 0

    def test_single_molecule_no_match(self):
        self.node.set_property("smarts", "[Fe]")
        mols = _mols("c1ccccc1")
        result = self.node.execute({"molecules": mols})
        assert len(result["matched"]) == 0
        assert len(result["unmatched"]) == 1

    def test_nitrogen_filter(self):
        self.node.set_property("smarts", "[#7]")
        mols = _mols("c1ccncc1", "CCO", "CC(N)C")
        result = self.node.execute({"molecules": mols})
        # pyridine and isopropylamine have nitrogen
        assert len(result["matched"]) == 2
