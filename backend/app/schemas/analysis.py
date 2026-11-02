"""
MediExplain AI — Pydantic Schemas for AI Analysis & Medical Explanations.
Enforces strict structural validation of all Gemini model outputs.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class OverallSummarySchema(BaseModel):
    report_type: str = Field(default="Laboratory Test Report", description="Type of lab report identified")
    overall_assessment: str = Field(description="2-3 sentence educational overview of findings")
    parameters_within_range: List[str] = Field(default_factory=list, description="Parameters within normal interval")
    parameters_outside_range: List[str] = Field(default_factory=list, description="Parameters outside reference interval")
    parameters_unclassified: List[str] = Field(default_factory=list, description="Parameters where reference range was unavailable or not reported")
    potentially_critical_flags: List[str] = Field(default_factory=list, description="Parameters warranting prompt medical review")
    missing_information: List[str] = Field(default_factory=list, description="Information missing from lab report")
    key_limitations: List[str] = Field(default_factory=list, description="Clinical context limitations")
    disclaimer: str = Field(
        default="This explanation is for educational purposes only and does not constitute medical advice. Please discuss these results with your healthcare provider."
    )
    doctor_discussion_questions: List[str] = Field(default_factory=list, description="Informed discussion questions for physician")


class ParameterExplanationSchema(BaseModel):
    parameter_name: str
    observed_value: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    classification: str = Field(
        default="UNKNOWN",
        description="Classification: WITHIN_RANGE, BELOW_RANGE, ABOVE_RANGE, CRITICAL, INCOMPLETE_ASSESSMENT, PEDIATRIC_INTERPRETATION_REQUIRED, RANGE_UNAVAILABLE, NOT_CLASSIFIED, UNKNOWN"
    )
    what_it_measures: str = Field(description="Educational explanation of biological role")
    simple_explanation: str = Field(description="Plain-language educational explanation without diagnosing")
    contextual_limitations: str = Field(default="Results must be interpreted in clinical context by a physician.")
    when_to_seek_attention: str = Field(default="Discuss findings with your doctor at your next appointment.")
    doctor_questions: List[str] = Field(default_factory=list)
    is_contextual_threshold: bool = Field(
        default=False,
        description="True if classification used a clinical contextual benchmark rather than lab printed range"
    )
    clinical_source: Optional[str] = Field(
        default=None,
        description="Configured clinical guideline source if a contextual benchmark was used"
    )
    contextual_notes: Optional[str] = Field(
        default=None,
        description="Important clinical contextual notes or safety boundaries"
    )
    disclaimer: str = Field(
        default="This explanation is for informational purposes only. Please discuss this result with your healthcare provider."
    )


class AnalysisTriggerResponse(BaseModel):
    analysis_id: Optional[str]
    report_id: str
    parameters_analyzed: int
    unconfirmed_parameters_skipped: int
    questions_generated: int
    message: str
    disclaimer: str

