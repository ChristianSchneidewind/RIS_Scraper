from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class TocRecord:
    law: str
    application: str
    gesetzesnummer: str
    source: str
    license: str
    retrieved_at: str
    document_number: Optional[str]
    url: str
    heading: Optional[str]
    paragraph_id: Optional[str]
    text: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FullRecord:
    gesetzesnummer: str
    law: str
    unit_type: str
    unit: str
    unit_number: str
    date_in_force: Optional[str]
    date_out_of_force: Optional[str]
    license: Optional[str]
    status: str
    text: Optional[str]
    heading: Optional[str]
    nor: Optional[str]
    url: str

    def to_dict(self) -> dict:
        return asdict(self)
