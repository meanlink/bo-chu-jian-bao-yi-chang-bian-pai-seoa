from sqlalchemy import String, JSON, Double, Integer, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base

class IngestionContract(Base):
    """接入契约：按来源版本登记列映射与单位，版本化不可变；更新即生成新版本。"""
    __tablename__ = 'ingestion_contracts'
    id: Mapped[int] = mapped_column(primary_key=True)
    source_version: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    column_mapping: Mapped[dict] = mapped_column(JSON)   # 原始列名 -> 标准列 key
    units: Mapped[dict] = mapped_column(JSON)           # 标准列 key -> 原始单位
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    checksum: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('source_version', 'version', name='uq_contract_version'),)

class IngestionBatch(Base):
    """待审核区批次：保留原文、错误历史与所用契约快照；发布前不产生业务批次。"""
    __tablename__ = 'ingestion_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source: Mapped[str] = mapped_column(String(200))
    source_version: Mapped[str] = mapped_column(String(80))
    raw_text: Mapped[str] = mapped_column(Text)
    raw_format: Mapped[str] = mapped_column(String(10))      # csv / json
    raw_checksum: Mapped[str] = mapped_column(String(64))
    raw_revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default='staged')
    errors: Mapped[list] = mapped_column(JSON, default=list)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey('ingestion_contracts.id'), nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_records: Mapped[list | None] = mapped_column(JSON, nullable=True)
    validated_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # 反向引用，use_alter 打破与 batches/datasets 的建表循环
    validated_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey('ingestion_attempts.id', use_alter=True, name='fk_batch_validated_attempt'), nullable=True)
    published_dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey('datasets.id', use_alter=True, name='fk_batch_published_dataset'), nullable=True)
    published_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    published_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)

class IngestionAttempt(Base):
    """每次初次接入与重放的留痕：保留当时的原文指纹、错误和所用契约。"""
    __tablename__ = 'ingestion_attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey('ingestion_batches.id'))
    kind: Mapped[str] = mapped_column(String(20))          # initial / replay
    status: Mapped[str] = mapped_column(String(20), default='queued')
    raw_checksum: Mapped[str] = mapped_column(String(64))
    raw_revision: Mapped[int] = mapped_column(Integer)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey('ingestion_contracts.id'), nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
