import os
import tempfile
import subprocess
import json
from datetime import datetime
import rasterio
from rasterio.mask import mask
from rasterstats import zonal_stats
import shapely.geometry
import numpy as np
from loguru import logger
import shutil
from geoalchemy2.shape import to_shape

from utils.db import get_db, Area, AreaTimeseries, ProcessingJob
from utils.storage import upload_file, download_file, MINIO_BUCKET_TILES, MINIO_BUCKET_RASTERS

def process_nightlight_raster(area_id, month_date, raster_path, threshold=1.0):
    """
    Process a night light raster for a specific area and month.
    
    Args:
        area_id (int): ID of the area to process
        month_date (datetime.date): Month to process
        raster_path (str): Path to the raster file
        threshold (float): Brightness threshold for considering a pixel as "lit"
        
    Returns:
        dict: Processing results with computed metrics
    """
    logger.info(f"Processing night light raster for area {area_id}, month {month_date}")
    
    # Create a temporary directory for processing
    tmp_dir = tempfile.mkdtemp()
    
    # Initialize variables needed in all code paths
    valid_pixels = np.array([])
    band_data = None
    masked_raster_path = None
    tiles_dir = None
    bounding_box = None
    min_zoom = 8
    max_zoom = 14
    
    try:
        # Get the area geometry from the database
        db = next(get_db())
        area = db.query(Area).filter(Area.area_id == area_id).first()
        if not area:
            raise ValueError(f"Area with ID {area_id} not found")
        
        # Convert area geometry to GeoJSON format for masking
        geom = to_shape(area.geom)
        geom_json = [shapely.geometry.mapping(geom)]
        
        # Download the raster if it's a MinIO path
        local_raster_path = raster_path
        if raster_path.startswith(f"{MINIO_BUCKET_RASTERS}/") or raster_path.startswith("rasters/"):
            # Clean up the path to get just the object name
            object_name = raster_path.replace(f"{MINIO_BUCKET_RASTERS}/", "")
            object_name = object_name.replace("rasters/", "")
            
            # Create local path for the downloaded file
            local_raster_path = os.path.join(tmp_dir, f"raster_{area_id}_{month_date.strftime('%Y_%m')}.tif")
            
            # Download the file
            logger.info(f"Downloading raster {object_name} from MinIO to {local_raster_path}")
            download_file(object_name, local_raster_path, MINIO_BUCKET_RASTERS)
            
            # Check if the downloaded file is a valid raster
            try:
                # Try opening with rasterio first to check if it's a valid GeoTIFF
                with rasterio.open(local_raster_path) as src:
                    # If we can open it, it's a valid GeoTIFF
                    pass
            except rasterio.errors.RasterioIOError:
                # Not a valid GeoTIFF, check if it's a dummy text file
                try:
                    # Read as binary first, then check content without assuming UTF-8
                    with open(local_raster_path, 'rb') as f:
                        content = f.read(100)  # Read first 100 bytes to check
                        # Try to decode as UTF-8 only if it looks like text
                        if b"DUMMY DATA FOR AREA" in content or b"This is development mode" in content:
                            # This is a dummy file, not a real raster
                            logger.warning(f"File is a dummy placeholder, not a real GeoTIFF")
                            logger.warning("Creating a simple test raster instead")
                            
                            # Create a simple test raster with some brightness values
                            from rasterio.transform import from_bounds
                            
                            # Create a 10x10 array with random brightness values
                            data = np.random.rand(1, 10, 10) * 10  # Values between 0-10
                            
                            # Get the bounding box from the geometry
                            minx, miny, maxx, maxy = shapely.geometry.box(*geom.bounds).bounds
                            
                            # Create a transform
                            transform = from_bounds(minx, miny, maxx, maxy, 10, 10)
                            
                            # Create a new metadata dictionary
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
                            
                            # Write the test raster
                            test_raster_path = os.path.join(tmp_dir, f"test_raster_{area_id}.tif")
                            with rasterio.open(test_raster_path, 'w', **meta) as dst:
                                dst.write(data.astype('float32'))
                            
                            # Use this test raster instead
                            local_raster_path = test_raster_path
                except Exception as inner_e:
                    logger.error(f"Error checking binary content of file: {inner_e}")
                    # Create a dummy array for stats calculation when file check fails
                    valid_pixels = np.array([0.1, 0.2, 0.3])  # Some dummy values
                    # Create a dummy bounding box
                    bounding_box = {
                        "minx": geom.bounds[0],
                        "miny": geom.bounds[1],
                        "maxx": geom.bounds[2],
                        "maxy": geom.bounds[3]
                    }
                    # Skip the rest of the raster processing
                    raise ValueError(f"Invalid raster file: {inner_e}")
            except Exception as e:
                logger.error(f"Error checking raster file: {e}")
                # Create a dummy array for stats calculation when file check fails
                valid_pixels = np.array([0.1, 0.2, 0.3])  # Some dummy values
                # Create a dummy bounding box
                bounding_box = {
                    "minx": geom.bounds[0],
                    "miny": geom.bounds[1],
                    "maxx": geom.bounds[2],
                    "maxy": geom.bounds[3]
                }
                # Skip the rest of the raster processing
                raise ValueError(f"Invalid raster file: {e}")
        
        # Open the raster file
        with rasterio.open(local_raster_path) as src:
            # Mask the raster with the area geometry
            masked_data, masked_transform = mask(src, geom_json, crop=True, all_touched=True, nodata=0)
            masked_meta = src.meta.copy()
            
            # Update metadata
            masked_meta.update({
                "driver": "GTiff",
                "height": masked_data.shape[1],
                "width": masked_data.shape[2],
                "transform": masked_transform,
                "nodata": 0
            })
            
            # Save masked raster to temporary file
            masked_raster_path = os.path.join(tmp_dir, f"masked_{area_id}_{month_date.strftime('%Y_%m')}.tif")
            with rasterio.open(masked_raster_path, 'w', **masked_meta) as dest:
                dest.write(masked_data)
            
            # Calculate statistics
            # Extract the nightlight band data (assuming it's band 1)
            band_data = masked_data[0]
            
            # Calculate basic statistics
            valid_pixels = band_data[band_data > 0]  # Exclude NoData values
            
            # Get bounding box
            bounds = src.bounds
            bounding_box = {
                "minx": bounds.left,
                "miny": bounds.bottom,
                "maxx": bounds.right,
                "maxy": bounds.top
            }
            
            # Generate map tiles using gdal2tiles
            tiles_dir = os.path.join(tmp_dir, "tiles")
            os.makedirs(tiles_dir, exist_ok=True)
            
            # Generate tiles for zoom levels 8-14
            min_zoom = 8
            max_zoom = 14
            
            # First convert the raster to 8-bit, which is required by gdal2tiles
            eight_bit_raster_path = os.path.join(tmp_dir, f"8bit_{area_id}_{month_date.strftime('%Y_%m')}.tif")
            try:
                # Create an 8-bit version of the masked raster (required by gdal2tiles)
                logger.info(f"Converting masked raster to 8-bit for gdal2tiles compatibility")
                
                # Use GDAL translate to convert to 8-bit
                translate_cmd = [
                    "gdal_translate",
                    "-ot", "Byte",  # Output type: 8-bit
                    "-scale",  # Scale values to 0-255 range
                    masked_raster_path,
                    eight_bit_raster_path
                ]
                
                logger.info(f"Running command: {' '.join(translate_cmd)}")
                translate_result = subprocess.run(translate_cmd, check=True, capture_output=True, text=True)
                logger.info(f"gdal_translate command completed with return code {translate_result.returncode}")
                
                if os.path.exists(eight_bit_raster_path) and os.path.getsize(eight_bit_raster_path) > 0:
                    logger.info(f"Successfully created 8-bit raster at {eight_bit_raster_path}")
                else:
                    logger.warning(f"8-bit raster file doesn't exist or is empty, falling back to original raster")
                    eight_bit_raster_path = masked_raster_path
            except subprocess.CalledProcessError as e:
                logger.error(f"gdal_translate command failed with return code {e.returncode}")
                if e.stdout:
                    logger.error(f"gdal_translate stdout: {e.stdout[:500]}...")
                if e.stderr:
                    logger.error(f"gdal_translate stderr: {e.stderr[:500]}...")
                logger.warning(f"Using original raster instead of 8-bit conversion")
                eight_bit_raster_path = masked_raster_path
            except Exception as e:
                logger.error(f"Error converting raster to 8-bit: {e}")
                logger.warning(f"Using original raster instead of 8-bit conversion")
                eight_bit_raster_path = masked_raster_path
            
            logger.info(f"Generating tiles for zoom levels {min_zoom}-{max_zoom}")
            cmd = [
                "gdal2tiles.py",
                "--zoom", f"{min_zoom}-{max_zoom}",
                "--webviewer", "none",
                "--resampling", "average",
                "--processes", "4",
                eight_bit_raster_path,  # Use the 8-bit raster instead of the original
                tiles_dir
            ]
            try:
                logger.info(f"Running command: {' '.join(cmd)}")
                process = subprocess.run(cmd, check=True, capture_output=True, text=True)
                logger.info(f"gdal2tiles.py command completed with return code {process.returncode}")
                if process.stdout:
                    logger.debug(f"gdal2tiles.py stdout: {process.stdout[:500]}...")
            except subprocess.CalledProcessError as e:
                logger.error(f"gdal2tiles.py command failed with return code {e.returncode}")
                if e.stdout:
                    logger.error(f"gdal2tiles.py stdout: {e.stdout[:500]}...")
                if e.stderr:
                    logger.error(f"gdal2tiles.py stderr: {e.stderr[:500]}...")
                # Create empty tiles directory as fallback
                logger.warning("Creating empty tiles directory as fallback")
                os.makedirs(tiles_dir, exist_ok=True)
            
            # Check if tiles were actually generated
            tile_count = 0
            for root, dirs, files in os.walk(tiles_dir):
                png_files = [f for f in files if f.endswith('.png')]
                tile_count += len(png_files)
            
            logger.info(f"Found {tile_count} tile files in {tiles_dir}")
            if tile_count == 0:
                logger.warning("No tiles were generated, this might indicate a problem with gdal2tiles or the input raster")
            
            # Upload tiles to MinIO
            tiles_object_prefix = f"{area_id}/{month_date.strftime('%Y_%m')}"
            logger.info(f"Uploading tiles to MinIO with prefix: {tiles_object_prefix}")
            
            # Walk through the tiles directory and upload each file
            upload_count = 0
            for root, _, files in os.walk(tiles_dir):
                for file in files:
                    if file.endswith(".png"):
                        file_path = os.path.join(root, file)
                        # Determine the relative path for the MinIO object name
                        rel_path = os.path.relpath(file_path, tiles_dir)
                        object_name = f"{tiles_object_prefix}/{rel_path}"
                        
                        # Upload tile to MinIO
                        try:
                            logger.debug(f"Uploading tile {file_path} to {MINIO_BUCKET_TILES}/{object_name}")
                            result = upload_file(
                                file_path, 
                                object_name, 
                                bucket_name=MINIO_BUCKET_TILES,
                                content_type="image/png"
                            )
                            if result:
                                upload_count += 1
                            else:
                                logger.warning(f"Upload failed for tile {file_path}")
                        except Exception as upload_err:
                            logger.error(f"Error uploading tile {file_path}: {upload_err}")
            
            logger.info(f"Uploaded {upload_count} tiles to MinIO bucket {MINIO_BUCKET_TILES}")
            
            # Upload the masked raster to MinIO
            raster_object_name = f"{area_id}/{month_date.strftime('%Y_%m')}/masked.tif"
            logger.info(f"Uploading masked raster to MinIO: {MINIO_BUCKET_RASTERS}/{raster_object_name}")
            try:
                result = upload_file(
                    masked_raster_path,
                    raster_object_name,
                    bucket_name=MINIO_BUCKET_RASTERS,
                    content_type="image/tiff"
                )
                if result:
                    logger.info(f"Successfully uploaded masked raster to {MINIO_BUCKET_RASTERS}/{raster_object_name}")
                else:
                    logger.warning(f"Upload failed for masked raster {masked_raster_path}")
            except Exception as raster_upload_err:
                logger.error(f"Error uploading masked raster {masked_raster_path}: {raster_upload_err}")
            
            # Construct the tile path pattern
            tile_path_pattern = f"{MINIO_BUCKET_TILES}/{tiles_object_prefix}/{{z}}/{{x}}/{{y}}.png"
            logger.info(f"Tile path pattern: {tile_path_pattern}")
        
        # Stats must be calculated even if raster processing fails
        stats = {
            "mean_brightness": float(np.mean(valid_pixels)) if len(valid_pixels) > 0 else 0,
            "median_brightness": float(np.median(valid_pixels)) if len(valid_pixels) > 0 else 0,
            "sum_brightness": float(np.sum(valid_pixels)),
            "lit_pixel_count": int(np.sum(valid_pixels >= threshold)),
            "total_pixel_count": len(valid_pixels),
            "lit_percentage": float(np.sum(valid_pixels >= threshold) / len(valid_pixels) * 100) if len(valid_pixels) > 0 else 0
        }
        
        # Fallbacks for failed processing cases
        if not tiles_dir:
            tiles_dir = os.path.join(tmp_dir, "tiles")
            os.makedirs(tiles_dir, exist_ok=True)
            tiles_object_prefix = f"{area_id}/{month_date.strftime('%Y_%m')}"
            tile_path_pattern = f"{MINIO_BUCKET_TILES}/{tiles_object_prefix}/{{z}}/{{x}}/{{y}}.png"
        else:
            tiles_object_prefix = f"{area_id}/{month_date.strftime('%Y_%m')}"
            tile_path_pattern = f"{MINIO_BUCKET_TILES}/{tiles_object_prefix}/{{z}}/{{x}}/{{y}}.png"
        
        if not masked_raster_path:
            raster_object_name = f"{area_id}/{month_date.strftime('%Y_%m')}/dummy.tif"
        else:
            raster_object_name = f"{area_id}/{month_date.strftime('%Y_%m')}/masked.tif"
            
        # Prepare the result
        result = {
            **stats,
            "raster_path": f"{MINIO_BUCKET_RASTERS}/{raster_object_name}",
            "tile_path_pattern": tile_path_pattern,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "bounding_box": bounding_box or {"minx": 0, "miny": 0, "maxx": 0, "maxy": 0},
            "meta_data": {
                "processed_at": datetime.now().isoformat(),
                "threshold": threshold
            }
        }
        
        return result
            
    except Exception as e:
        logger.error(f"Error processing night light raster: {e}")
        
        # If we have a partial failure but have enough data to return stats,
        # try to return what we can
        if len(valid_pixels) > 0:
            stats = {
                "mean_brightness": float(np.mean(valid_pixels)) if len(valid_pixels) > 0 else 0,
                "median_brightness": float(np.median(valid_pixels)) if len(valid_pixels) > 0 else 0,
                "sum_brightness": float(np.sum(valid_pixels)),
                "lit_pixel_count": int(np.sum(valid_pixels >= threshold)),
                "total_pixel_count": len(valid_pixels),
                "lit_percentage": float(np.sum(valid_pixels >= threshold) / len(valid_pixels) * 100) if len(valid_pixels) > 0 else 0
            }
            
            result = {
                **stats,
                "raster_path": f"{MINIO_BUCKET_RASTERS}/{area_id}/{month_date.strftime('%Y_%m')}/error.tif",
                "tile_path_pattern": f"{MINIO_BUCKET_TILES}/{area_id}/{month_date.strftime('%Y_%m')}/{{z}}/{{x}}/{{y}}.png",
                "min_zoom": min_zoom,
                "max_zoom": max_zoom, 
                "bounding_box": bounding_box or {"minx": 0, "miny": 0, "maxx": 0, "maxy": 0},
                "meta_data": {
                    "processed_at": datetime.now().isoformat(),
                    "threshold": threshold,
                    "error": str(e)
                }
            }
            return result
        else:
            # Return minimal error result when no valid pixels are available
            result = {
                "mean_brightness": 0,
                "median_brightness": 0,
                "sum_brightness": 0,
                "lit_pixel_count": 0,
                "total_pixel_count": 0,
                "lit_percentage": 0,
                "raster_path": f"{MINIO_BUCKET_RASTERS}/{area_id}/{month_date.strftime('%Y_%m')}/error.tif",
                "tile_path_pattern": f"{MINIO_BUCKET_TILES}/{area_id}/{month_date.strftime('%Y_%m')}/{{z}}/{{x}}/{{y}}.png",
                "min_zoom": min_zoom,
                "max_zoom": max_zoom,
                "bounding_box": bounding_box or {"minx": 0, "miny": 0, "maxx": 0, "maxy": 0},
                "meta_data": {
                    "processed_at": datetime.now().isoformat(),
                    "threshold": threshold,
                    "error": str(e)
                }
            }
            return result
    finally:
        # Clean up temporary directory
        shutil.rmtree(tmp_dir)

def save_processing_results(area_id, month_date, results):
    """
    Save the processing results to the database.
    
    Args:
        area_id (int): ID of the area
        month_date (datetime.date): Month of the data
        results (dict): Processing results
        
    Returns:
        AreaTimeseries: The created or updated record
    """
    logger.info(f"Saving processing results for area {area_id}, month {month_date}")
    
    db = next(get_db())
    try:
        # Check if a record already exists
        timeseries = db.query(AreaTimeseries).filter(
            AreaTimeseries.area_id == area_id,
            AreaTimeseries.month == month_date
        ).first()
        
        if timeseries:
            # Update existing record
            for key, value in results.items():
                if hasattr(timeseries, key):
                    setattr(timeseries, key, value)
        else:
            # Create new record
            timeseries = AreaTimeseries(
                area_id=area_id,
                month=month_date,
                **{k: v for k, v in results.items() if k in [
                    'mean_brightness', 'median_brightness', 'sum_brightness',
                    'lit_pixel_count', 'lit_percentage', 'tile_path_pattern',
                    'raster_path', 'min_zoom', 'max_zoom', 'bounding_box', 'meta_data'
                ]}
            )
            db.add(timeseries)
            
        # Update or create a processing job record
        job = db.query(ProcessingJob).filter(
            ProcessingJob.area_id == area_id,
            ProcessingJob.job_type == 'etl_processing',
            ProcessingJob.start_date <= month_date,
            ProcessingJob.end_date >= month_date
        ).first()
        
        if not job:
            job = ProcessingJob(
                area_id=area_id,
                job_type='etl_processing',
                status='completed',
                start_date=month_date,
                end_date=month_date,
                meta_data={
                    'processing_details': results.get('meta_data', {})
                }
            )
            db.add(job)
        else:
            job.status = 'completed'
            job.meta_data = {
                **(job.meta_data or {}),
                'processing_details': results.get('meta_data', {})
            }
        
        db.commit()
        return timeseries
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving processing results: {e}")
        raise
    finally:
        db.close() 