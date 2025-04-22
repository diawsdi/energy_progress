import os
import socket
from minio import Minio
from minio.error import S3Error
from loguru import logger
from urllib.parse import urlparse

# MinIO configuration from environment variables
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", f"http://localhost:{os.getenv('MINIO_PORT','9000')}")
MINIO_BUCKET_RASTERS = os.getenv("MINIO_BUCKET_RASTERS", "energy_progress_rasters")
MINIO_BUCKET_TILES = os.getenv("MINIO_BUCKET_TILES", "energy_progress_tiles")

# Map the environment variable bucket names to the safe bucket names
RASTERS_BUCKET_SAFE = "rasters"
TILES_BUCKET_SAFE = "tiles"

# Add endpoint URL parsing
MINIO_ENDPOINT_URL = os.getenv(
    "MINIO_ENDPOINT_URL",
    f"http://{os.getenv('MINIO_HOST','energy_progress_minio')}:{os.getenv('MINIO_PORT','9000')}"
)
parsed = urlparse(MINIO_ENDPOINT_URL)
hostname = parsed.hostname
port = parsed.port

# Try to resolve hostname to IP address if it's not already an IP
try:
    # Check if hostname is not already an IP address (simple check)
    if not all(part.isdigit() for part in hostname.split('.')):
        logger.info(f"Resolving hostname {hostname} to IP address...")
        hostname_ip = socket.gethostbyname(hostname)
        logger.info(f"Resolved {hostname} to IP address {hostname_ip}")
        ENDPOINT = f"{hostname_ip}:{port}"
    else:
        ENDPOINT = f"{hostname}:{port}"
except Exception as e:
    logger.warning(f"Error resolving hostname {hostname}: {e}. Using original hostname.")
    ENDPOINT = f"{hostname}:{port}"

SECURE = (parsed.scheme == "https")

logger.info(f"Connecting to MinIO at {ENDPOINT} (secure={SECURE})")

# Initialize MinIO client
minio_client = Minio(
    ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=SECURE
)

def get_presigned_url(bucket_name, object_name, expires=3600):
    """
    Generate a presigned URL for object download
    
    Args:
        bucket_name (str): MinIO bucket name
        object_name (str): Object name/path within the bucket
        expires (int): URL expiration time in seconds (default: 1 hour)
        
    Returns:
        str: Presigned URL for the object
    """
    # Map the environment variable bucket names to the safe bucket names
    if bucket_name == MINIO_BUCKET_RASTERS:
        bucket_name = RASTERS_BUCKET_SAFE
    elif bucket_name == MINIO_BUCKET_TILES:
        bucket_name = TILES_BUCKET_SAFE
    
    try:
        url = minio_client.presigned_get_object(bucket_name, object_name, expires=expires)
        return url
    except S3Error as e:
        logger.error(f"Error generating presigned URL: {e}")
        return None

def check_object_exists(bucket_name, object_name):
    """
    Check if an object exists in MinIO
    
    Args:
        bucket_name (str): MinIO bucket name
        object_name (str): Object name/path within the bucket
        
    Returns:
        bool: True if object exists, False otherwise
    """
    # Map the environment variable bucket names to the safe bucket names
    if bucket_name == MINIO_BUCKET_RASTERS:
        bucket_name = RASTERS_BUCKET_SAFE
    elif bucket_name == MINIO_BUCKET_TILES:
        bucket_name = TILES_BUCKET_SAFE
    
    try:
        minio_client.stat_object(bucket_name, object_name)
        return True
    except:
        return False

def list_objects(bucket_name, prefix="", recursive=True):
    """
    List objects in a MinIO bucket
    
    Args:
        bucket_name (str): MinIO bucket name
        prefix (str): Prefix to filter objects
        recursive (bool): Whether to recursively list objects in subdirectories
        
    Returns:
        list: List of object information dictionaries
    """
    # Map the environment variable bucket names to the safe bucket names
    if bucket_name == MINIO_BUCKET_RASTERS:
        bucket_name = RASTERS_BUCKET_SAFE
    elif bucket_name == MINIO_BUCKET_TILES:
        bucket_name = TILES_BUCKET_SAFE
    
    try:
        objects = minio_client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
        return [
            {
                "name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified
            }
            for obj in objects
        ]
    except S3Error as e:
        logger.error(f"Error listing objects: {e}")
        return [] 