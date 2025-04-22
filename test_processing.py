#!/usr/bin/env python3
"""
Test script for processing nightlight data for a specific area.
"""

import os
import sys
from datetime import datetime
from loguru import logger

# Add the etl directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'etl'))

# Import required functions
from etl.processors.nightlight import process_nightlight_raster, save_processing_results
from etl.utils.storage import download_file, MINIO_BUCKET_RASTERS

def process_area(area_id, month_date):
    """Process nightlight data for a specific area and month."""
    
    # Prepare paths
    month_str = month_date.strftime('%Y_%m')
    raster_path = f'rasters/{area_id}/{month_str}/viirs_ntl.tif'
    local_path = f'/tmp/viirs_{area_id}_{month_str}.tif'
    
    # Download the raster if needed
    logger.info(f"Downloading raster from {raster_path} to {local_path}")
    object_name = raster_path.replace('rasters/', '')
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
        logger.info(f"Results saved successfully as timeseries ID {timeseries.timeseries_id}")
        
        return results
    except Exception as e:
        logger.error(f"Error processing raster: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

if __name__ == "__main__":
    # Configure logger
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    # Process area 13 for January, February, and March 2024
    area_id = 13
    for month in [1, 2, 3]:
        month_date = datetime(2024, month, 1).date()
        logger.info(f"Processing area {area_id} for {month_date}")
        results = process_area(area_id, month_date)
        if results:
            logger.info(f"Processed area {area_id} for {month_date} - Mean brightness: {results['mean_brightness']}") 