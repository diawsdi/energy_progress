#!/usr/bin/env python3
"""
Script to create a single-color visualization of nightlight data with varying intensity.
Uses yellow color typical of nightlights with intensity based on brightness values.
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import json
import rasterio
from rasterio.mask import mask
from shapely.geometry import shape
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

# Input/output paths
input_file = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar.tif'
output_png = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar_yellow.png'
geojson_file = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar.geojson'

def create_single_color_visualization(raster_path, geojson_path, output_png, 
                                     base_color=(1.0, 0.9, 0.0), add_border=True,
                                     percentile_stretch=(2, 98)):
    """
    Create a visualization of the raster data with a single color and varying intensity.
    
    Args:
        raster_path: Path to the input raster file
        geojson_path: Path to the GeoJSON file containing the polygon
        output_png: Path for the output PNG file
        base_color: RGB tuple for the base color (default is yellow)
        add_border: Whether to add the polygon border to the visualization
        percentile_stretch: Data values to stretch between (as percentiles)
    """
    print(f"Reading raster: {raster_path}")
    print(f"Reading polygon: {geojson_path}")
    
    # Load the GeoJSON polygon
    with open(geojson_path, 'r') as f:
        geojson = json.load(f)
    
    # Extract the first feature's geometry
    if 'features' in geojson:
        geometry = geojson['features'][0]['geometry']
    else:
        geometry = geojson
        
    # Convert to a list of GeoJSON-like features
    geom = [geometry]
    
    # Create a shapely geometry for plotting
    shapely_geom = shape(geometry)
    
    # Open the raster
    with rasterio.open(raster_path) as src:
        # Get the raster's bounds and transform
        bounds = src.bounds
        transform = src.transform
        
        # Perform the masking operation - crop and mask by the polygon
        masked_data, masked_transform = mask(src, geom, crop=True, all_touched=False)
        masked_data = masked_data[0]  # Get the first band
        
        # Create a mask where data is valid
        valid_mask = masked_data > 0
        
        # Calculate statistics on valid data
        if np.any(valid_mask):
            data_valid = masked_data[valid_mask]
            data_min = data_valid.min()
            data_max = data_valid.max()
            
            # Get percentile values for better visualization
            min_val = np.percentile(data_valid, percentile_stretch[0])
            max_val = np.percentile(data_valid, percentile_stretch[1])
            
            print(f"Data statistics:")
            print(f"  - Actual range: {data_min:.6f} to {data_max:.6f}")
            print(f"  - Visualization range ({percentile_stretch[0]}% - {percentile_stretch[1]}%): {min_val:.6f} to {max_val:.6f}")
            
            # Normalize the data for colormap
            normalized_data = np.copy(masked_data)
            normalized_data = np.clip(normalized_data, min_val, max_val)
            normalized_data = (normalized_data - min_val) / (max_val - min_val)
            
            # Create a custom colormap that goes from transparent to the base color
            colors = [(0, 0, 0, 0)]  # Start with transparent
            for i in range(1, 256):
                # Scale the alpha from 0.1 (minimal visibility) to 1.0 (full intensity)
                alpha = 0.1 + 0.9 * (i / 255.0)
                colors.append((*base_color, alpha))
            
            # Create the custom colormap
            yellow_cmap = LinearSegmentedColormap.from_list("yellow_intensity", colors, N=256)
            
            # Create a matplotlib figure for high-quality output
            fig, ax = plt.subplots(figsize=(10, 10), facecolor='black')
            
            # Create a masked array with transparency for areas outside the polygon
            yellow_cmap.set_bad((0, 0, 0, 0))  # Set areas outside mask to transparent
            masked_array = np.ma.masked_array(normalized_data, mask=~valid_mask)
            
            # Plot the masked data with transparency
            img = ax.imshow(masked_array, cmap=yellow_cmap, interpolation='nearest')
            
            # Add a colorbar
            cbar = plt.colorbar(img, ax=ax)
            cbar.set_label('Brightness Intensity', color='white')
            cbar.ax.yaxis.set_tick_params(color='white')
            cbar.outline.set_edgecolor('white')
            plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='white')
            
            # Add polygon border if requested
            if add_border:
                # Convert polygon coordinates to pixel coordinates
                def world_to_pixel(lon, lat, transform):
                    """Convert world coordinates to pixel coordinates"""
                    row, col = ~transform * (lon, lat)
                    return col, row
                
                # Extract polygon exterior coordinates
                coords = list(shapely_geom.exterior.coords)
                
                # Convert to pixel coordinates
                pixel_coords = [world_to_pixel(x, y, masked_transform) for x, y in coords]
                
                # Create a patch for the polygon
                poly = mpatches.Polygon(pixel_coords, 
                                       fill=False, 
                                       edgecolor='white', 
                                       linewidth=2, 
                                       linestyle='--')
                ax.add_patch(poly)
            
            # Set title and remove axes
            ax.set_title("Nightlight Intensity in Dakar", color='white')
            ax.set_axis_off()
            
            # Save the figure with tight layout and transparency
            plt.tight_layout()
            plt.savefig(output_png, bbox_inches='tight', 
                       dpi=300, transparent=True, format='png',
                       facecolor='black')
            plt.close()
            
            print(f"Saved single-color visualization to: {output_png}")
        else:
            print("No valid data found within the polygon!")

if __name__ == "__main__":
    # Check if input files exist
    if not os.path.exists(input_file):
        print(f"Error: Input raster file {input_file} does not exist")
        sys.exit(1)
    
    if not os.path.exists(geojson_file):
        print(f"Error: GeoJSON file {geojson_file} does not exist")
        sys.exit(1)
    
    # Create the visualization
    create_single_color_visualization(input_file, geojson_file, output_png) 