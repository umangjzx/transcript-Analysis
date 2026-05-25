"""
Pydantic schemas for Audio Safety Analysis API.

These schemas define request/response models for FastAPI endpoints
with proper validation and documentation.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ChatRequest(BaseModel):
    """Request schema for chatbot endpoint."""
    
    report_id: int = Field(..., description="ID of the analysis report", gt=0)
    question: str = Field(..., description="Question to ask about the report", min_length=1)
    
    class Config:
        schema_extra = {
            "example": {
                "report_id": 1,
                "question": "What are the main concerns in this conversation?"
            }
        }


class AnalysisConfigRequest(BaseModel):
    """Optional configuration for analysis."""
    
    min_confidence: float = Field(
        default=0.3,
        description="Minimum confidence threshold for detections",
        ge=0.0,
        le=1.0
    )
    enable_llm_summary: bool = Field(
        default=True,
        description="Enable LLM-based summary generation"
    )
    speaker_aware: bool = Field(
        default=True,
        description="Enable speaker-aware analysis"
    )


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class CategoryDetail(BaseModel):
    """Details for a specific category detection."""
    
    category: str
    confidence: float
    pattern_strength: Optional[float] = None
    matched_text: Optional[str] = None
    severity: Optional[str] = None
    timestamp: Optional[float] = None


class Finding(BaseModel):
    """Individual finding from grooming detection."""
    
    category: Optional[str] = None
    categories: Optional[List[str]] = None
    confidence: float
    evidence: str
    matched_text: Optional[str] = None
    severity: str
    weight: Optional[float] = None
    timestamp: Optional[float] = None
    speaker: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None
    scoring: Optional[Dict[str, Any]] = None
    category_details: Optional[List[CategoryDetail]] = None


class DetectionSummary(BaseModel):
    """Summary of detection results."""
    
    total_findings: int
    category_distribution: Dict[str, int]
    severity_distribution: Dict[str, int]
    confidence_stats: Dict[str, float]
    risk_level: str
    high_confidence_findings: int
    critical_severity_findings: int


class DetectionResults(BaseModel):
    """Complete detection results."""
    
    findings: List[Finding]
    grouped_findings: List[Finding]
    summary: DetectionSummary
    metadata: Dict[str, Any]


class RiskBreakdown(BaseModel):
    """Risk score breakdown by category."""
    
    category: str
    weight: float
    occurrence_count: int
    total_score: float
    occurrences: List[Dict[str, Any]]


class RiskScore(BaseModel):
    """Risk scoring results."""
    
    score: float = Field(..., description="Risk score (0-100)")
    level: str = Field(..., description="Risk level classification")
    breakdown: Dict[str, RiskBreakdown]
    category_counts: Dict[str, int]
    total_findings: int
    raw_score: Optional[float] = None


class Evidence(BaseModel):
    """Evidence item."""
    
    category: str
    categories: Optional[List[str]] = None
    evidence: str
    confidence: float
    severity: str
    timestamp: Optional[float] = None
    # Rich detail fields passed through from the detector
    speaker: Optional[str] = None
    context_type: Optional[str] = None
    base_confidence: Optional[float] = None
    context_multiplier: Optional[float] = None
    is_joke: Optional[bool] = None
    is_negation: Optional[bool] = None


class Statistics(BaseModel):
    """Analysis statistics."""
    
    word_count: Optional[int] = None
    character_count: Optional[int] = None
    finding_count: Optional[int] = None
    unique_categories: Optional[int] = None
    categories: Optional[Dict[str, int]] = None
    category_breakdown: Optional[Dict[str, int]] = None  # alias
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    # Legacy fields
    total_words: Optional[int] = None
    total_sentences: Optional[int] = None
    total_findings: Optional[int] = None
    category_distribution: Optional[Dict[str, int]] = None
    severity_distribution: Optional[Dict[str, int]] = None
    average_confidence: Optional[float] = None

    class Config:
        extra = "allow"  # allow any extra fields from the stats module


class Summaries(BaseModel):
    """Analysis summaries."""
    
    rule_based: str = Field(..., description="Rule-based summary")
    llm_based: Optional[str] = Field(None, description="LLM-generated summary")


class AnalysisMetadata(BaseModel):
    """Metadata about the analysis."""
    
    analyzed_at: str
    min_confidence_threshold: float
    total_findings: int
    high_confidence_findings: int


class TimelineEntry(BaseModel):
    """Timeline entry from transcription."""
    
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Complete analysis response."""
    
    id: int = Field(..., description="Analysis record ID")
    filename: str = Field(..., description="Original audio filename")
    transcript: str = Field(..., description="Full transcript")
    timeline: List[TimelineEntry] = Field(..., description="Timestamped transcript")
    detection: DetectionResults = Field(..., description="Grooming detection results")
    evidence: List[Evidence] = Field(..., description="Extracted evidence")
    risk: RiskScore = Field(..., description="Risk scoring results")
    severity: str = Field(..., description="Overall severity classification")
    stats: Statistics = Field(..., description="Analysis statistics")
    summaries: Summaries = Field(..., description="Analysis summaries")
    pdf_report: str = Field(..., description="Path to PDF report")
    analysis_metadata: AnalysisMetadata = Field(..., description="Analysis metadata")
    
    class Config:
        schema_extra = {
            "example": {
                "id": 1,
                "filename": "conversation.mp3",
                "transcript": "Full conversation transcript...",
                "timeline": [
                    {"start": 0.0, "end": 2.5, "text": "Hello", "speaker": "Speaker 1"}
                ],
                "detection": {
                    "findings": [],
                    "grouped_findings": [],
                    "summary": {
                        "total_findings": 5,
                        "category_distribution": {"secrecy": 2, "manipulation": 3},
                        "severity_distribution": {"high": 3, "critical": 2},
                        "confidence_stats": {"average": 0.85, "maximum": 0.95, "minimum": 0.70},
                        "risk_level": "high",
                        "high_confidence_findings": 4,
                        "critical_severity_findings": 2
                    },
                    "metadata": {}
                },
                "evidence": [],
                "risk": {
                    "score": 67.5,
                    "level": "High",
                    "breakdown": {},
                    "category_counts": {},
                    "total_findings": 5
                },
                "severity": "High",
                "stats": {},
                "summaries": {
                    "rule_based": "Analysis summary...",
                    "llm_based": "Detailed LLM summary..."
                },
                "pdf_report": "reports/report_1.pdf",
                "analysis_metadata": {
                    "analyzed_at": "2026-05-22T12:00:00",
                    "min_confidence_threshold": 0.3,
                    "total_findings": 5,
                    "high_confidence_findings": 4
                }
            }
        }


class HistoryItem(BaseModel):
    """History list item."""

    id: int
    filename: str
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    # created_at is the canonical field; analyzed_at is kept for schema compat
    created_at: Optional[str] = None
    analyzed_at: Optional[str] = None  # alias — populated from created_at if present


class HistoryResponse(BaseModel):
    """History list response."""
    
    reports: List[HistoryItem]
    total: int


class ReportResponse(BaseModel):
    """Single report response."""

    id: int
    filename: str
    transcript: Optional[str] = None
    findings: List[Any] = []
    evidence: List[Any] = []
    stats: Optional[Any] = None
    summary: Optional[str] = None
    llm_summary: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[float] = None
    pdf_path: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        extra = "allow"  # forward-compat with any extra fields


class EvidenceResponse(BaseModel):
    """Evidence response."""
    
    report_id: int
    severity: str
    risk_score: float
    evidence: List[Evidence]


class ChatResponse(BaseModel):
    """Chatbot response."""
    
    answer: str
    sources: Optional[List[str]] = None
    confidence: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str
    service: str
    version: str
    timestamp: str


class ErrorResponse(BaseModel):
    """Error response."""
    
    error: str
    detail: str
    timestamp: str
    
    class Config:
        schema_extra = {
            "example": {
                "error": "AnalysisError",
                "detail": "Transcription failed: Unsupported audio format",
                "timestamp": "2026-05-22T12:00:00"
            }
        }
