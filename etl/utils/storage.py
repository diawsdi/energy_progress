import os
import time
import socket
import json
from minio import Minio
from minio.error import S3Error, MinioException
from loguru import logger
from urllib.parse import urlparse

# MinIO configuration from environment variables
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_RASTERS = os.getenv("MINIO_BUCKET_RASTERS", "energy_progress_rasters")
MINIO_BUCKET_TILES = os.getenv("MINIO_BUCKET_TILES", "energy_progress_tiles")

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

logger.info(f"Configuring MinIO at {ENDPOINT} (secure={SECURE})")

# Initialize MinIO client function to call when needed
def get_minio_client(max_retries=3, retry_delay=2):
    """
    Create and return a MinIO client with retry logic
    
    Args:
        max_retries (int): Maximum number of connection attempts
        retry_delay (int): Delay between retries in seconds
        
    Returns:
        Minio: Configured MinIO client
    """
    # Update log message
    logger.info(f"Creating MinIO client at {ENDPOINT} (secure={SECURE})")
    
    client = Minio(
        ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=SECURE
    )
    
    # Verify connection with retry logic
    for attempt in range(max_retries):
        try:
            # Try a simple operation to verify connection
            # List buckets is a lightweight operation to test connectivity
            client.list_buckets()
            logger.info(f"Successfully connected to MinIO at {ENDPOINT}")
            return client
        except (S3Error, MinioException, Exception) as e:
            logger.warning(f"MinIO connection attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Failed to connect to MinIO after {max_retries} attempts")
                # Still return the client - operations will be attempted when used
                return client

def initialize_buckets():
    """Initialize buckets with proper policies."""
    try:
        client = get_minio_client()
        
        # Use simpler bucket names without underscores or other special characters
        rasters_bucket_safe = "rasters"
        tiles_bucket_safe = "tiles"
        
        # Map from environment variable names to actual bucket names
        bucket_map = {
            MINIO_BUCKET_RASTERS: rasters_bucket_safe,
            MINIO_BUCKET_TILES: tiles_bucket_safe
        }
        
        logger.info(f"Bucket mapping: environment variables to actual bucket names")
        for env_name, actual_name in bucket_map.items():
            logger.info(f"  {env_name} -> {actual_name}")
        
        # Verify buckets exist and create them if they don't
        buckets = []
        try:
            buckets = [bucket.name for bucket in client.list_buckets()]
            logger.info(f"Available buckets: {buckets}")
        except Exception as e:
            logger.error(f"Error listing buckets: {e}")
        
        # Create rasters bucket if it doesn't exist
        if rasters_bucket_safe not in buckets:
            logger.warning(f"Bucket {rasters_bucket_safe} does not exist. Creating it...")
            try:
                client.make_bucket(rasters_bucket_safe)
                logger.info(f"Created bucket {rasters_bucket_safe}")
            except Exception as e:
                logger.error(f"Error creating rasters bucket: {e}")
        else:
            logger.info(f"Bucket {rasters_bucket_safe} already exists")
        
        # Create tiles bucket if it doesn't exist
        if tiles_bucket_safe not in buckets:
            logger.warning(f"Bucket {tiles_bucket_safe} does not exist. Creating it...")
            try:
                client.make_bucket(tiles_bucket_safe)
                logger.info(f"Created bucket {tiles_bucket_safe}")
            except Exception as e:
                logger.error(f"Error creating tiles bucket: {e}")
        else:
            logger.info(f"Bucket {tiles_bucket_safe} already exists")
        
        # Set public download policy for tiles bucket
        policy_dict = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{tiles_bucket_safe}/*"]
                }
            ]
        }
        policy_str = json.dumps(policy_dict)
        
        try:
            client.set_bucket_policy(tiles_bucket_safe, policy_str)
            logger.info(f"Set public download policy for bucket {tiles_bucket_safe}")
        except Exception as e:
            logger.error(f"Error setting policy on tiles bucket: {e}")
        
        # Refresh bucket list to confirm buckets were created
        try:
            updated_buckets = [bucket.name for bucket in client.list_buckets()]
            logger.info(f"Updated bucket list: {updated_buckets}")
            
            if rasters_bucket_safe not in updated_buckets or tiles_bucket_safe not in updated_buckets:
                logger.warning("One or more required buckets still do not exist after attempts to create them")
                return False
        except Exception as e:
            logger.error(f"Error listing buckets after creation: {e}")
        
        return True
            
    except Exception as e:
        logger.error(f"Unexpected error initializing buckets: {e}")
        # Don't raise the exception, just return False
        return False

def upload_file(local_path, object_name, bucket_name=None, content_type=None, max_retries=3):
    """
    Upload a file to MinIO.
    
    Args:
        local_path (str): Path to the file on the local filesystem
        object_name (str): Name to save the object as in MinIO
        bucket_name (str, optional): Bucket to upload to. Defaults to rasters bucket.
        content_type (str, optional): Content type of the file
        max_retries (int): Maximum number of upload attempts
        
    Returns:
        str: Full path to the uploaded object or None if upload failed
    """
    # Fix the mapping of bucket environment variables to actual bucket names
    if bucket_name is None or bucket_name == MINIO_BUCKET_RASTERS:
        actual_bucket_name = "rasters"
        env_bucket_name = MINIO_BUCKET_RASTERS
    elif bucket_name == MINIO_BUCKET_TILES:
        actual_bucket_name = "tiles"
        env_bucket_name = MINIO_BUCKET_TILES
    else:
        actual_bucket_name = bucket_name.lstrip('/')
        env_bucket_name = bucket_name
    
    logger.debug(f"Uploading {local_path} to bucket '{actual_bucket_name}' (env var: {env_bucket_name}) as {object_name}")
    
    # Verify the file exists before attempting upload
    if not os.path.exists(local_path):
        logger.error(f"Cannot upload file {local_path} because it does not exist")
        return None
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            client = get_minio_client()
            # Ensure the bucket exists by checking the list of buckets
            buckets = [bucket.name for bucket in client.list_buckets()]
            logger.debug(f"Available buckets: {buckets}")
            
            if actual_bucket_name not in buckets:
                logger.warning(f"Bucket {actual_bucket_name} does not exist. Creating it...")
                client.make_bucket(actual_bucket_name)
                logger.info(f"Created bucket {actual_bucket_name}")
                
                # If this is the tiles bucket, set a public policy
                if actual_bucket_name == "tiles":
                    policy_dict = {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": {"AWS": ["*"]},
                                "Action": ["s3:GetObject"],
                                "Resource": [f"arn:aws:s3:::{actual_bucket_name}/*"]
                            }
                        ]
                    }
                    # Convert the policy dictionary to a JSON string
                    policy_str = json.dumps(policy_dict)
                    try:
                        client.set_bucket_policy(actual_bucket_name, policy_str)
                        logger.info(f"Set public download policy for bucket {actual_bucket_name}")
                    except Exception as e:
                        logger.error(f"Error setting policy on tiles bucket: {e}")
            
            # Check file size for large uploads
            file_size = os.path.getsize(local_path)
            logger.debug(f"Uploading file of size {file_size} bytes")
            
            # Upload file
            result = client.fput_object(
                actual_bucket_name, object_name, local_path, content_type=content_type
            )
            
            logger.info(f"Successfully uploaded {local_path} to MinIO bucket {actual_bucket_name} as {object_name}")
            
            # Verify the upload by attempting to stat the object
            try:
                client.stat_object(actual_bucket_name, object_name)
                logger.debug(f"Verified that {object_name} exists in bucket {actual_bucket_name}")
                return f"{env_bucket_name}/{object_name}"
            except Exception as stat_err:
                logger.warning(f"File was uploaded but verification failed: {stat_err}")
                # Return path anyway as the upload seemed to work
                return f"{env_bucket_name}/{object_name}"
            
        except Exception as e:
            last_exception = e
            logger.warning(f"Upload attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {2 ** attempt} seconds...")
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # If we get here, all retries failed
    logger.error(f"Error uploading file to MinIO after {max_retries} attempts: {last_exception}")
    return None  # Return None instead of raising an exception to allow the process to continue

def download_file(object_name, local_path, bucket_name=None, max_retries=3):
    """
    Download a file from MinIO.
    
    Args:
        object_name (str): Name of the object in MinIO
        local_path (str): Path to save the file on the local filesystem
        bucket_name (str, optional): Bucket to download from. Defaults to rasters bucket.
        max_retries (int): Maximum number of download attempts
        
    Returns:
        str: Local path to the downloaded file or None if download failed
    """
    # Map the environment variable bucket names to the actual bucket names
    if bucket_name is None or bucket_name == MINIO_BUCKET_RASTERS:
        actual_bucket_name = "rasters"
    elif bucket_name == MINIO_BUCKET_TILES:
        actual_bucket_name = "tiles"
    else:
        actual_bucket_name = bucket_name.lstrip('/')
    
    logger.debug(f"Downloading {actual_bucket_name}/{object_name} to {local_path}")
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            client = get_minio_client()
            # Check if bucket exists
            buckets = [bucket.name for bucket in client.list_buckets()]
            logger.debug(f"Available buckets: {buckets}")
            
            if actual_bucket_name not in buckets:
                raise Exception(f"Bucket {actual_bucket_name} does not exist")
            
            # Check if object exists
            try:
                client.stat_object(actual_bucket_name, object_name)
                logger.debug(f"Verified that {object_name} exists in bucket {actual_bucket_name}")
            except Exception as stat_err:
                logger.error(f"Object {object_name} does not exist in bucket {actual_bucket_name}: {stat_err}")
                return None
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download file
            client.fget_object(actual_bucket_name, object_name, local_path)
            logger.info(f"Successfully downloaded {actual_bucket_name}/{object_name} to {local_path}")
            
            # Verify the download
            if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                logger.debug(f"Verified that {local_path} exists and is not empty")
                return local_path
            else:
                logger.warning(f"Downloaded file {local_path} does not exist or is empty")
                return None
                
        except Exception as e:
            last_exception = e
            logger.warning(f"Download attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {2 ** attempt} seconds...")
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # If we get here, all retries failed
    logger.error(f"Error downloading file from MinIO after {max_retries} attempts: {last_exception}")
    return None  # Return None instead of raising an exception

def list_files(prefix, bucket_name=None, max_retries=3):
    """
    List files in a MinIO bucket with a given prefix.
    
    Args:
        prefix (str): Prefix to filter objects
        bucket_name (str, optional): Bucket to list objects from. Defaults to rasters bucket.
        max_retries (int): Maximum number of list attempts
        
    Returns:
        list: List of object names
    """
    # Map the environment variable bucket names to the safe bucket names
    if bucket_name is None or bucket_name == MINIO_BUCKET_RASTERS:
        bucket_name = "rasters"
    elif bucket_name == MINIO_BUCKET_TILES:
        bucket_name = "tiles"
    
    # Remove any leading slashes from bucket_name to avoid InvalidBucketName errors
    bucket_name = bucket_name.lstrip('/')
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            client = get_minio_client()
            # Check if bucket exists
            buckets = [bucket.name for bucket in client.list_buckets()]
            if bucket_name not in buckets:
                logger.warning(f"Bucket {bucket_name} does not exist")
                return []
            
            # List objects
            objects = client.list_objects(bucket_name, prefix=prefix, recursive=True)
            result = [obj.object_name for obj in objects]
            
            return result
        except Exception as e:
            last_exception = e
            logger.warning(f"List attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # If we get here, all retries failed
    logger.error(f"Error listing files from MinIO after {max_retries} attempts: {last_exception}")
    raise last_exception

def delete_file(object_name, bucket_name=None, max_retries=3):
    """
    Delete a file from MinIO.
    
    Args:
        object_name (str): Name of the object in MinIO
        bucket_name (str, optional): Bucket to delete from. Defaults to rasters bucket.
        max_retries (int): Maximum number of delete attempts
    """
    # Map the environment variable bucket names to the safe bucket names
    if bucket_name is None or bucket_name == MINIO_BUCKET_RASTERS:
        bucket_name = "rasters"
    elif bucket_name == MINIO_BUCKET_TILES:
        bucket_name = "tiles"
    
    # Remove any leading slashes from bucket_name to avoid InvalidBucketName errors
    bucket_name = bucket_name.lstrip('/')
    
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            client = get_minio_client()
            # Check if bucket exists
            buckets = [bucket.name for bucket in client.list_buckets()]
            if bucket_name not in buckets:
                logger.warning(f"Bucket {bucket_name} does not exist")
                return
            
            # Delete object
            client.remove_object(bucket_name, object_name)
            logger.info(f"Deleted {bucket_name}/{object_name}")
            return
        except Exception as e:
            last_exception = e
            logger.warning(f"Delete attempt {attempt+1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # If we get here, all retries failed
    logger.error(f"Error deleting file from MinIO after {max_retries} attempts: {last_exception}")
    raise last_exception

# Comment out or remove this line to prevent bucket initialization at import time
# initialize_buckets() 