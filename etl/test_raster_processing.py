#!/usr/bin/env python3
"""
Test script for raster processing and Earth Engine export.
This script is used to verify fixes to the nightlight processing workflow.
"""

import os
import sys
import json
import logging
from loguru import logger
from datetime import datetime
import tempfile
import traceback

# Configure logging
logger.remove()
logger.add(sys.stdout, level="DEBUG")  # Changed to stdout and DEBUG level for more verbose output
logger.info("=== Starting Test Script for Nightlight Processing ===")

# Import our modules
try:
    logger.info("Importing modules...")
    from utils.storage import initialize_buckets, upload_file, MINIO_BUCKET_RASTERS
    from utils.earth_engine import export_for_area, initialize_earth_engine
    from processors.nightlight import process_nightlight_raster, save_processing_results
    logger.success("Successfully imported all modules")
except Exception as e:
    logger.error(f"Error importing modules: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

def test_earth_engine_export():
    """Test Earth Engine export functionality"""
    logger.info("Starting Earth Engine export test...")
    
    # Test area geometry (simple polygon for testing)
    test_geom = {
        "type": "Polygon",
        "coordinates": [
            [
                [35.0, -1.0],
                [35.5, -1.0],
                [35.5, -0.5],
                [35.0, -0.5],
                [35.0, -1.0]
            ]
        ]
    }
    
    try:
        # Initialize Earth Engine
        logger.info("Initializing Earth Engine...")
        if not initialize_earth_engine():
            logger.error("Failed to initialize Earth Engine")
            return False
        
        # Try to export data for this area
        logger.info("Attempting to export data for test area...")
        result_path = export_for_area(
            area_id=999,  # Test area ID
            geom=test_geom,
            year=2024,
            month=1
        )
        
        logger.success(f"Successfully exported test data to: {result_path}")
        return result_path
    
    except Exception as e:
        logger.error(f"Error testing Earth Engine export: {e}")
        logger.error(traceback.format_exc())
        return False

def test_nightlight_processing(raster_path=None):
    """Test nightlight raster processing functionality"""
    logger.info("Starting nightlight processing test...")
    
    try:
        # If no raster path provided, create a test GeoTIFF
        if not raster_path:
            logger.info("No raster path provided, creating test GeoTIFF...")
            import numpy as np
            import rasterio
            from rasterio.transform import from_bounds
            
            # Create a temporary directory
            tmp_dir = tempfile.mkdtemp()
            logger.debug(f"Created temporary directory: {tmp_dir}")
            
            # Create a small test raster
            data = np.random.rand(1, 10, 10) * 10  # Values between 0-10
            logger.debug(f"Created random data array with shape {data.shape}")
            
            # Create a transform for a small area
            minx, miny, maxx, maxy = 35.0, -1.0, 35.5, -0.5
            transform = from_bounds(minx, miny, maxx, maxy, 10, 10)
            logger.debug(f"Created transform with bounds: {minx}, {miny}, {maxx}, {maxy}")
            
            # Create metadata
            meta = {
                'driver': 'GTiff',
                'height': 10,
                'width': 10,
                'count': 1,
                'dtype': 'float32',
                'crs': '+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs',
                'transform': transform,
                'nodata': 0
            }
            
            # Write test raster
            test_raster_path = os.path.join(tmp_dir, "test_raster.tif")
            with rasterio.open(test_raster_path, 'w', **meta) as dst:
                dst.write(data.astype('float32'))
            
            logger.info(f"Created test raster at: {test_raster_path}")
            raster_path = test_raster_path
        else:
            logger.info(f"Using provided raster path: {raster_path}")
        
        # Test area ID and date
        area_id = 999
        month_date = datetime(2024, 1, 1).date()
        
        # First create a test area in the database
        from utils.db import get_db, Area
        from geoalchemy2 import Geometry
        from sqlalchemy import func
        import json
        
        # Test geometry
        test_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [35.0, -1.0],
                    [35.5, -1.0],
                    [35.5, -0.5],
                    [35.0, -0.5],
                    [35.0, -1.0]
                ]
            ]
        }
        
        # Connect to the database
        logger.info("Creating test area in database...")
        db = next(get_db())
        
        try:
            # Check if test area already exists
            existing_area = db.query(Area).filter(Area.area_id == area_id).first()
            
            if existing_area:
                logger.info(f"Test area with ID {area_id} already exists, using it")
            else:
                # Create a test area
                geom_wkt = f"SRID=4326;{json.dumps(test_geom)}"
                area = Area(
                    area_id=area_id,
                    name=f"Test Area {area_id}",
                    geom=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(test_geom)), 4326),
                    meta_data={
                        "test": True,
                        "created_at": datetime.now().isoformat()
                    }
                )
                db.add(area)
                db.commit()
                logger.info(f"Created test area with ID {area_id}")
        except Exception as db_error:
            logger.error(f"Error creating test area: {db_error}")
            db.rollback()
            raise
        finally:
            db.close()
        
        # Process the raster
        logger.info(f"Processing raster for area ID {area_id}, month {month_date}...")
        results = process_nightlight_raster(
            area_id=area_id,
            month_date=month_date,
            raster_path=raster_path
        )
        
        logger.success(f"Successfully processed nightlight raster. Results:")
        logger.info(f"Mean brightness: {results.get('mean_brightness')}")
        logger.info(f"Median brightness: {results.get('median_brightness')}")
        logger.info(f"Lit pixel count: {results.get('lit_pixel_count')}")
        logger.info(f"Tile path pattern: {results.get('tile_path_pattern')}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error testing nightlight processing: {e}")
        logger.error(traceback.format_exc())
        return False

def test_with_dummy_text_file():
    """Test processing with a dummy text file instead of a real GeoTIFF"""
    logger.info("Starting dummy text file test...")
    
    try:
        # Create a temporary directory
        tmp_dir = tempfile.mkdtemp()
        logger.debug(f"Created temporary directory: {tmp_dir}")
        
        # Create a dummy text file
        dummy_file_path = os.path.join(tmp_dir, "dummy_raster.tif")
        with open(dummy_file_path, 'w') as f:
            f.write("DUMMY DATA FOR AREA 999, 2024-01")
        
        logger.info(f"Created dummy text file at: {dummy_file_path}")
        
        # Test area ID and date
        area_id = 999
        month_date = datetime(2024, 1, 1).date()
        
        # First create a test area in the database
        from utils.db import get_db, Area
        from geoalchemy2 import Geometry
        from sqlalchemy import func
        import json
        
        # Test geometry
        test_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [35.0, -1.0],
                    [35.5, -1.0],
                    [35.5, -0.5],
                    [35.0, -0.5],
                    [35.0, -1.0]
                ]
            ]
        }
        
        # Connect to the database
        logger.info("Creating test area in database...")
        db = next(get_db())
        
        try:
            # Check if test area already exists
            existing_area = db.query(Area).filter(Area.area_id == area_id).first()
            
            if existing_area:
                logger.info(f"Test area with ID {area_id} already exists, using it")
            else:
                # Create a test area
                geom_wkt = f"SRID=4326;{json.dumps(test_geom)}"
                area = Area(
                    area_id=area_id,
                    name=f"Test Area {area_id}",
                    geom=func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(test_geom)), 4326),
                    meta_data={
                        "test": True,
                        "created_at": datetime.now().isoformat()
                    }
                )
                db.add(area)
                db.commit()
                logger.info(f"Created test area with ID {area_id}")
        except Exception as db_error:
            logger.error(f"Error creating test area: {db_error}")
            db.rollback()
            raise
        finally:
            db.close()
        
        # Process the dummy file
        logger.info(f"Processing dummy file for area ID {area_id}, month {month_date}...")
        results = process_nightlight_raster(
            area_id=area_id,
            month_date=month_date,
            raster_path=dummy_file_path
        )
        
        logger.success(f"Successfully processed dummy file. Results:")
        logger.info(f"Mean brightness: {results.get('mean_brightness')}")
        logger.info(f"Median brightness: {results.get('median_brightness')}")
        logger.info(f"Lit pixel count: {results.get('lit_pixel_count')}")
        logger.info(f"Tile path pattern: {results.get('tile_path_pattern')}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error testing with dummy text file: {e}")
        logger.error(traceback.format_exc())
        return False

def run_all_tests():
    """Run all tests to validate fixes"""
    logger.info("\n=== Running Earth Engine Export Test ===")
    ee_result = test_earth_engine_export()
    logger.info(f"Earth Engine Export Test: {'PASSED' if ee_result else 'FAILED'}")
    
    if ee_result:
        logger.info("\n=== Running Nightlight Processing Test with EE Result ===")
        processing_result = test_nightlight_processing(ee_result)
        logger.info(f"Nightlight Processing Test (EE): {'PASSED' if processing_result else 'FAILED'}")
    
    logger.info("\n=== Running Nightlight Processing Test with Test Raster ===")
    processing_result2 = test_nightlight_processing()
    logger.info(f"Nightlight Processing Test (Test Raster): {'PASSED' if processing_result2 else 'FAILED'}")
    
    logger.info("\n=== Running Dummy Text File Test ===")
    dummy_result = test_with_dummy_text_file()
    logger.info(f"Dummy Text File Test: {'PASSED' if dummy_result else 'FAILED'}")

if __name__ == "__main__":
    try:
        # Initialize storage
        logger.info("Initializing storage...")
        try:
            initialize_buckets()
            logger.success("Storage initialized successfully")
        except Exception as e:
            logger.warning(f"Storage initialization failed, but continuing with tests: {e}")
        
        # Run tests
        run_all_tests()
        
        logger.info("All tests completed!")
        
    except Exception as e:
        logger.error(f"Error in test script: {e}")
        logger.error(traceback.format_exc()) 