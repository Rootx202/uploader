import os
import boto3
from botocore.exceptions import ClientError
from models.protocols.base import BaseUploader

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

class S3Uploader(BaseUploader):
    def __init__(self, access_key, secret_key, bucket_name, region='us-east-1', **kwargs):
        super().__init__(**kwargs)
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = None
    
    def disconnect(self):
        self.s3_client = None
        super().disconnect()
        
    def connect(self):
        if not HAS_BOTO3:
            return False, "boto3 library not installed"
            
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )
            
            # Test connection by listing buckets
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            self.is_connected = True
            return True, "Connected successfully"
            
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
            
    def create_remote_directory(self, remote_path):
        return True, "S3 doesn't require explicit directory creation"
        
    def upload_file(self, local_path, remote_path, progress_callback=None):
        if not self.is_connected:
            return False, "Not connected"
            
        try:
            file_size = os.path.getsize(local_path)
            
            class S3ProgressCallback:
                def __init__(self, callback):
                    self.callback = callback
                    self.uploaded = 0
                    
                def __call__(self, bytes_transferred):
                    self.uploaded += bytes_transferred
                    if self.callback:
                        self.callback(self.uploaded / file_size * 100)
            
            callback = S3ProgressCallback(progress_callback) if progress_callback else None
            
            self.s3_client.upload_file(
                local_path, 
                self.bucket_name, 
                remote_path.lstrip('/'),
                Callback=callback
            )
            
            return True, "File uploaded successfully"
            
        except Exception as e:
            return False, f"Upload failed: {str(e)}"
