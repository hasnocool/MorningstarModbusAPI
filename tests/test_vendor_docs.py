# tests/test_vendor_docs.py
import json
from pathlib import Path
from urllib.parse import urlparse

CATALOG = Path(__file__).resolve().parents[1] / "docs" / "vendor" / "morningstar" / "sources.json"


def test_morningstar_source_catalog_is_well_formed() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    sources = payload["sources"]

    ids = [source["id"] for source in sources]
    assert len(ids) == len(set(ids))

    filenames = [source["filename"] for source in sources if source.get("download", True)]
    assert len(filenames) == len(set(filenames))

    for source in sources:
        parsed = urlparse(source["url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in {"morningstarcorp.com", "www.morningstarcorp.com"}
        assert source["title"]
        assert source["relevance"]
        if source.get("download", True):
            assert source["filename"].endswith(".pdf")
