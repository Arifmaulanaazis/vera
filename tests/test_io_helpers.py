"""
Tests for helper functions in nodes/io_nodes.py

Covers: _as_path_list, _validate_xyz_format, _parse_xyz_molecule,
_create_xyz_content. All are pure functions with no Qt dependency.
"""

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# _as_path_list
# ---------------------------------------------------------------------------

class TestAsPathList:
    @pytest.fixture(autouse=True)
    def _import(self):
        from nodes.io import _as_path_list
        self._fn = _as_path_list

    def test_none_returns_empty(self):
        assert self._fn(None) == []

    def test_empty_string_returns_empty(self):
        assert self._fn("") == []

    def test_empty_list_returns_empty(self):
        assert self._fn([]) == []

    def test_nonexistent_path_filtered_out(self):
        result = self._fn("/nonexistent/path/does_not_exist.pdb")
        assert result == []

    def test_existing_file_path(self):
        with tempfile.NamedTemporaryFile(suffix=".pdb", delete=False) as f:
            f.write(b"test")
            tmp = f.name
        try:
            result = self._fn(tmp)
            assert tmp in result
        finally:
            os.unlink(tmp)

    def test_semicolon_separated_string(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f2:
            p1, p2 = f1.name, f2.name
        try:
            result = self._fn(f"{p1};{p2}")
            assert p1 in result
            assert p2 in result
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_comma_separated_string(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f2:
            p1, p2 = f1.name, f2.name
        try:
            result = self._fn(f"{p1},{p2}")
            assert p1 in result
            assert p2 in result
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_newline_separated_string(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f2:
            p1, p2 = f1.name, f2.name
        try:
            result = self._fn(f"{p1}\n{p2}")
            assert p1 in result
            assert p2 in result
        finally:
            os.unlink(p1)
            os.unlink(p2)

    def test_list_input_existing_files(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp = f.name
        try:
            result = self._fn([tmp])
            assert tmp in result
        finally:
            os.unlink(tmp)

    def test_duplicate_paths_deduplicated(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp = f.name
        try:
            result = self._fn(f"{tmp};{tmp};{tmp}")
            assert result.count(tmp) == 1
        finally:
            os.unlink(tmp)

    def test_list_with_nonexistent_filtered(self):
        result = self._fn(["/ghost/does_not_exist.mol"])
        assert result == []

    def test_path_object_accepted(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp = f.name
        try:
            result = self._fn(Path(tmp))
            assert tmp in result
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# _validate_xyz_format
# ---------------------------------------------------------------------------

class TestValidateXyzFormat:
    @pytest.fixture(autouse=True)
    def _import(self):
        from nodes.io import _validate_xyz_format
        self._fn = _validate_xyz_format

    def _valid_xyz_lines(self):
        return [
            "3",
            "Water molecule",
            "O  0.000000  0.000000  0.117176",
            "H  0.000000  0.757200 -0.468704",
            "H  0.000000 -0.757200 -0.468704",
        ]

    def test_valid_xyz_returns_true(self):
        ok, msg = self._fn(self._valid_xyz_lines())
        assert ok is True

    def test_empty_lines_returns_false(self):
        ok, msg = self._fn([])
        assert ok is False

    def test_invalid_atom_count_returns_false(self):
        ok, msg = self._fn(["not_a_number", "comment", "C 0 0 0"])
        assert ok is False

    def test_zero_atom_count_returns_false(self):
        ok, msg = self._fn(["0", "comment"])
        assert ok is False

    def test_not_enough_lines_returns_false(self):
        # atom count says 3, but only one coordinate line
        ok, msg = self._fn(["3", "comment", "C 0.0 0.0 0.0"])
        assert ok is False

    def test_missing_coordinates_returns_false(self):
        # Valid header but a coordinate line only has element (too short)
        ok, msg = self._fn(["2", "comment", "C", "H 1.0 0.0 0.0"])
        assert ok is False

    def test_invalid_coordinates_returns_false(self):
        ok, msg = self._fn([
            "1",
            "comment",
            "C  notanum  0.0  0.0",
        ])
        assert ok is False

    def test_valid_message_not_empty(self):
        _, msg = self._fn(self._valid_xyz_lines())
        assert isinstance(msg, str)

    def test_single_atom_valid(self):
        ok, _ = self._fn(["1", "Helium", "He 0.0 0.0 0.0"])
        assert ok is True

    def test_negative_coordinates_valid(self):
        ok, _ = self._fn(["1", "", "C -1.2 -3.4 5.6"])
        assert ok is True

    def test_error_message_on_failure_is_string(self):
        ok, msg = self._fn([])
        assert ok is False
        assert isinstance(msg, str) and len(msg) > 0


# ---------------------------------------------------------------------------
# _parse_xyz_molecule
# ---------------------------------------------------------------------------

class TestParseXyzMolecule:
    @pytest.fixture(autouse=True)
    def _import(self):
        pytest.importorskip("rdkit")
        from nodes.io import _parse_xyz_molecule
        self._fn = _parse_xyz_molecule

    def _water_lines(self):
        return [
            "3",
            "Water",
            "O  0.000000  0.000000  0.117176",
            "H  0.000000  0.757200 -0.468704",
            "H  0.000000 -0.757200 -0.468704",
        ]

    def test_water_molecule_parsed(self):
        mol = self._fn(self._water_lines())
        assert mol is not None

    def test_atom_count_correct(self):
        mol = self._fn(self._water_lines())
        assert mol.GetNumAtoms() == 3

    def test_has_conformer(self):
        mol = self._fn(self._water_lines())
        conf = mol.GetConformer()
        assert conf is not None

    def test_empty_lines_returns_none(self):
        mol = self._fn([])
        assert mol is None

    def test_single_atom(self):
        mol = self._fn(["1", "", "C 0.0 0.0 0.0"])
        assert mol is not None
        assert mol.GetNumAtoms() == 1

    def test_coordinates_stored_in_conformer(self):
        mol = self._fn(self._water_lines())
        conf = mol.GetConformer()
        pos = conf.GetAtomPosition(0)
        # Oxygen is approximately at (0, 0, 0.117)
        assert abs(pos.z - 0.117176) < 0.001


# ---------------------------------------------------------------------------
# _create_xyz_content
# ---------------------------------------------------------------------------

class TestCreateXyzContent:
    @pytest.fixture(autouse=True)
    def _import(self):
        pytest.importorskip("rdkit")
        from nodes.io import _create_xyz_content
        self._fn = _create_xyz_content

    def _ethanol_mol(self):
        from rdkit import Chem
        from rdkit.Chem import AllChem
        m = Chem.MolFromSmiles("CCO")
        m = Chem.AddHs(m)
        AllChem.EmbedMolecule(m, AllChem.ETKDGv3())
        return m

    def test_none_returns_empty_string(self):
        assert self._fn(None) == ""

    def test_returns_string(self):
        mol = self._ethanol_mol()
        content = self._fn(mol)
        assert isinstance(content, str)

    def test_first_line_is_atom_count(self):
        mol = self._ethanol_mol()
        content = self._fn(mol)
        lines = content.splitlines()
        # First line should be parseable as integer
        assert int(lines[0]) == mol.GetNumAtoms()

    def test_content_has_enough_lines(self):
        mol = self._ethanol_mol()
        content = self._fn(mol)
        lines = content.splitlines()
        atom_count = mol.GetNumAtoms()
        # At minimum: atom_count line + comment line + atom_count coordinate lines
        assert len(lines) >= 2 + atom_count

    def test_custom_name_in_second_line(self):
        mol = self._ethanol_mol()
        content = self._fn(mol, name="ethanol_test")
        lines = content.splitlines()
        assert "ethanol_test" in lines[1]
