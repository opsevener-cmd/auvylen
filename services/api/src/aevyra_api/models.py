from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from aevyra_api.database import Base


class FoundationRecord(Base):
    """One operational marker proves migrations; not a future product entity."""

    __tablename__ = "foundation_records"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
