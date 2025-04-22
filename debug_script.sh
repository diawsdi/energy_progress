#!/bin/bash

# Extract the geometry from the village.geojson file
GEOMETRY=$(cat village.geojson | jq '.features[0].geometry')

# Create an area with a unique name to avoid conflict with existing areas
echo "Creating area..."
AREA_RESPONSE=$(curl -s -X POST "http://localhost:8009/areas/" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Debug Village $(date +%s)\",
    \"geometry\": $GEOMETRY,
    \"meta_data\": {
      \"country\": \"Example Country\",
      \"region\": \"Example Region\"
    }
  }")

echo "Raw area response:"
echo "$AREA_RESPONSE"
echo

# Extract the area_id with debug output
echo "Using jq to extract area_id..."
echo "$AREA_RESPONSE" | jq '.area_id'
AREA_ID=$(echo "$AREA_RESPONSE" | jq -r '.area_id')
echo "Area ID extracted: '$AREA_ID'"

# Create an Earth Engine export job for the area
echo "Creating Earth Engine export job..."
JOB_RESPONSE=$(curl -s -X POST "http://localhost:8009/earth-engine/export/" \
  -H "Content-Type: application/json" \
  -d "{
    \"area_id\": $AREA_ID,
    \"start_date\": \"2024-01-01\",
    \"end_date\": \"2024-03-31\"
  }")

echo "Raw job response:"
echo "$JOB_RESPONSE"
echo

# Extract the job_id with debug output
echo "Using jq to extract job_id..."
echo "$JOB_RESPONSE" | jq '.job_id'
JOB_ID=$(echo "$JOB_RESPONSE" | jq -r '.job_id')
echo "Job ID extracted: '$JOB_ID'" 