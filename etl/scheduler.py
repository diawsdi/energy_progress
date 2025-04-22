#!/usr/bin/env python3
"""
Scheduler for the Energy Progress ETL service.
This script runs scheduled tasks for processing nightlight data.
"""

import os
import time
import schedule
from datetime import datetime, timedelta
from loguru import logger
import traceback
import json

# Import utilities - don't initialize storage at import time
from utils.db import get_db, Area, ProcessingJob 
# Import storage utilities but don't call initialize_buckets at import time
from utils.storage import download_file, MINIO_BUCKET_RASTERS, initialize_buckets, get_minio_client
from processors.nightlight import process_nightlight_raster, save_processing_results
from utils.earth_engine import export_for_area
from geoalchemy2.shape import to_shape
import shapely.geometry

# Log environment variables related to MinIO for debugging
def log_minio_config():
    """Log MinIO configuration for debugging"""
    logger.info(f"MinIO Host: {os.getenv('MINIO_HOST', 'Not set')}")
    logger.info(f"MinIO Port: {os.getenv('MINIO_PORT', 'Not set')}")
    logger.info(f"MinIO Access Key: {'Set' if os.getenv('MINIO_ACCESS_KEY') else 'Not set'}")
    logger.info(f"MinIO Secret Key: {'Set' if os.getenv('MINIO_SECRET_KEY') else 'Not set'}")
    logger.info(f"MinIO Secure: {os.getenv('MINIO_SECURE', 'Not set')}")
    logger.info(f"MinIO Bucket Rasters: {os.getenv('MINIO_BUCKET_RASTERS', 'Not set')}")
    logger.info(f"MinIO Bucket Tiles: {os.getenv('MINIO_BUCKET_TILES', 'Not set')}")

def process_pending_jobs():
    """Process any pending jobs in the database"""
    logger.info("Checking for pending jobs...")
    db = next(get_db())
    
    try:
        # Find pending jobs
        pending_jobs = db.query(ProcessingJob).filter(
            ProcessingJob.status == "pending"
        ).order_by(
            ProcessingJob.created_at
        ).limit(10).all()
        
        if pending_jobs:
            # Initialize MinIO buckets when we have jobs to process
            try:
                initialize_buckets()
            except Exception as e:
                logger.error(f"Error initializing MinIO buckets: {e}")
                logger.error(traceback.format_exc())
        
        for job in pending_jobs:
            try:
                logger.info(f"Processing job {job.job_id} for area {job.area_id}")
                
                # Update job status to running
                job.status = "running"
                db.commit()
                
                if job.job_type == "etl_processing":
                    # Get the area
                    area = db.query(Area).filter(Area.area_id == job.area_id).first()
                    if not area:
                        logger.error(f"Area {job.area_id} not found")
                        job.status = "failed"
                        job.error_message = f"Area {job.area_id} not found"
                        db.commit()
                        continue
                    
                    # Get job metadata (should contain raster path)
                    raster_path = job.meta_data.get("raster_path")
                    if not raster_path:
                        logger.error(f"No raster path in job metadata")
                        job.status = "failed"
                        job.error_message = "No raster path in job metadata"
                        db.commit()
                        continue
                    
                    # Download the raster if it's a MinIO path
                    if raster_path.startswith(f"{MINIO_BUCKET_RASTERS}/"):
                        object_name = raster_path.replace(f"{MINIO_BUCKET_RASTERS}/", "")
                        local_path = f"/tmp/{object_name.split('/')[-1]}"
                        download_file(object_name, local_path, MINIO_BUCKET_RASTERS)
                        raster_path = local_path
                    
                    # Process the raster
                    month_date = job.start_date
                    if not month_date:
                        # Use the first day of the current month if not specified
                        today = datetime.now()
                        month_date = datetime(today.year, today.month, 1).date()
                    
                    results = process_nightlight_raster(
                        area_id=job.area_id,
                        month_date=month_date,
                        raster_path=raster_path
                    )
                    
                    # Save results to database
                    save_processing_results(job.area_id, month_date, results)
                    
                    # Update job status
                    job.status = "completed"
                    db.commit()
                    logger.info(f"Job {job.job_id} completed successfully")
                
                elif job.job_type == "earth_engine_export":
                    # Get the area
                    area = db.query(Area).filter(Area.area_id == job.area_id).first()
                    if not area:
                        logger.error(f"Area {job.area_id} not found")
                        job.status = "failed"
                        job.error_message = f"Area {job.area_id} not found"
                        db.commit()
                        continue
                    
                    # Get date range from job metadata
                    start_date = job.start_date
                    end_date = job.end_date or start_date
                    
                    # Convert PostGIS geometry to GeoJSON
                    shapely_geom = to_shape(area.geom)
                    geojson = json.loads(json.dumps(shapely.geometry.mapping(shapely_geom)))
                    
                    # Process each month in the date range
                    current_date = start_date
                    while current_date <= end_date:
                        try:
                            # Export data for this month
                            raster_path = export_for_area(
                                area_id=job.area_id,
                                geom=geojson,
                                year=current_date.year,
                                month=current_date.month
                            )
                            
                            # Create a processing job for the exported data
                            etl_job = ProcessingJob(
                                area_id=job.area_id,
                                job_type="etl_processing",
                                status="pending",
                                start_date=current_date,
                                meta_data={
                                    "raster_path": raster_path,
                                    "parent_job_id": str(job.job_id)
                                }
                            )
                            db.add(etl_job)
                            db.commit()
                            
                            # Move to next month
                            if current_date.month == 12:
                                current_date = datetime(current_date.year + 1, 1, 1).date()
                            else:
                                current_date = datetime(current_date.year, current_date.month + 1, 1).date()
                                
                        except Exception as e:
                            logger.error(f"Error processing month {current_date}: {e}")
                            logger.error(traceback.format_exc())
                            # Continue with next month
                            if current_date.month == 12:
                                current_date = datetime(current_date.year + 1, 1, 1).date()
                            else:
                                current_date = datetime(current_date.year, current_date.month + 1, 1).date()
                    
                    # Update job status
                    job.status = "completed"
                    db.commit()
                    logger.info(f"Earth Engine export job {job.job_id} completed successfully")
                    
                else:
                    logger.warning(f"Unknown job type: {job.job_type}")
                    job.status = "failed"
                    job.error_message = f"Unknown job type: {job.job_type}"
                    db.commit()
                
            except Exception as e:
                logger.error(f"Error processing job {job.job_id}: {e}")
                logger.error(traceback.format_exc())
                job.status = "failed"
                job.error_message = str(e)
                db.commit()
                
    except Exception as e:
        logger.error(f"Error in process_pending_jobs: {e}")
        logger.error(traceback.format_exc())
    finally:
        db.close()

def run_scheduler():
    """Run the scheduler"""
    logger.info("Starting scheduler...")
    
    # Log MinIO configuration on startup
    log_minio_config()
    
    # Give MinIO and Postgres time to fully initialize
    logger.info("Waiting 10 seconds for services to be fully available...")
    time.sleep(10)
    
    # Test MinIO connection
    try:
        client = get_minio_client()
        logger.info(f"Successfully connected to MinIO service")
    except Exception as e:
        logger.error(f"Initial MinIO connection test failed: {e}")
    
    # Initialize MinIO buckets at startup with retry mechanism
    max_attempts = 5
    attempts = 0
    success = False
    
    while not success and attempts < max_attempts:
        try:
            logger.info(f"Attempt {attempts+1}/{max_attempts} to initialize MinIO buckets")
            initialize_buckets()
            logger.info("MinIO buckets initialized successfully")
            success = True
        except Exception as e:
            attempts += 1
            logger.error(f"Error initializing MinIO buckets (attempt {attempts}/{max_attempts}): {e}")
            logger.error(traceback.format_exc())
            if attempts < max_attempts:
                wait_time = 5 * attempts  # Exponential backoff
                logger.info(f"Waiting {wait_time} seconds before next attempt...")
                time.sleep(wait_time)
    
    if not success:
        logger.warning("Failed to initialize MinIO buckets after multiple attempts")
        logger.warning("Will assume buckets were created by MinIO client container")
        # Don't treat this as a fatal error, continue processing
        success = True
    
    # Schedule jobs to run every 5 minutes
    schedule.every(5).minutes.do(process_pending_jobs)
    
    # Run pending jobs immediately
    process_pending_jobs()
    
    # Run the scheduler
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logger.info("Energy Progress ETL service starting...")
    run_scheduler()