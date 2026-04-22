"""
Tests for core/port_types.py

Covers type normalisation, compatibility rules, and the
compatibility_message helper — all pure functions with no Qt dependency.
"""

import pytest
from core.port_types import normalize_type, is_compatible, compatibility_message


class TestNormalizeType:
    def test_none_returns_any(self):
        assert normalize_type(None) == "any"

    def test_empty_string_returns_any(self):
        assert normalize_type("") == "any"

    def test_canonical_types_pass_through(self):
        for t in ("any", "file", "string", "data", "list", "molecules", "bytes", "image", "model"):
            assert normalize_type(t) == t

    def test_lowercase_conversion(self):
        assert normalize_type("FILE") == "file"
        assert normalize_type("Data") == "data"

    def test_synonym_molecule(self):
        assert normalize_type("molecule") == "molecules"

    def test_synonym_mol(self):
        assert normalize_type("mol") == "molecules"

    def test_synonym_sdf(self):
        assert normalize_type("sdf") == "file"

    def test_synonym_pdb(self):
        assert normalize_type("pdb") == "file"

    def test_synonym_pdbqt(self):
        assert normalize_type("pdbqt") == "file"

    def test_synonym_xyz(self):
        assert normalize_type("xyz") == "file"

    def test_synonym_csv(self):
        assert normalize_type("csv") == "file"

    def test_synonym_json(self):
        assert normalize_type("json") == "data"

    def test_synonym_txt(self):
        assert normalize_type("txt") == "file"

    def test_synonym_files(self):
        assert normalize_type("files") == "list"

    def test_synonym_docking_results(self):
        assert normalize_type("docking_results") == "data"

    def test_synonym_report(self):
        assert normalize_type("report") == "string"

    def test_synonym_plot(self):
        assert normalize_type("plot") == "image"

    def test_unknown_type_kept_as_is(self):
        assert normalize_type("myweirdtype") == "myweirdtype"

    def test_whitespace_stripped(self):
        assert normalize_type("  file  ") == "file"


class TestIsCompatible:
    def test_same_type_compatible(self):
        assert is_compatible("file", "file") is True

    def test_any_output_compatible_with_anything(self):
        assert is_compatible("any", "file") is True
        assert is_compatible("any", "data") is True
        assert is_compatible("any", "molecules") is True

    def test_anything_compatible_with_any_input(self):
        assert is_compatible("file", "any") is True
        assert is_compatible("data", "any") is True

    def test_both_any_compatible(self):
        assert is_compatible("any", "any") is True

    def test_different_types_incompatible(self):
        assert is_compatible("file", "data") is False
        assert is_compatible("molecules", "string") is False
        assert is_compatible("image", "model") is False

    def test_synonyms_resolved_before_check(self):
        # "mol" normalises to "molecules", so should match
        assert is_compatible("mol", "molecules") is True
        # "csv" normalises to "file"
        assert is_compatible("csv", "file") is True

    def test_unknown_type_requires_exact_match(self):
        assert is_compatible("mytype", "mytype") is True
        assert is_compatible("mytype", "othertype") is False


class TestCompatibilityMessage:
    def test_compatible_returns_empty_string(self):
        assert compatibility_message("file", "file") == ""
        assert compatibility_message("any", "data") == ""

    def test_incompatible_returns_nonempty_message(self):
        msg = compatibility_message("file", "data")
        assert msg != ""
        assert "file" in msg
        assert "data" in msg

    def test_message_contains_mismatch_info(self):
        msg = compatibility_message("molecules", "string")
        assert "molecules" in msg
        assert "string" in msg
