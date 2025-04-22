import ee
import os
import tempfile
import requests
import json
import time
from datetime import datetime, timedelta
from loguru import logger
import rasterio
import numpy as np
from rasterio.transform import from_bounds
import shapely.geometry

from utils.storage import upload_file, MINIO_BUCKET_RASTERS

def initialize_earth_engine():
    """Initialize Earth Engine with service account credentials"""
    try:
        # Get the path to the service account key file
        credentials_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '/app/energy_progress.json')
        
        if not os.path.exists(credentials_path):
            logger.error(f"Earth Engine credentials file not found at {credentials_path}")
            raise FileNotFoundError(f"Earth Engine credentials file not found at {credentials_path}")
            
        logger.info(f"Using Earth Engine credentials from {credentials_path}")
        
        # Initialize with service account credentials
        credentials = ee.ServiceAccountCredentials(None, credentials_path)
        ee.Initialize(credentials)
        
        # Test authentication with a simple API call instead of loading a specific image
        # Just check if we can access the VIIRS collection
        try:
            collection = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
            # Just get info about the collection, don't try to load specific images
            info = collection.limit(1).getInfo()
            logger.info("Successfully connected to Earth Engine")
            return True
        except Exception as e:
            logger.error(f"Earth Engine connection test failed: {e}")
            # Don't fall back to development mode, propagate the error
            raise Exception(f"Failed to connect to Earth Engine API: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize Earth Engine: {e}")
        # Don't fall back to development mode, propagate the error
        raise Exception(f"Failed to initialize Earth Engine: {e}")

def get_viirs_collection(start_date, end_date):
    """Get VIIRS nightlight collection for a date range"""
    try:
        # Get the VIIRS nightlight collection
        collection = ee.ImageCollection('NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG')
        
        # Filter by date
        filtered = collection.filterDate(start_date, end_date)
        
        # Get the size to check if we have images
        size = filtered.size().getInfo()
        logger.info(f"Got VIIRS collection from {start_date} to {end_date} with {size} images")
        
        if size == 0:
            raise Exception(f"No VIIRS images found for date range {start_date} to {end_date}")
            
        return filtered
    except Exception as e:
        logger.error(f"Error getting VIIRS collection: {e}")
        raise Exception(f"Failed to get VIIRS collection for {start_date} to {end_date}: {e}")

def get_monthly_composite(year, month):
    """Create a monthly composite of VIIRS nightlight data"""
    # Calculate start and end dates for the month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # Format dates for Earth Engine
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    try:
        # Get the collection for this month
        collection = get_viirs_collection(start_str, end_str)
        
        # Create a composite by taking the mean value for each pixel
        composite = collection.mean()
        
        # Select the 'avg_rad' band (brightness)
        composite = composite.select(['avg_rad'])
        
        logger.info(f"Created composite for {start_str} to {end_str}")
        return composite, start_date
    except Exception as e:
        logger.error(f"Error creating monthly composite for {start_str} to {end_str}: {e}")
        raise Exception(f"Failed to create monthly composite for {year}-{month:02d}: {e}")

def download_ee_image(image, region, filename, scale=500):
    """Download an Earth Engine image directly to a file"""
    try:
        if not image:
            raise ValueError("No image provided for download")
            
        # Set up the export parameters
        url = image.getDownloadURL({
            'region': region,
            'scale': scale,
            'format': 'GEO_TIFF',
            'crs': 'EPSG:4326'
        })
        
        # Download the file
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            logger.info(f"Downloaded Earth Engine image to {filename}")
            
            # Verify the download is valid
            try:
                with rasterio.open(filename) as src:
                    # Check if file has valid data
                    if src.width <= 0 or src.height <= 0:
                        raise ValueError("Downloaded raster has invalid dimensions")
                    # Read a small sample to confirm data is accessible
                    sample = src.read(1, window=((0, min(10, src.height)), (0, min(10, src.width))))
                    logger.info(f"Successfully validated GeoTIFF: {filename}")
            except Exception as e:
                raise ValueError(f"Downloaded file is not a valid GeoTIFF: {e}")
                
            return filename
        else:
            raise Exception(f"Download failed with status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error in download_ee_image: {e}")
        raise Exception(f"Failed to download Earth Engine image: {e}")

def export_for_area(area_id, geom, year, month):
    """
    Export VIIRS data for a specific area and month
    
    Args:
        area_id: ID of the area
        geom: GeoJSON geometry of the area
        year: Year to process
        month: Month to process
        
    Returns:
        Path to the exported raster in MinIO
    """
    try:
        # Initialize Earth Engine
        if not initialize_earth_engine():
            raise Exception("Failed to initialize Earth Engine")
        
        logger.info(f"Processing nightlight data for area {area_id}, {year}-{month:02d}")
        
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create the Earth Engine geometry
            ee_geometry = ee.Geometry(geom)
            
            # Get the monthly composite
            composite, _ = get_monthly_composite(year, month)
            
            # Create filename for the downloaded raster
            local_path = os.path.join(tmp_dir, f"viirs_{area_id}_{year}_{month:02d}.tif")
            
            # Download the image
            download_ee_image(composite, ee_geometry, local_path)
            
            # Upload to MinIO
            month_str = f"{year}_{month:02d}"
            object_name = f"{area_id}/{month_str}/viirs_ntl.tif"
            result_path = upload_file(local_path, object_name, MINIO_BUCKET_RASTERS)
            
            logger.info(f"Successfully exported data for area {area_id}, {year}-{month:02d} to {result_path}")
            return result_path
        
    except Exception as e:
        logger.error(f"Error exporting VIIRS data for area {area_id}, {year}-{month:02d}: {e}")
        raise Exception(f"Failed to export VIIRS data for area {area_id}, {year}-{month:02d}: {e}")
