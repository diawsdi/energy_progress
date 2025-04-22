import os
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from fastapi import FastAPI, Depends, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from geojson import Polygon, Feature, FeatureCollection
from loguru import logger
import json
from shapely.geometry import shape
from geoalchemy2.shape import to_shape
import shapely

# Import database models and connection
from db import get_db, Area, AreaTimeseries, ProcessingJob
from minio_client import minio_client, MINIO_PUBLIC_ENDPOINT, MINIO_BUCKET_TILES

# Initialize FastAPI app
app = FastAPI(
    title="Energy Progress API",
    description="API for tracking electrification progress using nightlight data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class AreaCreate(BaseModel):
    name: str
    geometry: Dict[str, Any]  # GeoJSON Polygon
    meta_data: Optional[Dict[str, Any]] = None

class AreaResponse(BaseModel):
    area_id: int
    name: str
    geometry: Dict[str, Any]  # GeoJSON
    created_at: datetime
    meta_data: Optional[Dict[str, Any]] = None

class TimeseriesResponse(BaseModel):
    area_id: int
    month: date
    mean_brightness: Optional[float] = None
    median_brightness: Optional[float] = None
    sum_brightness: Optional[float] = None
    lit_pixel_count: Optional[int] = None
    lit_percentage: Optional[float] = None
    tile_url_template: Optional[str] = None
    min_zoom: Optional[int] = None
    max_zoom: Optional[int] = None
    bounding_box: Optional[Dict[str, float]] = None

class JobStatus(BaseModel):
    job_id: str
    area_id: int
    job_type: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None

class EarthEngineJobCreate(BaseModel):
    area_id: int
    start_date: date
    end_date: Optional[date] = None

@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "energy_progress_api"}

@app.post("/areas/", response_model=AreaResponse)
def create_area(area: AreaCreate, db: Session = Depends(get_db)):
    """Create a new area for monitoring."""
    try:
        # Validate geometry is a Polygon
        if area.geometry.get("type") != "Polygon":
            raise HTTPException(status_code=400, detail="Geometry must be a GeoJSON Polygon")
        
        # Convert GeoJSON to WKT format with SRID for PostGIS
        geom_shape = shape(area.geometry)
        geom_wkt = f"SRID=4326;{geom_shape.wkt}"
        
        # Create new area in database
        db_area = Area(
            name=area.name,
            geom=geom_wkt,
            meta_data=area.meta_data or {}
        )
        db.add(db_area)
        db.commit()
        db.refresh(db_area)
        
        # Return the created area
        return {
            "area_id": db_area.area_id,
            "name": db_area.name,
            "geometry": area.geometry,  # Return the original GeoJSON
            "created_at": db_area.created_at,
            "meta_data": db_area.meta_data
        }
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating area: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error creating area: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/areas/", response_model=List[AreaResponse])
def list_areas(db: Session = Depends(get_db)):
    """List all areas."""
    try:
        # Get all areas
        areas = db.query(Area).all()
        
        # Convert PostGIS geometry to GeoJSON
        result = []
        for area in areas:
            # Convert WKB to Shapely geometry and then to GeoJSON
            shapely_geom = to_shape(area.geom)
            geojson = json.loads(json.dumps(shapely.geometry.mapping(shapely_geom)))
            
            result.append({
                "area_id": area.area_id,
                "name": area.name,
                "geometry": geojson,
                "created_at": area.created_at,
                "meta_data": area.meta_data
            })
        
        return result
    except Exception as e:
        logger.error(f"Error listing areas: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/areas/{area_id}", response_model=AreaResponse)
def get_area(area_id: int, db: Session = Depends(get_db)):
    """Get a specific area by ID."""
    try:
        # Get the area
        area = db.query(Area).filter(Area.area_id == area_id).first()
        if not area:
            raise HTTPException(status_code=404, detail=f"Area with ID {area_id} not found")
        
        # Convert PostGIS geometry to GeoJSON
        # Convert WKB to Shapely geometry and then to GeoJSON
        shapely_geom = to_shape(area.geom)
        geojson = json.loads(json.dumps(shapely.geometry.mapping(shapely_geom)))
        
        return {
            "area_id": area.area_id,
            "name": area.name,
            "geometry": geojson,
            "created_at": area.created_at,
            "meta_data": area.meta_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting area {area_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/areas/{area_id}/timeseries", response_model=List[TimeseriesResponse])
def get_area_timeseries(
    area_id: int, 
    start_date: Optional[date] = None, 
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Get timeseries data for a specific area, optionally filtered by date range."""
    # Check if area exists
    area = db.query(Area).filter(Area.area_id == area_id).first()
    if not area:
        raise HTTPException(status_code=404, detail=f"Area with ID {area_id} not found")
    
    # Build query
    query = db.query(AreaTimeseries).filter(AreaTimeseries.area_id == area_id)
    
    # Apply date filters if provided
    if start_date:
        query = query.filter(AreaTimeseries.month >= start_date)
    if end_date:
        query = query.filter(AreaTimeseries.month <= end_date)
    
    # Execute query
    timeseries = query.order_by(AreaTimeseries.month).all()
    
    # Format public URLs for tile patterns
    results = []
    for ts in timeseries:
        # Replace bucket name with public endpoint if available
        tile_url_template = None
        if ts.tile_path_pattern:
            tile_url_template = ts.tile_path_pattern.replace(
                f"{MINIO_BUCKET_TILES}/", 
                f"{MINIO_PUBLIC_ENDPOINT}/{MINIO_BUCKET_TILES}/"
            )
        
        results.append({
            "area_id": ts.area_id,
            "month": ts.month,
            "mean_brightness": ts.mean_brightness,
            "median_brightness": ts.median_brightness,
            "sum_brightness": ts.sum_brightness,
            "lit_pixel_count": ts.lit_pixel_count,
            "lit_percentage": ts.lit_percentage,
            "tile_url_template": tile_url_template,
            "min_zoom": ts.min_zoom,
            "max_zoom": ts.max_zoom,
            "bounding_box": ts.bounding_box
        })
    
    return results

@app.get("/jobs/", response_model=List[JobStatus])
def list_jobs(
    area_id: Optional[int] = None, 
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List processing jobs, optionally filtered by area, status, and type."""
    query = db.query(ProcessingJob)
    
    if area_id:
        query = query.filter(ProcessingJob.area_id == area_id)
    if status:
        query = query.filter(ProcessingJob.status == status)
    if job_type:
        query = query.filter(ProcessingJob.job_type == job_type)
    
    jobs = query.order_by(ProcessingJob.created_at.desc()).all()
    
    return [{
        "job_id": str(job.job_id),
        "area_id": job.area_id,
        "job_type": job.job_type,
        "status": job.status,
        "start_date": job.start_date,
        "end_date": job.end_date,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error_message": job.error_message
    } for job in jobs]

@app.get("/statistics")
def get_statistics(db: Session = Depends(get_db)):
    """Get overall system statistics."""
    try:
        # Count areas
        area_count = db.query(Area).count()
        
        # Count months with data
        month_count = db.query(AreaTimeseries.month).distinct().count()
        
        # Count total time series records
        record_count = db.query(AreaTimeseries).count()
        
        # Get latest processed month
        latest_month = db.query(AreaTimeseries.month).order_by(AreaTimeseries.month.desc()).first()
        latest_month_str = latest_month[0].isoformat() if latest_month else None
        
        # Count jobs by status
        job_counts = {}
        for status in ["pending", "running", "completed", "failed"]:
            job_counts[status] = db.query(ProcessingJob).filter(ProcessingJob.status == status).count()
        
        return {
            "area_count": area_count,
            "month_count": month_count,
            "record_count": record_count,
            "latest_month": latest_month_str,
            "job_counts": job_counts,
            "system_time": datetime.now()
        }
    except SQLAlchemyError as e:
        logger.error(f"Database error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/earth-engine/export/", response_model=JobStatus)
def create_earth_engine_job(job: EarthEngineJobCreate, db: Session = Depends(get_db)):
    """Create a job to export VIIRS nightlight data from Earth Engine."""
    try:
        # Check if area exists
        area = db.query(Area).filter(Area.area_id == job.area_id).first()
        if not area:
            raise HTTPException(status_code=404, detail=f"Area with ID {job.area_id} not found")
        
        # Create job
        db_job = ProcessingJob(
            area_id=job.area_id,
            job_type="earth_engine_export",
            status="pending",
            start_date=job.start_date,
            end_date=job.end_date or job.start_date,
            meta_data={}
        )
        db.add(db_job)
        db.commit()
        db.refresh(db_job)
        
        return {
            "job_id": str(db_job.job_id),
            "area_id": db_job.area_id,
            "job_type": db_job.job_type,
            "status": db_job.status,
            "start_date": db_job.start_date,
            "end_date": db_job.end_date,
            "created_at": db_job.created_at,
            "updated_at": db_job.updated_at,
            "error_message": db_job.error_message
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating Earth Engine job: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 