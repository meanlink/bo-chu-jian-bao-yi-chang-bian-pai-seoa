from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models  # noqa: F401  注册全部模型

# 已上线表的新增列（幂等补列；全新库由 create_all 直接建出）
_ADDED_COLUMNS = {
    'datasets': [
        ('ingestion_batch_id', 'INT NULL'),
        ('contract_id', 'INT NULL'),
        ('contract_version', 'INT NULL'),
    ],
}

def migrate():
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in existing:
                continue
            present = {col['name'] for col in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))

if __name__=='__main__':migrate()
