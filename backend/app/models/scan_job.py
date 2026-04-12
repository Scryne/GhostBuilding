from sqlalchemy import Column, String, Float, Integer, DateTime, text
from sqlalchemy.dialects.postgresql import UUID
import uuid
from app.db.base_class import Base

class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, nullable=False, default="PENDING")
    
    center_lat = Column(Float, nullable=False)
    center_lng = Column(Float, nullable=False)
    radius_km = Column(Float, nullable=False)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    anomaly_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<ScanJob {self.id} | Status: {self.status} | Found: {self.anomaly_count}>"

    @property
    def coverage_area(self):
        return 3.14159 * (self.radius_km ** 2)
