from sqlalchemy import inspect,text
from .db import engine

def upgrade():
    # Additive migration for installations created before surveyed-road support.
    inspector=inspect(engine)
    if 'segments' in inspector.get_table_names() and 'is_demo' not in {c['name'] for c in inspector.get_columns('segments')}:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE segments ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT TRUE'))
