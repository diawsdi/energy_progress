#!/usr/bin/env python3
"""
Test script to verify that different geometries result in different raster extents.
"""

import os
import sys
import json
from datetime import datetime
import tempfile
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stdout, level="INFO")
logger.info("=== Testing Earth Engine Export with Different Geometry ===")

# Import our modules
from utils.earth_engine import export_for_area, initialize_earth_engine

# Define a completely different test geometry (Kenya area, far from Tamba)
test_geom = {
    "type": "Polygon",
    "coordinates": [
        [
            [36.8, -1.3],
            [36.9, -1.3],
            [36.9, -1.2],
            [36.8, -1.2],
            [36.8, -1.3]
        ]
    ]
}

def test_with_different_geometry():
    """Test Earth Engine export with a different geometry"""
    try:
        area_id = 999  # Test area ID
        year = 2024
        month = 1
        
        # Initialize Earth Engine
        if not initialize_earth_engine():
            logger.error("Failed to initialize Earth Engine")
            return False
        
        # Export data for this area
        logger.info(f"Exporting nightlight data for test area (Kenya) for {year}-{month:02d}")
        raster_path = export_for_area(
            area_id=area_id,
            geom=test_geom,
            year=year,
            month=month
        )
        
        logger.info(f"Successfully exported test data to: {raster_path}")
        logger.info("To verify, download this file from MinIO and check its bounding box")
        return raster_path
    
    except Exception as e:
        logger.error(f"Error testing Earth Engine export: {e}")
        return False

if __name__ == "__main__":
    test_with_different_geometry() 