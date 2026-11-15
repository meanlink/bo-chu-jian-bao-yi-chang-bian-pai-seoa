from sqlalchemy import String, JSON, Double, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Dataset(Base):
    __tablename__ = 'datasets'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200), default='manual.json')
    records: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Double)
    # 发布依据：仅已发布的接入批次可以生成业务批次，发布后只读
    ingestion_batch_id: Mapped[int | None] = mapped_column(ForeignKey('ingestion_batches.id'), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey('ingestion_contracts.id'), nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
