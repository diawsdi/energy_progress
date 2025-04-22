#!/usr/bin/env python3
"""
Script to colorize nightlight raster data for better visualization.
Uses 'inferno' colormap which is ideal for representing brightness data.
"""

import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib import cm
import rasterio
from rasterio.plot import show
from rasterio.io import MemoryFile

# Input/output paths
input_file = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar.tif'
output_tif = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar_colorized.tif'
output_png = '/home/tolbi-cto/godlang/auroraai/backend/energy_progress/dakar_colorized.png'

def colorize_raster(input_file, output_tif, output_png, colormap='inferno', 
                   percentile_stretch=(2, 98), add_legend=True):
    """
    Colorize a raster file using a specified colormap.
    
    Args:
        input_file: Path to input raster
        output_tif: Path to save colorized GeoTIFF
        output_png: Path to save colorized PNG
        colormap: Matplotlib colormap to use
        percentile_stretch: Tuple of (min, max) percentiles to stretch data
        add_legend: Whether to add a colorbar legend to the PNG
    """
    print(f"Reading raster: {input_file}")
    
    # Open the input file
    with rasterio.open(input_file) as src:
        # Read the data and mask no-data values
        data = src.read(1)
        profile = src.profile
        
        # Calculate statistics
        data_valid = data[data > 0]  # Filter out no-data values
        if len(data_valid) == 0:
            print("No valid data found in raster")
            return
        
        # Get actual min/max
        data_min = data_valid.min()
        data_max = data_valid.max()
        
        # Get percentile-based min/max for better visualization
        min_val = np.percentile(data_valid, percentile_stretch[0])
        max_val = np.percentile(data_valid, percentile_stretch[1])
        
        print(f"Data statistics:")
        print(f"  - Actual range: {data_min:.6f} to {data_max:.6f}")
        print(f"  - Visualization range ({percentile_stretch[0]}% - {percentile_stretch[1]}%): {min_val:.6f} to {max_val:.6f}")
        
        # Normalize data for colormap
        normalized_data = np.copy(data)
        normalized_data = np.clip(normalized_data, min_val, max_val)
        normalized_data = (normalized_data - min_val) / (max_val - min_val)
        
        # Get colormap from matplotlib
        cmap = plt.get_cmap(colormap)
        
        # Apply colormap
        colored_data = cmap(normalized_data)
        
        # Convert to 8-bit RGBA
        colored_data_8bit = (colored_data * 255).astype(np.uint8)
        
        # Save as PNG with matplotlib for better visualization
        fig, ax = plt.subplots(figsize=(10, 10))
        img = ax.imshow(normalized_data, cmap=colormap)
        ax.set_title(f"Colorized Nightlight Data: {os.path.basename(input_file)}")
        
        if add_legend:
            cbar = plt.colorbar(img, ax=ax)
            cbar.set_label('Brightness')
        
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_png, dpi=300, bbox_inches='tight')
        print(f"Saved colorized PNG: {output_png}")
        plt.close()
        
        # Save as GeoTIFF with rasterio (maintaining geospatial metadata)
        profile.update(
            dtype=rasterio.uint8,
            count=4,
            nodata=None
        )
        
        with rasterio.open(output_tif, 'w', **profile) as dst:
            for i in range(4):  # Write each channel (R,G,B,A)
                dst.write(colored_data_8bit[:, :, i], i+1)
        
        print(f"Saved colorized GeoTIFF: {output_tif}")

if __name__ == "__main__":
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} does not exist")
        sys.exit(1)
    
    # Run the colorization
    colorize_raster(input_file, output_tif, output_png)
    
    print("Done! The colorized raster has been saved as both TIF and PNG.")
    print(f"TIF file (with geospatial data): {output_tif}")
    print(f"PNG file (for easy viewing): {output_png}") 