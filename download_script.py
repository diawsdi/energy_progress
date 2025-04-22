from utils.storage import download_file, MINIO_BUCKET_RASTERS
download_file('999/2024_01/viirs_ntl.tif', '/tmp/kenya_test.tif', MINIO_BUCKET_RASTERS)
print("File downloaded to /tmp/kenya_test.tif")
