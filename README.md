# JevCheck

Extract a CSV, Excel, PDF or PNG/JPEG file and let TypeSafe Jev decide whether it is valid:
no PII, no sexually explicit content, well-formed, and of acceptable quality.

## Setup

```sh
uv venv && uv pip install -e ".[dev]"
sudo apt install tesseract-ocr     # only needed for PNG/JPEG
export TYPESAFE_API_KEY=...
```

## Usage

```sh
python -m jevcheck orders.csv      # prints the report; exit code 0 = valid, 1 = invalid
python -m pytest                   # tests use a fake client, no key needed
```

```python
from jevcheck import check

report = check("orders.pdf")
report.is_valid   # bool
report.errors     # e.g. ["contains_pii: p=0.94"]
report.answers    # raw typed Jev answers per request
```

The questions and thresholds live in `jevcheck/check.py`. Large files are split into
requests of at most about 60k tokens.
