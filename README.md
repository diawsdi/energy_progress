# Energy Progress Monitoring System

An end-to-end system for monitoring electrification progress using nightlight data. This system allows stakeholders to see progress over time through automated analysis of NASA Black Marble VNP46A2 nightlight imagery.

## Architecture

The system follows the architecture outlined in `docs.txt` and consists of:

1. **Data Storage**:
   - PostgreSQL (with PostGIS) on port 5439 for metadata, geometries, and time series data
   - MinIO object storage on port 9009 for raster files and map tiles

2. **Backend Services**:
   - FastAPI service for API endpoints and data retrieval
   - ETL processing service for nightlight data analysis and tile generation

3. **Data Flow**:
   - Upload user-defined areas as GeoJSON polygons
   - Process NASA Black Marble nightlight data for the area
   - Generate statistics and map tiles
   - Store results in the database and MinIO

## Prerequisites

- Docker and Docker Compose
- Git

## Quick Start

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd energy_progress
   ```

2. Start the services:
   ```bash
   docker-compose up -d
   ```

3. Access the services:
   - FastAPI Swagger UI: http://localhost:8000/docs
   - MinIO Console: http://localhost:9010 (login with admin/minioadmin)
   - PostgreSQL: localhost:5439 (connect with your preferred database client)

## Usage

### Creating a New Area

```bash
curl -X POST "http://localhost:8000/areas/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Area",
    "geometry": {
      "type": "Polygon",
      "coordinates": [
        [
          [30.0, 10.0],
          [40.0, 40.0],
          [20.0, 40.0],
          [10.0, 20.0],
          [30.0, 10.0]
        ]
      ]
    },
    "metadata": {
      "country": "Example Country",
      "region": "Example Region"
    }
  }'
```

### Creating an Earth Engine Export Job

```bash
curl -X POST "http://localhost:8000/earth-engine/export/" \
  -H "Content-Type: application/json" \
  -d '{
    "area_id": 1,
    "start_date": "2023-01-01",
    "end_date": "2023-03-31"
  }'
```

This will automatically:
1. Fetch nightlight data from Google Earth Engine for the specified area and date range
2. Process the data to extract electrification metrics
3. Generate map tiles for visualization

### Viewing Area Timeseries Data

```bash
curl -X GET "http://localhost:8000/areas/1/timeseries?start_date=2020-01-01&end_date=2023-12-31"
```

### Processing Nightlight Data (ETL Service)

To manually run the ETL process:

```bash
docker-compose exec energy_progress_etl python -c "
from processors.nightlight import process_nightlight_raster, save_processing_results
from datetime import datetime
import tempfile

# Example: Process a local test file
results = process_nightlight_raster(
    area_id=1,
    month_date=datetime(2023, 1, 1).date(),
    raster_path='/path/to/test/raster.tif'
)
save_processing_results(1, datetime(2023, 1, 1).date(), results)
"
```

## Project Structure

```
energy_progress/
├── api/                  # FastAPI service
│   ├── main.py           # Main API application
│   ├── db.py             # Database models and connection
│   └── minio_client.py   # MinIO client
├── etl/                  # ETL processing service
│   ├── processors/       # Data processing modules
│   │   └── nightlight.py # Nightlight data processor
│   ├── utils/            # Utility modules
│   │   ├── db.py         # Database utilities
│   │   └── storage.py    # Storage utilities
│   └── scheduler.py      # Task scheduler
├── init-db/              # Database initialization scripts
│   └── 01-init-schema.sql # Schema creation script
├── docker-compose.yml    # Docker Compose configuration
└── docs.txt             # System architecture documentation
```

## Technologies Used

- **Backend**: Python, FastAPI, Celery
- **Database**: PostgreSQL, PostGIS
- **Storage**: MinIO (S3-compatible)
- **Containers**: Docker, Docker Compose
- **Geospatial**: GDAL, Rasterio, Shapely, GeoAlchemy2
- **Data Processing**: NumPy, Pandas

## License

This project is licensed under the MIT License - see the LICENSE file for details. # energy_progress
