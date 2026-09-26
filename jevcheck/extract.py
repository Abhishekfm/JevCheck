"""Turn a CSV, Excel, PDF, PNG/JPEG file (or a DataFrame) into tables and text."""

from pathlib import Path

import pandas as pd


class ExtractionError(Exception):
    pass


def extract(source: str | Path | pd.DataFrame) -> tuple[list[pd.DataFrame], str]:
    if isinstance(source, pd.DataFrame):
        return [source], ""

    path = Path(source)
    if not path.is_file():
        raise ExtractionError(f"file not found: {path}")
    if path.stat().st_size == 0:
        raise ExtractionError("file is empty")

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            return [pd.read_csv(path, dtype=str, encoding_errors="replace")], ""
        if suffix in (".xlsx", ".xls"):
            return list(pd.read_excel(path, sheet_name=None, dtype=str).values()), ""
        if suffix == ".pdf":
            return _pdf(path)
        if suffix in (".png", ".jpg", ".jpeg"):
            return _image(path)
    except Exception as exc:
        raise ExtractionError(f"could not read {suffix} file: {exc}") from exc
    raise ExtractionError(f"unsupported file type: {suffix}")


def _pdf(path: Path) -> tuple[list[pd.DataFrame], str]:
    import pdfplumber

    tables, texts = [], []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            found = page.find_tables()
            for table in found:
                rows = table.extract()
                if rows:
                    tables.append(pd.DataFrame(rows[1:], columns=rows[0]))
            boxes = [t.bbox for t in found]

            # Page text excludes table regions so the same cells are not sent twice.
            def outside(obj, boxes=boxes):
                return obj.get("object_type") != "char" or not any(
                    x0 <= obj["x0"] and obj["x1"] <= x1 and top <= obj["top"] and obj["bottom"] <= bottom
                    for x0, top, x1, bottom in boxes
                )

            texts.append(page.filter(outside).extract_text() or "")
    return tables, "\n".join(texts).strip()


def _image(path: Path) -> tuple[list[pd.DataFrame], str]:
    import pytesseract
    from PIL import Image

    with Image.open(path) as img:
        return [], pytesseract.image_to_string(img).strip()
