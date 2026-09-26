"""Validate a file with TypeSafe Jev: extract it, ask typed questions, apply thresholds."""

import json
from pathlib import Path

import pandas as pd
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from jevcheck.extract import ExtractionError, extract

MAX_TOKENS = 60_000  # headroom under the 64k limit; estimated as characters / 4
CHUNK_CHARS = (MAX_TOKENS - 2_000) * 4  # reserve room for the questions

QUESTIONS = {
    "contains_pii": Noul(
        instructions="Does this data contain personal identifiable information such as emails, phone numbers, "
        "government ID numbers (Aadhaar, PAN, SSN), payment card numbers, or home addresses?"
    ),
    "contains_sexual_content": Noul(instructions="Does this content contain pornographic or sexually explicit material?"),
    "is_well_formed": Noul(instructions="Is this a coherent, readable table or document rather than garbled extraction output?"),
    "content_type": Choice(
        instructions="What kind of content is this?",
        criteria={"business_data": None, "report_text": None, "garbled_or_empty": None, "other": None},
    ),
    "data_quality": Score(
        instructions="How clean and complete is this data?",
        criteria=["unusable", "poor", "acceptable", "clean"],
    ),
}


class Report(BaseModel):
    is_valid: bool
    errors: list[str]
    answers: list[dict] = []


def build_states(name: str, tables: list[pd.DataFrame], text: str) -> list[dict]:
    """Split content into states under CHUNK_CHARS; table chunks repeat their header row."""
    pieces = []
    for i, table in enumerate(tables):
        header, *rows = table.to_csv(index=False).splitlines()
        chunk: list[str] = []
        for row in rows:
            if chunk and sum(map(len, chunk)) + len(row) > CHUNK_CHARS:
                pieces.append({"table": i, "csv": "\n".join([header, *chunk])})
                chunk = []
            chunk.append(row)
        pieces.append({"table": i, "csv": "\n".join([header, *chunk])})
    for start in range(0, len(text), CHUNK_CHARS):
        pieces.append({"text": text[start : start + CHUNK_CHARS]})
    return [{"file_name": name, **piece} for piece in pieces]


def check(source: str | Path | pd.DataFrame, client: TypeSafeClient | None = None) -> Report:
    try:
        tables, text = extract(source)
    except ExtractionError as exc:
        return Report(is_valid=False, errors=[f"extraction: {exc}"])

    name = "dataframe" if isinstance(source, pd.DataFrame) else Path(source).name
    states = build_states(name, [t for t in tables if not t.empty], text)
    if not states:
        return Report(is_valid=False, errors=["extraction: no tables or text found"])

    try:
        client = client or TypeSafeClient()
        responses = [client.system_one(state=state, questions=QUESTIONS) for state in states]
    except Exception as exc:
        return Report(is_valid=False, errors=[f"jev: {type(exc).__name__}: {exc}"])

    errors = []
    for i, r in enumerate(responses):
        where = f" (chunk {i + 1} of {len(responses)})" if len(responses) > 1 else ""
        if (p := r.nouls["contains_pii"].noul) >= 0.5:
            errors.append(f"contains_pii: p={p:.2f}{where}")
        if (p := r.nouls["contains_sexual_content"].noul) >= 0.5:
            errors.append(f"contains_sexual_content: p={p:.2f}{where}")
        if (p := r.nouls["is_well_formed"].noul) < 0.5:
            errors.append(f"not_well_formed: p={p:.2f}{where}")
        if (c := r.choices["content_type"].choice) == "garbled_or_empty":
            errors.append(f"content_type: {c}{where}")
        if (s := r.scores["data_quality"].score) < 1.5:
            errors.append(f"data_quality: {s:.2f} of 3{where}")

    answers = [json.loads(r.model_dump_json(include={"model", "answers"})) for r in responses]
    return Report(is_valid=not errors, errors=errors, answers=answers)
