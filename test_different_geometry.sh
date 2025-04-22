#!/bin/bash

# Check if containers are already running
if ! docker compose ps --services energy_progress_api | grep -q energy_progress_api; then
  # Start the Docker containers only if they're not already running
  echo "Starting Docker containers..."
  docker compose up -d
else
  echo "Containers are already running, skipping startup..."
fi

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 5

# Copy test script to the ETL container
echo "Copying test script to ETL container..."
docker compose cp test_different_geometry.py energy_progress_etl:/app/

# Run the test script in the ETL container
echo "Running test with different geometry (Kenya)..."
RESULT=$(docker compose exec energy_progress_etl python /app/test_different_geometry.py)
echo "$RESULT"

# Extract the path from result
RASTER_PATH=$(echo "$RESULT" | grep "Successfully exported test data" | sed -E 's/.*: (.+)$/\1/')

if [ -z "$RASTER_PATH" ]; then
  echo "Failed to extract raster path from output. Exiting."
  exit 1
fi

# Extract object name
OBJECT_NAME=$(echo "$RASTER_PATH" | sed -E 's/energy_progress_rasters\/(.+)$/\1/')
BUCKET_NAME="rasters"

echo "Exported raster path: $RASTER_PATH"
echo "Object name: $OBJECT_NAME"

# Create a Python script to download the file
cat > download_script.py << EOF
from utils.storage import download_file, MINIO_BUCKET_RASTERS
download_file('$OBJECT_NAME', '/tmp/kenya_test.tif', MINIO_BUCKET_RASTERS)
print("File downloaded to /tmp/kenya_test.tif")
EOF

# Run the download script in the ETL container
echo "Downloading raster file from MinIO..."
docker compose exec energy_progress_etl python -c "
from utils.storage import download_file, MINIO_BUCKET_RASTERS
download_file('$OBJECT_NAME', '/tmp/kenya_test.tif', MINIO_BUCKET_RASTERS)
print('File downloaded to /tmp/kenya_test.tif')
"

# Copy the file from container to host
echo "Copying file from container to host..."
docker compose cp energy_progress_etl:/tmp/kenya_test.tif ./kenya_test.tif

# Check file info
echo "Checking raster file information..."
gdalinfo kenya_test.tif

echo "Test complete! Compare the bounding box of this file with the Tamba file."
echo "Kenya test raster bounds are shown above." 