from sqlalchemy import Column, String, Text, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base_class import Base

class Verification(Base):
    __tablename__ = "verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id = Column(UUID(as_uuid=True), ForeignKey("anomalies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    vote = Column(String, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=text('now()'))

    anomaly = relationship("Anomaly", back_populates="verifications")
    user = relationship("User", back_populates="verifications")

    def __repr__(self):
        return f"<Verification {self.vote} by {self.user_id} on {self.anomaly_id}>"
