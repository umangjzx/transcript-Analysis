"""
Audio Safety Analyzer - FastAPI Application (Version 2.0)

This is the modernized version with:
- Dependency injection
- Service layer architecture
- Proper error handling
- Comprehensive logging
- Async-compatible implementation
- Pydantic schemas
- Modular route organization
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request, status
from datetime import datetime

# Import database
from database.db import engine, Base

# Import routes
from api.audio_analysis_routes import router as analysis_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {str(e)}")
    raise

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Audio Safety Analyzer",
    description="""
    Advanced audio safety analysis system for detecting grooming patterns in conversations.
    
    ## Features
    
    * **Audio Transcription**: Convert audio files to text with timestamps
    * **Grooming Detection**: Identify 10+ categories of grooming patterns
    * **Risk Scoring**: Calculate weighted risk scores with diminishing returns
    * **Severity Classification**: Classify conversations by severity level
    * **AI Summaries**: Generate rule-based and LLM-powered summaries
    * **PDF Reports**: Create comprehensive PDF reports
    * **Chatbot**: Ask questions about analysis results
    
    ## Pipeline
    
    1. Audio Upload → Transcription
    2. Pattern Detection (10 categories)
    3. Context Analysis (safe/risk indicators)
    4. Negation & Joke Filtering
    5. Confidence Calculation
    6. Evidence Grouping
    7. Risk Scoring
    8. Severity Classification
    9. Summary Generation
    10. PDF Report Creation
    11. Database Persistence
    
    ## Categories Detected
    
    - Meeting Requests (Critical)
    - Address/Location (Critical)
    - Secrecy (High)
    - Parent Monitoring (High)
    - School Information (Medium)
    - Routine/Schedule (Medium)
    - Video Call Requests (Medium)
    - Manipulation (Medium)
    - Trust Building (Low)
    - Relationship Building (Low)
    """,
    version="2.0.0",
    contact={
        "name": "Audio Safety Team",
        "email": "support@audiosafety.com"
    },
    license_info={
        "name": "Proprietary"
    }
)

# ============================================================================
# CORS MIDDLEWARE
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# GLOBAL EXCEPTION HANDLER
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.now().isoformat()
        }
    )

# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Execute on application startup."""
    logger.info("=" * 80)
    logger.info("Audio Safety Analyzer v2.0 Starting...")
    logger.info("=" * 80)
    logger.info("Service initialized successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Execute on application shutdown."""
    logger.info("Audio Safety Analyzer shutting down...")

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Audio Safety Analyzer",
        "version": "2.0.0",
        "status": "running",
        "documentation": "/docs",
        "api_version": "v1",
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# INCLUDE ROUTERS
# ============================================================================

app.include_router(analysis_router)

# ============================================================================
# ADDITIONAL ENDPOINTS (Legacy Compatibility)
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Legacy health check endpoint."""
    return {
        "status": "healthy",
        "service": "Audio Safety Analyzer",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app_v2:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
