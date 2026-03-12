"""Abstract OCR provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    import PIL.Image

ImageInput = Union[str, bytes, "PIL.Image.Image"]


@dataclass
class OCRResult:
    """Output of an OCR extraction."""

    text: str
    confidence: Optional[float] = None  # 0..1 if available
    source_location: Optional[str] = None  # page number or image id
    extraction_method: str = "ocr"


class OCRProvider(ABC):
    """Abstract interface for OCR providers.

    OCR output must never overwrite native text—only complement it.
    """

    @abstractmethod
    def extract_text(
        self,
        image: ImageInput,
        source_location: Optional[str] = None,
    ) -> OCRResult:
        """Extract text from an image.

        Args:
            image: Path, bytes, or PIL Image.
            source_location: Optional page number or image identifier.

        Returns:
            OCRResult with extracted text, optional confidence, and metadata.
        """
        raise NotImplementedError
