#!/usr/bin/env python3
"""
Test script for processing nightlight data for a specific area.
This script runs directly inside the ETL container.
"""

import os
from datetime import datetime
from loguru import logger

# Import required functions
from processors.nightlight import process_nightlight_raster, save_processing_results
from utils.storage import download_file, MINIO_BUCKET_RASTERS

def process_area(area_id, month_date):
    """Process nightlight data for a specific area and month."""
    
    # Prepare paths
    month_str = month_date.strftime('%Y_%m')
    raster_path = f'{MINIO_BUCKET_RASTERS}/{area_id}/{month_str}/viirs_ntl.tif'
    local_path = f'/tmp/viirs_{area_id}_{month_str}.tif'
    
    # Download the raster if needed
    logger.info(f"Downloading raster from {raster_path} to {local_path}")
    object_name = raster_path.replace(f'{MINIO_BUCKET_RASTERS}/', '')
    download_file(object_name, local_path, MINIO_BUCKET_RASTERS)
    
    # Process the raster
    logger.info(f"Processing raster for area {area_id}, month {month_date}")
    try:
        results = process_nightlight_raster(
            area_id=area_id,
            month_date=month_date,
            raster_path=local_path
        )
        
        logger.info(f"Processing results: {results}")
        
        # Save the results
        timeseries = save_processing_results(area_id, month_date, results)
        logger.info(f"Results saved successfully")
        
        return results
    except Exception as e:
        logger.error(f"Error processing raster: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

if __name__ == "__main__":
    # Process area 13 for January 2024
    area_id = 13
    month_date = datetime(2024, 1, 1).date()
    logger.info(f"Processing area {area_id} for {month_date}")
    results = process_area(area_id, month_date)
    if results:
        logger.info(f"Processed area {area_id} for {month_date} - Mean brightness: {results['mean_brightness']}") 