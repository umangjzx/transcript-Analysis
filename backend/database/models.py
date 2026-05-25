from datetime import datetime
import json

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from sqlalchemy.types import TypeDecorator


Base = declarative_base()


class JSONEncoder(TypeDecorator):
    """Automatically encode/decode JSON for SQLite compatibility."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class AudioAnalysis(Base):

    __tablename__ = "audio_analysis"

    id = Column(Integer, primary_key=True, index=True)

    filename = Column(String)

    transcript = Column(Text)

    findings = Column(JSONEncoder, default=list)

    evidence = Column(JSONEncoder, default=list)

    stats = Column(JSONEncoder, default=dict)

    summary = Column(Text)

    llm_summary = Column(Text)

    severity = Column(String)

    risk_score = Column(Float)

    pdf_path = Column(String)

    status = Column(String, default="PENDING")

    error_message = Column(String, nullable=True)

    diarization = Column(JSONEncoder, nullable=True, default=list)

    # Timestamp columns — added to track when each record was created/updated
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
