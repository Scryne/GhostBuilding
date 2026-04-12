from sqlalchemy import Column, String, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.db.base_class import Base
from app.models.enums import UserRole

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, default=UserRole.USER.value, nullable=False)
    trust_score = Column(Float, default=50.0)
    verified_count = Column(Integer, default=0)
    submitted_count = Column(Integer, default=0)

    verifications = relationship("Verification", back_populates="user")

    def __repr__(self):
        return f"<User {self.username} (Role: {self.role}, Trust: {self.trust_score})>"
