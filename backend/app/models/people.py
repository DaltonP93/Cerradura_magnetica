"""People: departments, cardholders and their credentials."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.database import Base
from app.models.base import CredentialType, OrgScopedMixin, TimestampMixin


class Department(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))

    cardholders: Mapped[list["Cardholder"]] = relationship(back_populates="department")


class Cardholder(Base, TimestampMixin, OrgScopedMixin):
    """A person who holds access credentials (employee, visitor, contractor)."""

    __tablename__ = "cardholders"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    employee_number: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    photo_url: Mapped[str | None] = mapped_column(String(500))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1000))

    department: Mapped[Department | None] = relationship(back_populates="cardholders")
    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="cardholder", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def access_level_ids(self) -> list[int]:
        return [level.id for level in self.access_levels]  # backref from AccessLevel


class Credential(Base, TimestampMixin, OrgScopedMixin):
    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("organization_id", "card_number", name="uq_credential_org_card"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cardholder_id: Mapped[int] = mapped_column(
        ForeignKey("cardholders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[CredentialType] = mapped_column(
        Enum(CredentialType), default=CredentialType.CARD, nullable=False
    )
    card_number: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    # Stored encrypted at rest (see app.core.crypto); the attribute is plaintext.
    pin: Mapped[str | None] = mapped_column(EncryptedString(255))  # required for CARD_PLUS_PIN
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cardholder: Mapped[Cardholder] = relationship(back_populates="credentials")
