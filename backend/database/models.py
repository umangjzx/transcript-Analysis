from sqlalchemy.orm import declarative_base

from sqlalchemy import Column
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Float
from sqlalchemy import Text


Base = declarative_base()


class AudioAnalysis(Base):

    __tablename__ = "audio_analysis"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    filename = Column(
        String
    )

    transcript = Column(
        Text
    )

    findings = Column(
        Text
    )

    evidence = Column(
        Text
    )

    stats = Column(
        Text
    )

    summary = Column(
        Text
    )

    llm_summary = Column(
        Text
    )

    severity = Column(
        String
    )

    risk_score = Column(
        Float
    )

    pdf_path = Column(
        String
    )

    status = Column(
        String,
        default="PENDING"
    )

    error_message = Column(
        String,
        nullable=True
    )