from sqlalchemy import Column, String, Float, Text, DateTime, text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
import uuid
from datetime import datetime, timezone
from app.db.base_class import Base

class Anomaly(Base):
    __tablename__ = "anomalies"

    __table_args__ = (
        Index('ix_anomalies_category_status_confidence', 'category', 'status', 'confidence_score'),
        Index('ix_anomalies_covering', 'category', 'status', 'lat', 'lng', 'confidence_score'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    geom = Column(Geometry(geometry_type='POINT', srid=4326), nullable=False)
    
    category = Column(String, nullable=False)
    confidence_score = Column(Float, default=0.0)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default="PENDING")
    
    detected_at = Column(DateTime(timezone=True), server_default=text('now()'))
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    source_providers = Column(JSONB, default=list)
    detection_methods = Column(JSONB, default=list)
    meta_data = Column(JSONB, default=dict) # Avoid 'metadata' conflict
    
    created_at = Column(DateTime(timezone=True), server_default=text('now()'))
    updated_at = Column(DateTime(timezone=True), server_default=text('now()'), onupdate=datetime.now(timezone.utc))

    images = relationship("AnomalyImage", back_populates="anomaly", cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="anomaly", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Anomaly {self.category} @ ({self.lat}, {self.lng}) - Score: {self.confidence_score}>"

    @property
    def is_highly_confident(self):
        return self.confidence_score >= 85.0
