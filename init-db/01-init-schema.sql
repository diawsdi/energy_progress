-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Registered areas of interest
CREATE TABLE areas (
  area_id   SERIAL PRIMARY KEY,
  name      TEXT UNIQUE NOT NULL,
  geom      GEOMETRY(Polygon, 4326) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  meta_data  JSONB -- Other relevant info
);
CREATE INDEX areas_geom_idx ON areas USING GIST (geom);

-- Monthly nightlight-derived metrics per area
CREATE TABLE area_timeseries (
  area_id           INT REFERENCES areas(area_id) ON DELETE CASCADE,
  month             DATE NOT NULL,
  mean_brightness   DOUBLE PRECISION,
  median_brightness DOUBLE PRECISION,
  sum_brightness    DOUBLE PRECISION,
  lit_pixel_count   INT,
  lit_percentage    DOUBLE PRECISION,
  tile_path_pattern TEXT, -- Pattern like 'energy_progress_tiles/area_id/YYYY_MM/{z}/{x}/{y}.png'
  raster_path       TEXT, -- Path to original raster
  min_zoom          INT,  -- Minimum zoom level for tiles
  max_zoom          INT,  -- Maximum zoom level for tiles
  bounding_box      JSONB, -- Tile bounding box [minx, miny, maxx, maxy]
  meta_data          JSONB, -- Additional metadata (processing info, etc)
  PRIMARY KEY (area_id, month)
);
CREATE INDEX area_timeseries_month_idx ON area_timeseries (month);

-- Processing history and status tracking
CREATE TABLE processing_jobs (
  job_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  area_id           INT REFERENCES areas(area_id) ON DELETE CASCADE,
  job_type          TEXT NOT NULL, -- 'earth_engine_export', 'etl_processing', etc.
  status            TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed'
  start_date        DATE,
  end_date          DATE,
  created_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  error_message     TEXT,
  meta_data          JSONB -- Additional job metadata
);
CREATE INDEX processing_jobs_area_id_idx ON processing_jobs (area_id);
CREATE INDEX processing_jobs_status_idx ON processing_jobs (status);

-- Notification function for updated_at trigger
CREATE OR REPLACE FUNCTION update_modified_column() 
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW; 
END;
$$ LANGUAGE 'plpgsql';

-- Apply the update_modified_column trigger to processing_jobs
CREATE TRIGGER update_processing_jobs_modtime
BEFORE UPDATE ON processing_jobs
FOR EACH ROW
EXECUTE FUNCTION update_modified_column(); 