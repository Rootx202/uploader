import os
import re
import time
import logging
from PyQt5.QtCore import QThread, pyqtSignal

from models.protocols import (
    FTPUploader,
    SFTPUploader,
    HTTPUploader,
    S3Uploader
)

logger = logging.getLogger(__name__)

class EnhancedUploadWorker(QThread):
    progress_signal = pyqtSignal(str, float)
    file_completed_signal = pyqtSignal(str, bool, str, float)  # Added speed
    all_completed_signal = pyqtSignal(bool, str, int, int)
    log_signal = pyqtSignal(str, str)
    speed_signal = pyqtSignal(float)  # KB/s
    overall_progress_signal = pyqtSignal(int, int, float)  # uploaded_bytes, total_bytes, percent
    
    def __init__(self, uploader_config, files, remote_dir, max_retries, ignore_patterns, 
                 compress_files=False, max_threads=4, include_hidden_files=False, 
                 upload_directory_contents_only=False):
        QThread.__init__(self)
        self.uploader_config = uploader_config
        self.files = files
        self.remote_dir = remote_dir
        self.max_retries = max_retries
        self.ignore_patterns = ignore_patterns
        self.compress_files = compress_files
        self.max_threads = max_threads
        self.include_hidden_files = include_hidden_files
        self.upload_directory_contents_only = upload_directory_contents_only
        self.should_cancel = False
        self.is_paused = False
        self.start_time = None
        self.total_bytes = 0
        self.uploaded_bytes = 0
        
    def run(self):
        self.start_time = time.time()
        self.log_signal.emit("info", f"Starting enhanced upload with {self.max_threads} threads")
        
        # Create uploader instance
        uploader = self.create_uploader()
        if not uploader:
            self.all_completed_signal.emit(False, "Failed to create uploader", 0, 0)
            return
            
        try:
            # Connect to server
            success, message = uploader.connect()
            if not success:
                self.log_signal.emit("error", message)
                self.all_completed_signal.emit(False, message, 0, 0)
                return
                
            self.log_signal.emit("info", "Connected successfully. Preparing file list...")
            
            # Collect files and calculate total size
            all_files = self.collect_files()
            try:
                self.total_bytes = sum(os.path.getsize(local_path) for local_path, _ in all_files if os.path.exists(local_path))
            except OSError as e:
                self.log_signal.emit("error", f"Could not calculate total size: {e}")
                self.total_bytes = 0
            
            self.log_signal.emit("info", f"Found {len(all_files)} files ({self.total_bytes / 1024 / 1024:.1f} MB)")
            
            # Upload files
            if self.max_threads > 1:
                self.upload_files_threaded(uploader, all_files)
            else:
                self.upload_files_sequential(uploader, all_files)
        finally:
            uploader.disconnect()
        
    def create_uploader(self):
        """Create appropriate uploader based on configuration"""
        protocol = self.uploader_config['protocol']
        
        try:
            if protocol == "FTP":
                return FTPUploader(
                    self.uploader_config['host'],
                    self.uploader_config['port'],
                    self.uploader_config['username'],
                    self.uploader_config['password'],
                    False,
                    bandwidth_limit=self.uploader_config.get('bandwidth_limit', 0)
                )
            elif protocol == "FTPS":
                return FTPUploader(
                    self.uploader_config['host'],
                    self.uploader_config['port'],
                    self.uploader_config['username'],
                    self.uploader_config['password'],
                    True,
                    bandwidth_limit=self.uploader_config.get('bandwidth_limit', 0)
                )
            elif protocol == "SFTP":
                return SFTPUploader(
                    self.uploader_config['host'],
                    self.uploader_config['port'],
                    self.uploader_config['username'],
                    self.uploader_config['password'],
                    bandwidth_limit=self.uploader_config.get('bandwidth_limit', 0)
                )
            elif protocol == "HTTP/HTTPS":
                return HTTPUploader(
                    self.uploader_config['url'],
                    self.uploader_config.get('method', 'POST'),
                    self.uploader_config.get('auth_type', 'none'),
                    self.uploader_config.get('username', ''),
                    self.uploader_config.get('password', ''),
                    self.uploader_config.get('headers', {}),
                    bandwidth_limit=self.uploader_config.get('bandwidth_limit', 0)
                )
            elif protocol == "S3":
                return S3Uploader(
                    self.uploader_config['access_key'],
                    self.uploader_config['secret_key'],
                    self.uploader_config['bucket_name'],
                    self.uploader_config.get('region', 'us-east-1'),
                    bandwidth_limit=self.uploader_config.get('bandwidth_limit', 0)
                )
            else:
                self.log_signal.emit("error", f"Unsupported protocol: {protocol}")
                return None
                
        except Exception as e:
            self.log_signal.emit("error", f"Failed to create uploader: {str(e)}")
            return None
    
    def collect_files(self):
        """Collect all files to upload with filtering"""
        compiled_patterns = []
        for pattern in self.ignore_patterns:
            if pattern.strip():
                try:
                    compiled_patterns.append(re.compile(pattern.strip()))
                except re.error:
                    self.log_signal.emit("warning", f"Invalid ignore pattern: {pattern}")
        
        all_files = []
        for file_path in self.files:
            try:
                if os.path.isfile(file_path):
                    if not self._should_ignore(os.path.basename(file_path), compiled_patterns):
                        all_files.append((file_path, os.path.basename(file_path)))
                elif os.path.isdir(file_path):
                    if self._should_ignore(os.path.basename(file_path), compiled_patterns):
                        continue
                    for root, dirs, files in os.walk(file_path):
                        # Filter directories
                        dirs[:] = [d for d in dirs if not self._should_ignore(d, compiled_patterns)]
                        
                        for file in files:
                            if self._should_ignore(file, compiled_patterns):
                                continue
                                
                            local_file_path = os.path.join(root, file)
                            
                            if self.upload_directory_contents_only:
                                # Upload directory contents directly without creating subdirectory
                                rel_path = os.path.relpath(local_file_path, file_path)
                            else:
                                # Keep directory structure (default behavior)
                                rel_path = os.path.relpath(local_file_path, os.path.dirname(file_path))
                            
                            remote_file_path = os.path.join(self.remote_dir, rel_path).replace('\\', '/')
                            all_files.append((local_file_path, remote_file_path))
            except OSError as e:
                self.log_signal.emit("error", f"Error accessing {file_path}: {e}")
        
        return all_files
    
    def upload_files_threaded(self, uploader, files):
        """Upload files using multiple threads"""
        import concurrent.futures
        import threading
        
        successful_uploads = 0
        failed_uploads = 0
        upload_lock = threading.Lock()
        
        def upload_worker(local_path, remote_path):
            nonlocal successful_uploads, failed_uploads
            
            # Each thread needs its own uploader instance
            thread_uploader = self.create_uploader()
            if not thread_uploader:
                return False, 0
                
            success, message = thread_uploader.connect()
            if not success:
                self.log_signal.emit("error", f"Thread connection failed: {message}")
                return False, 0
            
            try:
                success = self.upload_single_file_threaded(thread_uploader, local_path, remote_path, upload_lock)
            finally:
                thread_uploader.disconnect()
                
            with upload_lock:
                if success:
                    successful_uploads += 1
                else:
                    failed_uploads += 1
                    
            return success, 0
        
        # Use ThreadPoolExecutor for concurrent uploads
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads)
        try:
            # Submit all upload tasks
            future_to_file = {
                executor.submit(upload_worker, local_path, remote_path): (local_path, remote_path)
                for local_path, remote_path in files
            }
            
            # Process completed uploads
            for future in concurrent.futures.as_completed(future_to_file):
                if self.should_cancel:
                    # Cancel remaining tasks
                    for f in future_to_file:
                        f.cancel()
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
                    break
                    
                local_path, remote_path = future_to_file[future]
                try:
                    success = future.result()
                except Exception as exc:
                    self.log_signal.emit("error", f"Upload thread error for {local_path}: {exc}")
                    with upload_lock:
                        failed_uploads += 1
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
        
        self.emit_completion_signal(successful_uploads, failed_uploads, len(files))
    
    def upload_files_sequential(self, uploader, files):
        """Upload files one by one"""
        successful_uploads = 0
        failed_uploads = 0
        
        for local_path, remote_path in files:
            if self.should_cancel:
                break
                
            while self.is_paused and not self.should_cancel:
                time.sleep(0.1)
                
            success = self.upload_single_file(uploader, local_path, remote_path)
            if success:
                successful_uploads += 1
            else:
                failed_uploads += 1
        
        self.emit_completion_signal(successful_uploads, failed_uploads, len(files))
    
    def upload_single_file(self, uploader, local_path, remote_path):
        """Upload a single file with retries"""
        self.log_signal.emit("info", f"Uploading {local_path} to {remote_path}")
        
        file_start_time = time.time()
        success = False
        error_message = ""
        
        for attempt in range(self.max_retries + 1):
            if self.should_cancel:
                break
                
            if attempt > 0:
                self.log_signal.emit("warning", f"Retry {attempt}/{self.max_retries} for {local_path}")
                
            def progress_callback(percent):
                if not self.should_cancel:
                    self.progress_signal.emit(local_path, percent)
                    # Calculate current file bytes uploaded
                    try:
                        file_size = os.path.getsize(local_path)
                        bytes_sent_this_file = file_size * percent / 100
                        
                        # Calculate overall progress
                        overall_bytes_uploaded = self.uploaded_bytes + bytes_sent_this_file
                        overall_percent = (overall_bytes_uploaded / self.total_bytes * 100) if self.total_bytes > 0 else 0
                        
                        self.overall_progress_signal.emit(int(overall_bytes_uploaded), int(self.total_bytes), overall_percent)
                        
                        # Calculate and emit speed
                        elapsed = time.time() - file_start_time
                        if elapsed > 0:
                            speed = bytes_sent_this_file / 1024 / elapsed  # KB/s
                            self.speed_signal.emit(speed)
                    except OSError as e:
                        self.log_signal.emit("warning", f"Could not get size of {local_path}: {e}")
            
            success, error_message = uploader.upload_file(local_path, remote_path, progress_callback)
            
            if success:
                break
                
            if attempt < self.max_retries:
                time.sleep(2)
        
        # Calculate upload speed
        try:
            elapsed = time.time() - file_start_time
            speed = os.path.getsize(local_path) / 1024 / max(elapsed, 0.1)  # KB/s
        except OSError as e:
            self.log_signal.emit("warning", f"Could not get size of {local_path} for speed calculation: {e}")
            speed = 0
        
        # Update uploaded bytes when file is completed
        if success:
            try:
                file_size = os.path.getsize(local_path)
                self.uploaded_bytes += file_size
                # Emit final overall progress for this file
                overall_percent = (self.uploaded_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
                self.overall_progress_signal.emit(int(self.uploaded_bytes), int(self.total_bytes), overall_percent)
            except OSError as e:
                self.log_signal.emit("warning", f"Could not get size of {local_path} for progress update: {e}")
        
        self.file_completed_signal.emit(local_path, success, error_message or "Success", speed)
        
        if success:
            self.log_signal.emit("info", f"Successfully uploaded {local_path} ({speed:.1f} KB/s)")
        else:
            self.log_signal.emit("error", f"Failed to upload {local_path}: {error_message}")
            
        return success
    
    def upload_single_file_threaded(self, uploader, local_path, remote_path, upload_lock):
        """Upload a single file with retries in threaded environment"""
        self.log_signal.emit("info", f"Uploading {local_path} to {remote_path}")
        
        file_start_time = time.time()
        success = False
        error_message = ""
        
        try:
            file_size = os.path.getsize(local_path)
        except OSError as e:
            self.log_signal.emit("error", f"Could not get size of {local_path}: {e}")
            return False
        
        for attempt in range(self.max_retries + 1):
            if self.should_cancel:
                break
                
            if attempt > 0:
                self.log_signal.emit("warning", f"Retry {attempt}/{self.max_retries} for {local_path}")
                
            def progress_callback(percent):
                if not self.should_cancel:
                    self.progress_signal.emit(local_path, percent)
                    
                    # For threaded uploads, we need to use locks to update progress safely
                    with upload_lock:
                        bytes_sent_this_file = file_size * percent / 100
                        overall_bytes_uploaded = self.uploaded_bytes + bytes_sent_this_file
                        overall_percent = (overall_bytes_uploaded / self.total_bytes * 100) if self.total_bytes > 0 else 0
                        
                        self.overall_progress_signal.emit(int(overall_bytes_uploaded), int(self.total_bytes), overall_percent)
                        
                        # Calculate and emit speed
                        elapsed = time.time() - file_start_time
                        if elapsed > 0:
                            speed = bytes_sent_this_file / 1024 / elapsed  # KB/s
                            self.speed_signal.emit(speed)
            
            success, error_message = uploader.upload_file(local_path, remote_path, progress_callback)
            
            if success:
                break
                
            if attempt < self.max_retries:
                time.sleep(2)
        
        # Calculate upload speed
        try:
            elapsed = time.time() - file_start_time
            speed = file_size / 1024 / max(elapsed, 0.1)  # KB/s
        except OSError as e:
            self.log_signal.emit("warning", f"Could not get size of {local_path} for speed calculation: {e}")
            speed = 0
        
        # Update uploaded bytes when file is completed (with lock for thread safety)
        if success:
            with upload_lock:
                self.uploaded_bytes += file_size
                # Emit final overall progress for this file
                overall_percent = (self.uploaded_bytes / self.total_bytes * 100) if self.total_bytes > 0 else 0
                self.overall_progress_signal.emit(int(self.uploaded_bytes), int(self.total_bytes), overall_percent)
        
        self.file_completed_signal.emit(local_path, success, error_message or "Success", speed)
        
        if success:
            self.log_signal.emit("info", f"Successfully uploaded {local_path} ({speed:.1f} KB/s)")
        else:
            self.log_signal.emit("error", f"Failed to upload {local_path}: {error_message}")
            
        return success
    
    def _should_ignore(self, filename, patterns):
        if not self.include_hidden_files and filename.startswith('.'):
            return True
            
        for pattern in patterns:
            if pattern.search(filename):
                return True
                
        return False
    
    def emit_completion_signal(self, successful, failed, total):
        """Emit the completion signal"""
        if self.should_cancel:
            self.all_completed_signal.emit(False, "Upload canceled", successful, failed)
        elif failed == 0:
            self.all_completed_signal.emit(True, f"All {total} files uploaded successfully", successful, failed)
        else:
            self.all_completed_signal.emit(False, f"Upload completed with {failed} errors", successful, failed)
    
    def cancel(self):
        self.should_cancel = True
        
    def pause(self):
        self.is_paused = True
        
    def resume(self):
        self.is_paused = False
