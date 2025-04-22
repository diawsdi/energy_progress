import os
import socket
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from datetime import datetime
import uuid
from loguru import logger

# Database configuration from environment variables
DB_USER = os.getenv("POSTGRES_USER", "energy_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "energy_password")
DB_HOST = os.getenv("POSTGRES_HOST", "energy_progress_postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "energy_progress")

# Try to resolve hostname to IP address for more reliable connection
try:
    # Check if hostname is not already an IP address
    if not all(part.isdigit() for part in DB_HOST.split('.')):
        logger.info(f"Resolving database hostname {DB_HOST} to IP address...")
        db_host_ip = socket.gethostbyname(DB_HOST)
        logger.info(f"Resolved {DB_HOST} to IP address {db_host_ip}")
        DB_HOST = db_host_ip
except Exception as e:
    logger.warning(f"Error resolving database hostname {DB_HOST}: {e}. Using original hostname.")

# Construct database URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

logger.info(f"Connecting to database at {DB_HOST}:{DB_PORT}")

# Create SQLAlchemy engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Get a database session, ensure it's closed when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Database models
class Area(Base):
    __tablename__ = "areas"

    area_id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    geom = Column(Geometry("POLYGON", srid=4326), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    meta_data = Column(JSONB)

    # Relationships
    timeseries = relationship("AreaTimeseries", back_populates="area")
    jobs = relationship("ProcessingJob", back_populates="area")

class AreaTimeseries(Base):
    __tablename__ = "area_timeseries"

    area_id = Column(Integer, ForeignKey("areas.area_id", ondelete="CASCADE"), primary_key=True)
    month = Column(Date, primary_key=True)
    mean_brightness = Column(Float)
    median_brightness = Column(Float)
    sum_brightness = Column(Float)
    lit_pixel_count = Column(Integer)
    lit_percentage = Column(Float)
    tile_path_pattern = Column(Text)
    raster_path = Column(Text)
    min_zoom = Column(Integer)
    max_zoom = Column(Integer)
    bounding_box = Column(JSONB)
    meta_data = Column(JSONB)

    # Relationships
    area = relationship("Area", back_populates="timeseries")

class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    area_id = Column(Integer, ForeignKey("areas.area_id", ondelete="CASCADE"))
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.now)
    updated_at = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now)
    error_message = Column(Text)
    meta_data = Column(JSONB)

    # Relationships
    area = relationship("Area", back_populates="jobs") 