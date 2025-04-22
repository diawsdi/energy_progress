# Energy Progress ETL Service Documentation

## Overview

The Energy Progress ETL service is designed to process nightlight satellite data for monitoring electrification progress in user-defined areas monthly based on user-defined time ranges. This system extracts data from satellite imagery, transforms it into meaningful electrification metrics, and loads the results into a database for analysis and visualization.

## Architecture Components

The system consists of the following key components:

1. **ETL Service**: Core processing engine that handles data transformation
2. **API Service**: FastAPI-based interface for client interactions
3. **PostgreSQL/PostGIS**: Database for storing area definitions and processing results
4. **MinIO**: Object storage for raster files and map tiles

## Data Flow

1. **Data Input**: 
   - NASA Black Marble VNP46A2 (BRDF-corrected nightly radiance) data
   - User-defined areas of interest (GeoJSON polygons)

2. **Processing Pipeline**:
   - Scheduler monitors for pending jobs
   - When jobs are found, raster data is downloaded from MinIO
   - Nightlight data is processed to extract electrification metrics
   - Results are saved to the database
   - Generated map tiles are uploaded to MinIO for visualization

3. **Output Data**:
   - Time series of electrification metrics in the database
   - Map tiles in MinIO for visual analysis

## Earth Engine Integration

The system now includes direct integration with Google Earth Engine for automated acquisition of NASA Black Marble VNP46A2 nightlight data:

1. **Data Acquisition**:
   - Users can create Earth Engine export jobs through the API
   - The system automatically fetches nightlight data for the specified area and time range
   - Data is downloaded directly from Earth Engine and stored in MinIO

2. **Processing Workflow**:
   - For each month in the requested time range, the system:
     - Creates a monthly composite of nightlight data
     - Clips the data to the area of interest
     - Downloads the data directly from Earth Engine
     - Uploads it to MinIO
     - Creates an ETL processing job to analyze the data

3. **API Endpoints**:
   - `/earth-engine/export/` - Create a new Earth Engine export job

4. **Job Types**:
   - `earth_engine_export` - Fetch data from Earth Engine
   - `etl_processing` - Process the downloaded data

This integration eliminates the need for manual data acquisition and provides a seamless workflow from data acquisition to visualization.

## System Configuration

### Environment Variables

The system uses the following environment variables:

#### Database Configuration
- `POSTGRES_HOST`: PostgreSQL host (default: `energy_progress_postgres`)
- `POSTGRES_PORT`: PostgreSQL port (default: `5432`)
- `POSTGRES_DB`: Database name (default: `energy_progress`)
- `POSTGRES_USER`: Database user (default: `energy_user`)
- `POSTGRES_PASSWORD`: Database password (default: `energy_password`)

#### MinIO Configuration
- `MINIO_HOST`: MinIO host (default: `energy_progress_minio`)
- `MINIO_PORT`: MinIO port (default: `9000`)
- `MINIO_ACCESS_KEY`: MinIO access key (default: `admin`)
- `MINIO_SECRET_KEY`: MinIO secret key (default: `minioadmin`)
- `MINIO_SECURE`: Use HTTPS for MinIO (default: `False`)
- `MINIO_BUCKET_RASTERS`: MinIO bucket for raster files (default: `energy_progress_rasters`)
- `MINIO_BUCKET_TILES`: MinIO bucket for map tiles (default: `energy_progress_tiles`)

## Running the System

### Using Docker Compose

The recommended way to run the system is using Docker Compose, which sets up all required components:

1. **Starting the entire system**:
   ```bash
   docker-compose up -d
   ```

2. **Starting specific components**:
   ```bash
   docker-compose up -d energy_progress_postgres energy_progress_minio energy_progress_api
   ```

3. **Restart a component**:
   ```bash
   docker-compose restart energy_progress_etl
   ```

4. **View logs**:
   ```bash
   docker-compose logs --tail=50 energy_progress_etl
   ```

### Checking Service Status

To check if services are running:
```bash
docker-compose ps
```

## ETL Scheduler

The ETL Scheduler is a critical component that:

1. Runs every 5 minutes to check for pending processing jobs
2. Processes raster data when jobs are available
3. Updates job status in the database

### Key Features

- **Delayed MinIO Initialization**: The system now delays MinIO bucket initialization until it's actually needed (when jobs are found). This allows the service to start even when MinIO is temporarily unavailable.
- **Error Handling**: Comprehensive error handling for job processing with state tracking in the database.
- **Scheduled Processing**: Automatically runs every 5 minutes to check for new jobs.

## Database Schema

Two main tables are used:

1. **Areas**: Stores user-defined areas of interest
   - `area_id`: Unique identifier
   - `name`: Human-readable name
   - `geom`: PostGIS geometry field for the polygon

2. **ProcessingJob**: Tracks ETL processing jobs
   - `job_id`: Unique identifier
   - `area_id`: Area to process
   - `job_type`: Type of job (e.g., "etl_processing")
   - `status`: Job status (pending, running, completed, failed)
   - `meta_data`: JSON field with job-specific parameters
   - `start_date`: Date the data represents
   - `created_at`: When the job was created
   - `error_message`: Error details if failed

## Development and Testing

### Setting Up Development Environment

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r etl/requirements.txt
   ```

### Running Tests

Tests can be run using:
```bash
# To be implemented based on testing framework
```

## Troubleshooting

### Common Issues

1. **MinIO Connection Errors**:
   - Check if MinIO service is running: `docker-compose ps energy_progress_minio`
   - Verify MinIO credentials in environment variables
   - Ensure MinIO buckets are correctly initialized
   
2. **Database Connection Issues**:
   - Check if PostgreSQL is running: `docker-compose ps energy_progress_postgres`
   - Verify database credentials and connection details
   
3. **ETL Processing Errors**:
   - Check the ETL service logs: `docker-compose logs energy_progress_etl`
   - Verify input data format and availability

## API Endpoints

The API service provides endpoints for:

1. Area management (create, update, delete areas of interest)
2. Job management (submit, check status)
3. Result retrieval (timeseries, statistics)
4. Map tile access for visualization

*Detailed API documentation will be available at http://localhost:8009/docs when the API service is running.* 

### PROJECT Flow:


# Area Processing Workflow with Component Interactions

## 1. Define the Area
- **Component**: API Service
- **Process**:
  - Client sends GeoJSON polygon to API service
  - API validates the geometry
  - API stores the area in PostgreSQL database
  - API returns the generated area_id to the client

## 2. Create a Processing Job
- **Component**: API Service
- **Process**:
  - Client sends job parameters to API service
  - API validates parameters and area_id
  - API creates a job record with "pending" status in PostgreSQL
  - API returns the job_id to the client

## 3. Job Processing
- **Component**: ETL Service (Scheduler)
- **Process**:
  - Scheduler runs every 5 minutes checking for pending jobs
  - When finding a job, it:
    - Updates job status to "running"
    - Initializes MinIO buckets (our improvement)
    - Downloads raster data from MinIO
    - Processes nightlight data using the processor modules
    - Calculates electrification metrics
    - Saves results to PostgreSQL
    - Generates map tiles and uploads to MinIO
    - Updates job status to "completed"

## 4. View Results
- **Component**: API Service
- **Process**:
  - Client requests timeseries data from API
  - API queries PostgreSQL for results
  - API formats and returns the data
  - For map visualization:
    - Client uses the tile URLs from API
    - Tiles are served directly from MinIO storage

## Error Handling
- **Component**: ETL Service
- **Process**:
  - If processing fails, ETL service:
    - Logs the error details
    - Updates job status to "failed"
    - Records error message in the job record
  - Client can check job status via API

The key improvement we made was in step 3, ensuring the ETL service can start reliably even when MinIO is unavailable, and only attempting to initialize MinIO buckets when actually processing jobs.
