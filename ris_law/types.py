from dataclasses import dataclass
from typing import Optional

@dataclass
class LawItem:
    law: str
    gesetzesnummer: str
    paragraph_id: Optional[str]
    heading: Optional[str]
    text: str
    url: str
    source: str
    document_number: Optional[str]
    retrieved_at: str
