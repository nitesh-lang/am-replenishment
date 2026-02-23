from sqlalchemy import create_engine
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/am_replenishment"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

def get_engine():
    return engine