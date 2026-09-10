import pathlib
import pytest

PDF_DIR = pathlib.Path(__file__).parent.parent / "pdfs"

# stem -> record type. Phase 1 scope only.
RECORD_PDFS = {
    "cloverdale": "cemetery", "eastcambridge": "cemetery", "gates": "cemetery",
    "hopkins": "cemetery", "jeffersonville": "cemetery", "mtview": "cemetery",
    "northcambridge": "cemetery", "plainsroad": "cemetery", "riverroad": "cemetery",
    "smilie": "cemetery", "southcambridge": "cemetery",
    "birth_records": "birth",
    "marriage_records2": "marriage",
    "death_records": "death",
    "warningsout_records": "warning",
    "freemansworn_records": "freeman",
}


@pytest.fixture(scope="session")
def pdf_dir():
    return PDF_DIR
