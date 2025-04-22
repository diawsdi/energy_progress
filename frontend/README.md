# Nightlight Visualization Frontend

This is a simple web-based frontend for visualizing nightlight data over time. It shows satellite nightlight imagery for different areas with a time slider to see changes over months.

## Features

- Select different areas from dropdown
- View satellite nightlight imagery overlaid on a map
- Use the time slider to navigate between different months
- See brightness statistics for each area and time period

## Setup

1. Make sure the backend API is running (docker-compose up)
2. Start the frontend server:

```bash
# From the frontend directory
python server.py
```

3. Open your browser and navigate to: http://localhost:8080

## Requirements

- Python 3.6+
- Backend API running on http://localhost:8009

## How it works

The frontend connects to the backend API to:
1. Fetch a list of available areas
2. Get timeseries data for the selected area
3. Display map tiles using the tile URLs provided by the API
4. Show statistics for each time period

The visualization uses Leaflet.js for map display and standard JavaScript for UI interactions. 