from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base_class import Base

class AnomalyImage(Base):
    __tablename__ = "anomaly_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id = Column(UUID(as_uuid=True), ForeignKey("anomalies.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String, nullable=False)
    image_url = Column(String, nullable=False)
    
    captured_at = Column(DateTime(timezone=True), nullable=False)
    zoom_level = Column(Integer)
    tile_x = Column(Integer)
    tile_y = Column(Integer)
    tile_z = Column(Integer)
    
    diff_score = Column(Float)
    is_blurred = Column(Boolean, default=False)

    anomaly = relationship("Anomaly", back_populates="images")

    def __repr__(self):
        return f"<AnomalyImage {self.provider} for Anomaly {self.anomaly_id}>"

    @property
    def coordinates_tile(self):
        return (self.tile_x, self.tile_y, self.tile_z)
