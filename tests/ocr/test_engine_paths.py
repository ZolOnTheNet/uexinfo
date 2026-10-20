"""Recherche de Tesseract : la copie stable extprg/tesseract passe avant celle de SC-Datarunner,
dont la v0.12 a supprimé Tesseract (ce qui cassait l'OCR de uexinfo)."""
from uexinfo.ocr.engine import _DATA_CANDIDATES, _EXE_CANDIDATES, _first_existing, _has_model


def test_own_copy_listed_first():
    assert _EXE_CANDIDATES[0].parts[-3:] == ("tesseract", "Tesseract-OCR", "tesseract.exe")
    assert _DATA_CANDIDATES[0].parts[-2:] == ("tesseract", "data")


def test_first_existing_prefers_order(tmp_path):
    own, dr = tmp_path / "own.exe", tmp_path / "dr.exe"
    dr.write_text("x")
    assert _first_existing((own, dr)) == dr          # copie stable absente : repli sur SC-Datarunner
    own.write_text("x")
    assert _first_existing((own, dr)) == own
    assert _first_existing((tmp_path / "a", tmp_path / "b")) is None


def test_data_dir_needs_model(tmp_path):
    empty, full = tmp_path / "empty", tmp_path / "full"
    empty.mkdir()
    full.mkdir()
    (full / "eng_sc.traineddata").write_bytes(b"")
    # Un dossier data/ sans modèle (cas de SC-Datarunner v0.12) ne doit pas être retenu.
    assert _first_existing((empty, full), _has_model) == full
