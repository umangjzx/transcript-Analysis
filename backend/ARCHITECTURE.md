# Audio Safety Analyzer - Architecture Documentation

## Directory Structure

```
backend/
│
├── app.py                          # Legacy FastAPI application
├── app_v2.py                       # New FastAPI application (v2.0)
├── config.py                       # Configuration settings
├── requirements.txt                # Python dependencies
│
├── api/                            # API Routes Layer
│   └── audio_analysis_routes.py   # Audio analysis endpoints
│
├── services/                       # Business Logic Layer
│   └── audio_safety_service.py    # Main analysis service
│
├── schemas/                        # Pydantic Models
│   └── audio_analysis_schemas.py  # Request/Response schemas
│
├── modules/                        # Core Detection Modules
│   ├── patterns.py                # Regex pattern libraries
│   ├── context_analyzer.py        # Safe/risk context detection
│   ├── confidence.py              # Confidence scoring engine
│   ├── filters.py                 # Negation & joke filters
│   ├── evidence_grouping.py       # Evidence deduplication
│   ├── grooming_detector.py       # Main detection pipeline
│   ├── risk_scorer.py             # Weighted risk scoring
│   ├── severity_classifier.py     # Severity classification
│   ├── summarizer.py              # Rule-based summary
│   ├── llm_summarizer.py          # LLM-based summary
│   ├── report_generator.py        # PDF report generation
│   ├── transcriber.py             # Audio transcription
│   ├── evidence_extractor.py      # Evidence extraction
│   ├── stats.py                   # Statistics generation
│   ├── chatbot.py                 # RAG chatbot
│   ├── analyzer.py                # Legacy analyzer
│   ├── ml_classifier.py           # ML classification
│   └── video_processor.py         # Video processing
│
├── database/                       # Database Layer
│   ├── db.py                      # Database connection
│   └── models.py                  # SQLAlchemy models
│
├── uploads/                        # Uploaded audio files
├── reports/                        # Generated PDF reports
├── vectors/                        # Vector database (ChromaDB)
├── logs/                          # Application logs
└── examples/                      # Example files
```

## Architecture Layers

### 1. API Layer (`api/`)
- **Purpose**: Handle HTTP requests/responses
- **Responsibilities**:
  - Request validation
  - Response formatting
  - Error handling
  - Route definitions
- **Files**: `audio_analysis_routes.py`

### 2. Service Layer (`services/`)
- **Purpose**: Business logic orchestration
- **Responsibilities**:
  - Pipeline coordination
  - Component integration
  - Transaction management
  - Async execution
- **Files**: `audio_safety_service.py`

### 3. Schema Layer (`schemas/`)
- **Purpose**: Data validation and serialization
- **Responsibilities**:
  - Request validation
  - Response formatting
  - Type safety
  - API documentation
- **Files**: `audio_analysis_schemas.py`

### 4. Module Layer (`modules/`)
- **Purpose**: Core detection algorithms
- **Responsibilities**:
  - Pattern matching
  - Risk scoring
  - Context analysis
  - Report generation
- **Files**: Multiple specialized modules

### 5. Database Layer (`database/`)
- **Purpose**: Data persistence
- **Responsibilities**:
  - Database connection
  - ORM models
  - Query execution
- **Files**: `db.py`, `models.py`

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     AUDIO SAFETY ANALYZER                        │
└─────────────────────────────────────────────────────────────────┘

1. UPLOAD
   ↓
   [FastAPI Endpoint] → Validate file format
   ↓
   [Save to uploads/]

2. TRANSCRIPTION
   ↓
   [transcriber.py] → Whisper API
   ↓
   Output: transcript + timeline

3. GROOMING DETECTION
   ↓
   [grooming_detector.py]
   ├── [patterns.py] → Pattern matching
   ├── [context_analyzer.py] → Safe/risk context
   ├── [filters.py] → Negation & joke detection
   ├── [confidence.py] → Confidence scoring
   └── [evidence_grouping.py] → Deduplication
   ↓
   Output: findings + grouped_findings

4. EVIDENCE EXTRACTION
   ↓
   [evidence_extractor.py]
   ↓
   Output: evidence list

5. RISK SCORING
   ↓
   [risk_scorer.py]
   ├── Apply category weights
   ├── Apply diminishing returns
   └── Calculate 0-100 score
   ↓
   Output: risk_score + breakdown

6. SEVERITY CLASSIFICATION
   ↓
   [severity_classifier.py]
   ↓
   Output: Safe/Low/Moderate/High/Critical

7. STATISTICS
   ↓
   [stats.py]
   ↓
   Output: stats dictionary

8. SUMMARY GENERATION
   ↓
   [summarizer.py] → Rule-based summary
   [llm_summarizer.py] → LLM summary (optional)
   ↓
   Output: summaries

9. DATABASE PERSISTENCE
   ↓
   [database/models.py] → Save to SQLite
   ↓
   Output: record_id

10. VECTOR STORAGE (Optional)
    ↓
    [chatbot.py] → Store in ChromaDB
    ↓
    Output: vector embeddings

11. PDF REPORT
    ↓
    [report_generator.py] → Generate PDF
    ↓
    Output: pdf_path

12. RESPONSE
    ↓
    [schemas/] → Format response
    ↓
    Return to client
```

## Dependency Injection

### Service Factory Pattern

```python
# services/audio_safety_service.py

def get_audio_safety_service(
    min_confidence: float = 0.3,
    enable_llm: bool = True,
    enable_vector: bool = True
) -> AudioSafetyService:
    """Factory function for creating service instances."""
    return AudioSafetyService(
        min_confidence_threshold=min_confidence,
        enable_llm_summary=enable_llm,
        enable_vector_storage=enable_vector
    )
```

### FastAPI Dependency Injection

```python
# api/audio_analysis_routes.py

def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_service() -> AudioSafetyService:
    """Service dependency."""
    return get_audio_safety_service()

@router.post("/analyze")
async def analyze_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    service: AudioSafetyService = Depends(get_service)
):
    # Use injected dependencies
    result = await service.analyze_audio_file(filepath, filename, db)
    return result
```

## Error Handling

### Service Layer

```python
# services/audio_safety_service.py

try:
    transcript, timeline = await self._transcribe_audio(filepath)
    logger.info(f"Transcription completed")
except Exception as e:
    logger.error(f"Transcription failed: {str(e)}")
    raise Exception(f"Transcription failed: {str(e)}")
```

### API Layer

```python
# api/audio_analysis_routes.py

try:
    result = await service.analyze_audio_file(...)
    return result
except Exception as e:
    logger.error(f"Analysis failed: {str(e)}", exc_info=True)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Analysis failed: {str(e)}"
    )
```

### Global Exception Handler

```python
# app_v2.py

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )
```

## Logging

### Configuration

```python
# app_v2.py

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
```

### Usage

```python
# services/audio_safety_service.py

logger = logging.getLogger(__name__)

logger.info(f"Starting analysis for file: {filename}")
logger.warning(f"LLM summary generation failed: {str(e)}")
logger.error(f"Analysis failed: {str(e)}", exc_info=True)
```

## Async Compatibility

### Async Wrapper Decorator

```python
# services/audio_safety_service.py

def async_wrap(func):
    """Make synchronous functions async-compatible."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper

@async_wrap
def _transcribe_audio(self, filepath: str):
    return transcribe_audio(filepath)
```

### Async Endpoints

```python
# api/audio_analysis_routes.py

@router.post("/analyze")
async def analyze_audio(...):
    result = await service.analyze_audio_file(...)
    return result
```

## Database Persistence

### Model Definition

```python
# database/models.py

class AudioAnalysis(Base):
    __tablename__ = "audio_analysis"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String)
    transcript = Column(Text)
    findings = Column(Text)  # JSON
    evidence = Column(Text)  # JSON
    stats = Column(Text)     # JSON
    summary = Column(Text)
    llm_summary = Column(Text)
    severity = Column(String)
    risk_score = Column(Float)
    pdf_path = Column(String)
```

### Save Operation

```python
# services/audio_safety_service.py

record = AudioAnalysis(
    filename=filename,
    transcript=transcript,
    findings=json.dumps(findings),
    evidence=json.dumps(evidence),
    stats=json.dumps(stats),
    summary=rule_summary,
    llm_summary=llm_summary,
    severity=severity,
    risk_score=risk_score,
    pdf_path=""
)

db_session.add(record)
db_session.commit()
db_session.refresh(record)
```

## Response Schema

### Complete Analysis Response

```python
# schemas/audio_analysis_schemas.py

class AnalysisResponse(BaseModel):
    id: int
    filename: str
    transcript: str
    timeline: List[TimelineEntry]
    detection: DetectionResults
    evidence: List[Evidence]
    risk: RiskScore
    severity: str
    stats: Statistics
    summaries: Summaries
    pdf_report: str
    analysis_metadata: AnalysisMetadata
```

## API Endpoints

### V1 Endpoints

```
POST   /api/v1/analyze              - Analyze audio file
GET    /api/v1/health               - Health check
GET    /api/v1/history              - Get analysis history
GET    /api/v1/report/{id}          - Get report details
GET    /api/v1/report/{id}/evidence - Get report evidence
GET    /api/v1/report/{id}/stats    - Get report statistics
GET    /api/v1/report/{id}/pdf      - Download PDF report
POST   /api/v1/chat                 - Ask chatbot question
DELETE /api/v1/report/{id}          - Delete report
```

## Testing

### Run Application

```bash
# Development
python app_v2.py

# Production
uvicorn app_v2:app --host 0.0.0.0 --port 8000
```

### API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Example Request

```bash
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@conversation.mp3"
```

## Configuration

### Environment Variables

```python
# config.py

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
DATABASE_URL = "sqlite:///./analysis.db"
```

## Security Considerations

1. **File Upload Validation**: Check file extensions and size
2. **SQL Injection**: Use SQLAlchemy ORM (parameterized queries)
3. **CORS**: Configure allowed origins for production
4. **Rate Limiting**: Implement rate limiting for API endpoints
5. **Authentication**: Add JWT authentication for production
6. **Input Sanitization**: Validate all user inputs

## Performance Optimization

1. **Async Operations**: All I/O operations are async
2. **Database Connection Pooling**: SQLAlchemy connection pool
3. **Caching**: Consider caching for repeated analyses
4. **Background Tasks**: Use FastAPI BackgroundTasks for long operations
5. **Batch Processing**: Process multiple files in parallel

## Monitoring

1. **Logging**: Comprehensive logging at all layers
2. **Metrics**: Track analysis duration, success rate
3. **Health Checks**: `/health` endpoint for monitoring
4. **Error Tracking**: Log all exceptions with stack traces

## Future Enhancements

1. **Authentication & Authorization**: JWT-based auth
2. **Rate Limiting**: Prevent API abuse
3. **Caching**: Redis for caching results
4. **Message Queue**: Celery for background processing
5. **Microservices**: Split into separate services
6. **Kubernetes**: Container orchestration
7. **Monitoring**: Prometheus + Grafana
8. **CI/CD**: Automated testing and deployment
