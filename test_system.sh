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
sleep 10

# Extract the geometry from the dakar.geojson file
GEOMETRY=$(cat dakar.geojson | jq '.features[0].geometry')

# Create an area using the dakar.geojson data
echo "Creating area..."
AREA_RESPONSE=$(curl -s -X POST "http://localhost:8009/areas/" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Dakar Area $(date +%s)\",
    \"geometry\": $GEOMETRY,
    \"meta_data\": {
      \"country\": \"Senegal\",
      \"region\": \"Dakar Region\"
    }
  }")

# Extract the area_id from the response
AREA_ID=$(echo "$AREA_RESPONSE" | jq -r '.area_id')
echo "Created area with ID: $AREA_ID"

# Create an Earth Engine export job for the area
echo "Creating Earth Engine export job..."
JOB_RESPONSE=$(curl -s -X POST "http://localhost:8009/earth-engine/export/" \
  -H "Content-Type: application/json" \
  -d "{
    \"area_id\": $AREA_ID,
    \"start_date\": \"2024-01-01\",
    \"end_date\": \"2024-03-31\"
  }")

# Extract the job_id from the response
JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.job_id')
echo "Created Earth Engine export job with ID: $JOB_ID"

# Check the job status
echo "Checking job status..."
curl -s -X GET "http://localhost:8009/jobs/?job_type=earth_engine_export" | jq .

echo "The ETL service will process the job in the background."
echo "You can check the job status using:"
echo "curl -X GET \"http://localhost:8009/jobs/?job_type=earth_engine_export\""
echo "And view the logs using:"
echo "docker compose logs -f energy_progress_etl"

echo "Once processing is complete, you can view the results using:"
echo "curl -X GET \"http://localhost:8009/areas/$AREA_ID/timeseries?start_date=2024-01-01&end_date=2024-03-31\""
