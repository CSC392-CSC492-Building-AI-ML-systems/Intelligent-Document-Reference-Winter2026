"""Document data model."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Document:
    id: str
    content: str
    source: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
    chunks: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.content.split())
