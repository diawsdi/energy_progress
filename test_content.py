#!/usr/bin/env python3
"""
Test script to check the content of the files in MinIO.
"""

from utils.storage import download_file, MINIO_BUCKET_RASTERS
import os

area_id = 13
month_str = "2024_01"
object_name = f"{area_id}/{month_str}/viirs_ntl.tif"
local_path = f"/tmp/viirs_{area_id}_{month_str}.tif"

print(f"Downloading {object_name} from bucket {MINIO_BUCKET_RASTERS}")
download_file(object_name, local_path, MINIO_BUCKET_RASTERS)

print(f"File size: {os.path.getsize(local_path)} bytes")
print("File content:")
with open(local_path, 'r') as f:
    content = f.read()
    print(content) 