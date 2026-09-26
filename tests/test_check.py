import pandas as pd
from typesafe_sdk import SystemOneResponse

from jevcheck.check import CHUNK_CHARS, build_states, check
from jevcheck.extract import extract


class FakeClient:
    """Stands in for TypeSafeClient; returns real SDK response objects."""

    def __init__(self, pii=0.02, sexual=0.01, well_formed=0.95, content="business_data", quality=2.7):
        self.calls = []
        self.answers = {
            "contains_pii": {"type": "noul", "noul": pii},
            "contains_sexual_content": {"type": "noul", "noul": sexual},
            "is_well_formed": {"type": "noul", "noul": well_formed},
            "content_type": {"type": "choice", "choice": content, "confidence": 0.9, "probabilities": {content: 0.9}},
            "data_quality": {"type": "score", "score": quality, "confidence": 0.8, "legend": {}, "probabilities": {}},
        }

    def system_one(self, state, questions):
        self.calls.append(state)
        return SystemOneResponse.model_validate(
            {"model": "jev-test", "usage": {"input_tokens": 1, "output_tokens": 0}, "answers": self.answers}
        )


ORDERS = pd.DataFrame({"sku": ["A-100", "B-200"], "qty": ["5", "2"]})


def test_clean_file_passes(tmp_path):
    path = tmp_path / "orders.csv"
    ORDERS.to_csv(path, index=False)
    client = FakeClient()
    report = check(path, client=client)
    assert report.is_valid and report.errors == []
    assert client.calls[0]["file_name"] == "orders.csv"
    assert client.calls[0]["csv"].startswith("sku,qty")


def test_every_failing_answer_is_reported():
    report = check(ORDERS, client=FakeClient(pii=0.9, sexual=0.8, well_formed=0.1, content="garbled_or_empty", quality=0.4))
    assert not report.is_valid
    assert [e.split(":")[0] for e in report.errors] == [
        "contains_pii",
        "contains_sexual_content",
        "not_well_formed",
        "content_type",
        "data_quality",
    ]


def test_large_table_is_chunked_under_budget():
    big = pd.DataFrame({"text": ["lorem ipsum dolor sit amet " * 20] * 3000})
    states = build_states("big.csv", [big], "")
    assert len(states) > 1
    assert all(len(s["csv"]) <= CHUNK_CHARS + 1000 for s in states)
    assert all(s["csv"].startswith("text\n") for s in states)
    assert sum(s["csv"].count("\n") for s in states) == 3000


def test_api_errors_do_not_crash():
    class Broken:
        def system_one(self, state, questions):
            raise TimeoutError("upstream timed out")

    report = check(ORDERS, client=Broken())
    assert not report.is_valid and "TimeoutError" in report.errors[0]


def test_bad_files_do_not_crash(tmp_path):
    (tmp_path / "empty.csv").write_bytes(b"")
    (tmp_path / "bad.pdf").write_bytes(b"%PDF-1.7 not really")
    (tmp_path / "notes.docx").write_text("x")
    for name in ["empty.csv", "bad.pdf", "notes.docx", "missing.csv"]:
        report = check(tmp_path / name, client=FakeClient())
        assert not report.is_valid and report.errors[0].startswith("extraction:")


def test_pdf_tables_and_text(tmp_path):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(text="Purchase order 1042", new_x="LMARGIN", new_y="NEXT")
    with pdf.table() as table:
        for row in [["sku", "qty"], ["A-100", "5"]]:
            cells = table.row()
            for value in row:
                cells.cell(value)
    path = tmp_path / "po.pdf"
    pdf.output(str(path))

    tables, text = extract(path)
    assert list(tables[0].columns) == ["sku", "qty"]
    assert text == "Purchase order 1042"
