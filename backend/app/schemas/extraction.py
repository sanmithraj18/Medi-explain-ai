"""
MediExplain AI — Pydantic Schemas for Document Vision & Laboratory Parameter Extraction.
Enforces strict structural validation of Gemini vision extracted parameters.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class VisionParameterItem(BaseModel):
    parameter_name: str = Field(description="Exact laboratory test or analyte name as printed")
    observed_value: str = Field(description="Measured value as printed on the document")
    unit: Optional[str] = Field(default=None, description="Reported unit of measure, or null if omitted")
    reference_range: Optional[str] = Field(default=None, description="Exact laboratory reference range string as printed")
    reference_min: Optional[float] = Field(default=None, description="Parsed numerical lower reference bound if applicable")
    reference_max: Optional[float] = Field(default=None, description="Parsed numerical upper reference bound if applicable")
    laboratory_flag: Optional[str] = Field(default=None, description="Laboratory-printed flag (HIGH, LOW, NORMAL, CRITICAL, H, L, etc.)")
    extraction_confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Confidence in transcription accuracy")
    needs_user_review: bool = Field(default=False, description="Flag indicating value is ambiguous, blurry, or partially obscured")


class VisionExtractionResponse(BaseModel):
    report_type: Optional[str] = Field(default=None, description="Laboratory report title or panel type")
    report_date: Optional[str] = Field(default=None, description="Date of report or specimen collection if clearly visible")
    raw_text: Optional[str] = Field(default=None, description="Summary transcription of visible document text")
    parameters: List[VisionParameterItem] = Field(default_factory=list, description="List of faithfully extracted laboratory parameters")
    extraction_notes: Optional[str] = Field(default=None, description="Observations regarding document legibility or quality")

