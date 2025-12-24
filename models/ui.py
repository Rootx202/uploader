import sys
import os
import json
import logging
import time
from datetime import datetime
from typing import Dict

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, 
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, 
    QFileDialog, QProgressBar, QTextEdit, QCheckBox, QGridLayout, 
    QGroupBox, QFormLayout, QMessageBox, QSpinBox, QSystemTrayIcon,
    QStyle, QListWidget, QListWidgetItem, QSplitter, QFrame, QMenu,
    QSlider, QDoubleSpinBox, QTreeWidget, QTreeWidgetItem, QTabBar,
    QScrollArea, QSizePolicy, QDialogButtonBox, QDialog, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QTimer, QMimeData
from PyQt5.QtGui import QIcon, QFont, QPalette, QColor, QTextCursor, QDragEnterEvent, QDropEvent

from models.worker import EnhancedUploadWorker

logger = logging.getLogger(__name__)

# Protocol-specific imports
try:
    from webdavclient3 import Client as WebDAVClient
    HAS_WEBDAV = True
except ImportError:
    HAS_WEBDAV = False

try:
    import dropbox
    HAS_DROPBOX = True
except ImportError:
    HAS_DROPBOX = False

try:
    from googleapiclient.discovery import build
    from google_auth_oauthlib.flow import Flow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False

class DragDropListWidget(QListWidget):
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
            
    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                files.append(url.toLocalFile())
        
        if files:
            self.files_dropped.emit(files)
        event.accept()

class EnhancedMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Enhanced Remote File Uploader v2.0")
        
        # Initialize variables
        self.selected_files = []
        self.file_progress = {}
        self.upload_worker = None
        self.settings = QSettings("EnhancedUploader", "Settings")
        self.dark_mode = self.settings.value("dark_mode", False, type=bool)
        
        # Set window geometry with minimum size
        self.setMinimumSize(800, 600)
        
        # Restore window geometry from settings or use defaults
        if self.settings.contains("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        else:
            self.setGeometry(100, 100, 1200, 800)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        self.init_ui()
        self.init_system_tray()
        self.load_saved_servers()
        
        if self.dark_mode:
            self.toggle_theme(True)
    
    def init_ui(self):
        """Initialize the enhanced UI"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Add tabs
        self.tab_widget.addTab(self.create_connection_tab(), "Connection")
        self.tab_widget.addTab(self.create_files_tab(), "Files & Upload")
        self.tab_widget.addTab(self.create_server_browser_tab(), "🗂️ Server Browser")
        self.tab_widget.addTab(self.create_advanced_tab(), "Advanced")
        self.tab_widget.addTab(self.create_log_tab(), "Log")
        self.tab_widget.addTab(self.create_settings_tab(), "Settings")
        
        layout.addWidget(self.tab_widget)
        
        # Status bar
        self.statusBar().showMessage("Ready - Enhanced Version")
    
    def create_connection_tab(self):
        """Create the enhanced connection tab"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # Protocol selection (more protocols)
        protocol_group = QGroupBox("Select Protocol")
        protocol_layout = QHBoxLayout()
        
        self.protocol_combo = QComboBox()
        protocols = ["FTP", "FTPS", "SFTP", "HTTP/HTTPS", "S3"]
        
        # Add conditional protocols based on available libraries
        if HAS_WEBDAV:
            protocols.append("WebDAV")
        if HAS_DROPBOX:
            protocols.append("Dropbox")
        if HAS_GOOGLE:
            protocols.append("Google Drive")
            
        self.protocol_combo.addItems(protocols)
        self.protocol_combo.currentTextChanged.connect(self.protocol_changed)
        
        protocol_layout.addWidget(QLabel("Protocol:"))
        protocol_layout.addWidget(self.protocol_combo)
        protocol_layout.addStretch()
        protocol_group.setLayout(protocol_layout)
        
        layout.addWidget(protocol_group)
        
        # Saved servers section
        saved_servers_group = QGroupBox("Saved Servers")
        saved_servers_layout = QVBoxLayout()
        
        server_list_layout = QHBoxLayout()
        
        self.server_list = QListWidget()
        self.server_list.setMinimumHeight(100)
        self.server_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.server_list.itemClicked.connect(self.load_server)
        server_list_layout.addWidget(self.server_list)
        
        server_buttons_layout = QVBoxLayout()
        self.save_server_btn = QPushButton("Save Current")
        self.save_server_btn.clicked.connect(self.save_current_server)
        self.delete_server_btn = QPushButton("Delete Selected")
        self.delete_server_btn.clicked.connect(self.delete_server)
        
        server_buttons_layout.addWidget(self.save_server_btn)
        server_buttons_layout.addWidget(self.delete_server_btn)
        server_buttons_layout.addStretch()
        
        server_list_layout.addLayout(server_buttons_layout)
        saved_servers_layout.addLayout(server_list_layout)
        saved_servers_group.setLayout(saved_servers_layout)
        
        layout.addWidget(saved_servers_group)
        
        # Create scrollable connection settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.connection_settings_widget = QWidget()
        self.connection_form_layout = QFormLayout(self.connection_settings_widget)
        
        # Common fields
        self.server_name_input = QLineEdit()
        self.server_name_input.setPlaceholderText("My Server (for saved connections)")
        self.connection_form_layout.addRow("Server Name:", self.server_name_input)
        
        # Protocol-specific fields will be added dynamically
        self.protocol_fields = {}
        
        scroll.setWidget(self.connection_settings_widget)
        layout.addWidget(scroll)
        
        # Test connection button
        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.clicked.connect(self.test_connection)
        layout.addWidget(self.test_connection_btn)
        
        # Initialize with FTP fields
        self.protocol_changed("FTP")
        
        return tab
    
    def protocol_changed(self, protocol):
        """Handle protocol change and update fields"""
        # Clear existing protocol fields
        for field_name, widgets in self.protocol_fields.items():
            for widget in widgets:
                self.connection_form_layout.removeRow(widget)
        
        self.protocol_fields.clear()
        
        # Add protocol-specific fields
        if protocol in ["FTP", "FTPS", "SFTP"]:
            # Standard server fields
            host_input = QLineEdit()
            host_input.setPlaceholderText("ftp.example.com")
            
            port_input = QSpinBox()
            port_input.setRange(1, 65535)
            if protocol == "SFTP":
                port_input.setValue(22)
            else:
                port_input.setValue(21)
            
            username_input = QLineEdit()
            username_input.setPlaceholderText("username")
            
            password_input = QLineEdit()
            password_input.setPlaceholderText("password")
            password_input.setEchoMode(QLineEdit.Password)
            
            remote_dir_input = QLineEdit()
            remote_dir_input.setPlaceholderText("/public_html/uploads")
            
            self.connection_form_layout.addRow("Host:", host_input)
            self.connection_form_layout.addRow("Port:", port_input)
            self.connection_form_layout.addRow("Username:", username_input)
            self.connection_form_layout.addRow("Password:", password_input)
            self.connection_form_layout.addRow("Remote Directory:", remote_dir_input)
            
            self.protocol_fields[protocol] = {
                'host': host_input,
                'port': port_input,
                'username': username_input,
                'password': password_input,
                'remote_dir': remote_dir_input
            }
            
        elif protocol == "HTTP/HTTPS":
            # HTTP specific fields
            url_input = QLineEdit()
            url_input.setPlaceholderText("https://example.com/upload")
            
            method_combo = QComboBox()
            method_combo.addItems(["POST", "PUT"])
            
            auth_combo = QComboBox()
            auth_combo.addItems(["none", "basic", "bearer"])
            
            username_input = QLineEdit()
            username_input.setPlaceholderText("username (for basic auth)")
            
            token_input = QLineEdit()
            token_input.setPlaceholderText("token/password")
            token_input.setEchoMode(QLineEdit.Password)
            
            headers_input = QTextEdit()
            headers_input.setPlaceholderText('{"Content-Type": "application/json"}')
            headers_input.setMaximumHeight(60)
            
            self.connection_form_layout.addRow("URL:", url_input)
            self.connection_form_layout.addRow("Method:", method_combo)
            self.connection_form_layout.addRow("Auth Type:", auth_combo)
            self.connection_form_layout.addRow("Username:", username_input)
            self.connection_form_layout.addRow("Token/Password:", token_input)
            self.connection_form_layout.addRow("Custom Headers:", headers_input)
            
            self.protocol_fields[protocol] = {
                'url': url_input,
                'method': method_combo,
                'auth_type': auth_combo,
                'username': username_input,
                'password': token_input,
                'headers': headers_input
            }
            
        elif protocol == "S3":
            # S3 specific fields
            access_key_input = QLineEdit()
            access_key_input.setPlaceholderText("AWS Access Key ID")
            
            secret_key_input = QLineEdit()
            secret_key_input.setPlaceholderText("AWS Secret Access Key")
            secret_key_input.setEchoMode(QLineEdit.Password)
            
            bucket_input = QLineEdit()
            bucket_input.setPlaceholderText("my-bucket-name")
            
            region_input = QLineEdit()
            region_input.setPlaceholderText("us-east-1")
            region_input.setText("us-east-1")
            
            prefix_input = QLineEdit()
            prefix_input.setPlaceholderText("folder/subfolder/ (optional)")
            
            self.connection_form_layout.addRow("Access Key:", access_key_input)
            self.connection_form_layout.addRow("Secret Key:", secret_key_input)
            self.connection_form_layout.addRow("Bucket Name:", bucket_input)
            self.connection_form_layout.addRow("Region:", region_input)
            self.connection_form_layout.addRow("Prefix:", prefix_input)
            
            self.protocol_fields[protocol] = {
                'access_key': access_key_input,
                'secret_key': secret_key_input,
                'bucket_name': bucket_input,
                'region': region_input,
                'remote_dir': prefix_input
            }
    
    def create_files_tab(self):
        """Create enhanced files tab with drag & drop"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # File selection with drag & drop support
        selection_group = QGroupBox("Select Files and Directories (Drag & Drop Supported)")
        selection_layout = QVBoxLayout()
        
        # Drag & drop info
        drag_drop_info = QLabel("💡 You can drag and drop files/folders directly into the file list below")
        drag_drop_info.setStyleSheet("color: #0066cc; font-style: italic; padding: 5px;")
        selection_layout.addWidget(drag_drop_info)
        
        button_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("📁 Add Files")
        self.add_files_btn.clicked.connect(self.add_files)
        self.add_directory_btn = QPushButton("📂 Add Directory")
        self.add_directory_btn.clicked.connect(self.add_directory)
        self.clear_files_btn = QPushButton("🗑️ Clear All")
        self.clear_files_btn.clicked.connect(self.clear_files)
        
        button_layout.addWidget(self.add_files_btn)
        button_layout.addWidget(self.add_directory_btn)
        button_layout.addWidget(self.clear_files_btn)
        
        selection_layout.addLayout(button_layout)
        
        # Directory contents option
        self.upload_directory_contents_checkbox = QCheckBox("Upload directory contents only (preserve subfolder structure)")
        self.upload_directory_contents_checkbox.setToolTip(
            "When checked: Upload the contents of the selected directory (including subfolders)\n"
            "directly to the destination without creating the parent directory.\n"
            "When unchecked: Upload the entire directory including its name."
        )
        selection_layout.addWidget(self.upload_directory_contents_checkbox)
        
        # Enhanced file list with drag & drop
        self.file_list = DragDropListWidget()
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.file_list.files_dropped.connect(self.add_dropped_files)
        selection_layout.addWidget(self.file_list)
        
        # File operations
        file_ops_layout = QHBoxLayout()
        self.remove_selected_btn = QPushButton("Remove Selected")
        self.remove_selected_btn.clicked.connect(self.remove_selected_files)
        self.preview_files_btn = QPushButton("Preview Files")
        self.preview_files_btn.clicked.connect(self.preview_files)
        
        file_ops_layout.addWidget(self.remove_selected_btn)
        file_ops_layout.addWidget(self.preview_files_btn)
        file_ops_layout.addStretch()
        
        selection_layout.addLayout(file_ops_layout)
        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)
        
        # Upload options
        options_group = QGroupBox("Upload Options")
        options_layout = QGridLayout()
        
        self.retry_count_spinbox = QSpinBox()
        self.retry_count_spinbox.setRange(0, 10)
        self.retry_count_spinbox.setValue(3)
        
        self.ignore_patterns_input = QLineEdit()
        self.ignore_patterns_input.setPlaceholderText("*.tmp, *.bak (comma separated regex patterns)")
        
        # New options
        self.compress_files_checkbox = QCheckBox("Compress files before upload")
        self.resume_uploads_checkbox = QCheckBox("Enable resume for failed uploads")
        self.verify_uploads_checkbox = QCheckBox("Verify uploads with checksums")
        self.include_hidden_files_checkbox = QCheckBox("Include hidden files")
        
        options_layout.addWidget(QLabel("Max Retries:"), 0, 0)
        options_layout.addWidget(self.retry_count_spinbox, 0, 1)
        options_layout.addWidget(QLabel("Ignore Patterns:"), 1, 0)
        options_layout.addWidget(self.ignore_patterns_input, 1, 1)
        options_layout.addWidget(self.compress_files_checkbox, 2, 0, 1, 2)
        options_layout.addWidget(self.resume_uploads_checkbox, 3, 0, 1, 2)
        options_layout.addWidget(self.verify_uploads_checkbox, 4, 0, 1, 2)
        options_layout.addWidget(self.include_hidden_files_checkbox, 5, 0, 1, 2)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Upload controls
        control_layout = QHBoxLayout()
        
        self.start_upload_btn = QPushButton("🚀 Start Upload")
        self.start_upload_btn.clicked.connect(self.start_upload)
        self.start_upload_btn.setStyleSheet("font-weight: bold; padding: 8px; background-color: #4CAF50; color: white;")
        
        self.pause_upload_btn = QPushButton("⏸️ Pause Upload")
        self.pause_upload_btn.clicked.connect(self.pause_upload)
        self.pause_upload_btn.setEnabled(False)
        
        self.cancel_upload_btn = QPushButton("⏹️ Cancel Upload")
        self.cancel_upload_btn.clicked.connect(self.cancel_upload)
        self.cancel_upload_btn.setEnabled(False)
        
        control_layout.addWidget(self.start_upload_btn)
        control_layout.addWidget(self.pause_upload_btn)
        control_layout.addWidget(self.cancel_upload_btn)
        
        layout.addLayout(control_layout)
        
        # Progress section
        progress_group = QGroupBox("Upload Progress")
        progress_layout = QVBoxLayout()
        
        # Overall progress
        self.overall_progress_label = QLabel("Overall Progress:")
        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setTextVisible(True)
        self.overall_progress_bar.setFormat("%p% (%v/%m files)")
        
        # Speed indicator
        self.speed_label = QLabel("Upload Speed: 0 KB/s")
        self.eta_label = QLabel("ETA: --")
        
        speed_eta_layout = QHBoxLayout()
        speed_eta_layout.addWidget(self.speed_label)
        speed_eta_layout.addWidget(self.eta_label)
        speed_eta_layout.addStretch()
        
        progress_layout.addWidget(self.overall_progress_label)
        progress_layout.addWidget(self.overall_progress_bar)
        progress_layout.addLayout(speed_eta_layout)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        return tab
    
    def create_server_browser_tab(self):
        """Create server browser tab"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # Browser controls
        controls_group = QGroupBox("🌐 Server Browser Controls")
        controls_layout = QHBoxLayout()
        
        # Connect/Disconnect button
        self.browser_connect_btn = QPushButton("🔗 Connect to Browse")
        self.browser_connect_btn.clicked.connect(self.connect_for_browsing)
        self.browser_connect_btn.setToolTip("Connect using current connection settings to browse server files")
        
        # Refresh button
        self.browser_refresh_btn = QPushButton("🔄 Refresh")
        self.browser_refresh_btn.clicked.connect(self.refresh_browser)
        self.browser_refresh_btn.setEnabled(False)
        
        # Path navigation
        self.browser_path_input = QLineEdit("/")
        self.browser_path_input.setPlaceholderText("Enter remote path (e.g., /home/user/)")
        self.browser_path_input.returnPressed.connect(self.navigate_to_path)
        
        self.browser_navigate_btn = QPushButton("📂 Go")
        self.browser_navigate_btn.clicked.connect(self.navigate_to_path)
        self.browser_navigate_btn.setEnabled(False)
        
        # Go up button
        self.browser_up_btn = QPushButton("⬆️ Up")
        self.browser_up_btn.clicked.connect(self.go_up_directory)
        self.browser_up_btn.setEnabled(False)
        
        controls_layout.addWidget(self.browser_connect_btn)
        controls_layout.addWidget(self.browser_refresh_btn)
        controls_layout.addWidget(QLabel("Path:"))
        controls_layout.addWidget(self.browser_path_input)
        controls_layout.addWidget(self.browser_navigate_btn)
        controls_layout.addWidget(self.browser_up_btn)
        controls_group.setLayout(controls_layout)
        
        layout.addWidget(controls_group)
        
        # Browser content - using splitter for two columns
        browser_splitter = QSplitter(Qt.Horizontal)
        browser_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Left panel - directory tree/list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Server file list
        server_files_group = QGroupBox("📁 Server Files & Folders")
        server_files_layout = QVBoxLayout()
        
        self.server_file_tree = QTreeWidget()
        self.server_file_tree.setHeaderLabels(["Name", "Type", "Size", "Modified", "Permissions"])
        self.server_file_tree.setRootIsDecorated(True)
        self.server_file_tree.setAlternatingRowColors(True)
        self.server_file_tree.setSortingEnabled(True)
        self.server_file_tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.server_file_tree.itemDoubleClicked.connect(self.on_server_item_double_click)
        self.server_file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.server_file_tree.customContextMenuRequested.connect(self.show_server_context_menu)
        
        server_files_layout.addWidget(self.server_file_tree)
        server_files_group.setLayout(server_files_layout)
        left_layout.addWidget(server_files_group)
        
        browser_splitter.addWidget(left_panel)
        
        # Right panel - actions and info
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # File operations
        operations_group = QGroupBox("📋 File Operations")
        operations_layout = QVBoxLayout()
        
        # Download section
        download_frame = QFrame()
        download_layout = QHBoxLayout(download_frame)
        
        self.download_selected_btn = QPushButton("💾 Download Selected")
        self.download_selected_btn.clicked.connect(self.download_selected_files)
        self.download_selected_btn.setEnabled(False)
        self.download_selected_btn.setToolTip("Download selected files/folders")
        
        self.download_folder_input = QLineEdit()
        self.download_folder_input.setPlaceholderText("Download folder path")
        self.download_browse_btn = QPushButton("📂")
        self.download_browse_btn.clicked.connect(self.browse_download_folder)
        
        download_layout.addWidget(self.download_selected_btn)
        download_layout.addWidget(QLabel("to:"))
        download_layout.addWidget(self.download_folder_input)
        download_layout.addWidget(self.download_browse_btn)
        
        operations_layout.addWidget(download_frame)
        
        # Upload to current location
        upload_frame = QFrame()
        upload_layout = QHBoxLayout(upload_frame)
        
        self.upload_to_current_btn = QPushButton("⬆️ Upload to Current Location")
        self.upload_to_current_btn.clicked.connect(self.upload_to_current_location)
        self.upload_to_current_btn.setEnabled(False)
        self.upload_to_current_btn.setToolTip("Upload files to currently browsed directory")
        
        upload_layout.addWidget(self.upload_to_current_btn)
        operations_layout.addWidget(upload_frame)
        
        # File management buttons
        management_frame = QFrame()
        management_layout = QHBoxLayout(management_frame)
        
        self.create_folder_btn = QPushButton("📁 New Folder")
        self.create_folder_btn.clicked.connect(self.create_new_folder)
        self.create_folder_btn.setEnabled(False)
        
        self.delete_selected_btn = QPushButton("🗑️ Delete Selected")
        self.delete_selected_btn.clicked.connect(self.delete_selected_files)
        self.delete_selected_btn.setEnabled(False)
        self.delete_selected_btn.setStyleSheet("QPushButton { color: red; }")
        
        management_layout.addWidget(self.create_folder_btn)
        management_layout.addWidget(self.delete_selected_btn)
        
        operations_layout.addWidget(management_frame)
        operations_group.setLayout(operations_layout)
        right_layout.addWidget(operations_group)
        
        # File info section
        info_group = QGroupBox("ℹ️ Selection Info")
        info_layout = QVBoxLayout()
        
        self.selected_info_label = QLabel("No files selected")
        self.selected_info_label.setWordWrap(True)
        self.selected_info_label.setStyleSheet("QLabel { padding: 10px; background-color: #f0f0f0; border-radius: 5px; }")
        
        info_layout.addWidget(self.selected_info_label)
        info_group.setLayout(info_layout)
        right_layout.addWidget(info_group)
        
        # Transfer progress for browser operations
        browser_progress_group = QGroupBox("📊 Transfer Progress")
        browser_progress_layout = QVBoxLayout()
        
        self.browser_progress_bar = QProgressBar()
        self.browser_progress_label = QLabel("Ready")
        
        browser_progress_layout.addWidget(self.browser_progress_label)
        browser_progress_layout.addWidget(self.browser_progress_bar)
        browser_progress_group.setLayout(browser_progress_layout)
        right_layout.addWidget(browser_progress_group)
        
        right_layout.addStretch()
        browser_splitter.addWidget(right_panel)
        
        # Set splitter sizes (70% left, 30% right)
        browser_splitter.setSizes([700, 300])
        
        layout.addWidget(browser_splitter)
        
        # Initialize browser state
        self.current_browser_connection = None
        self.current_remote_path = "/"
        self.browser_connected = False
        
        return tab
    
    def create_advanced_tab(self):
        """Create advanced settings tab"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # Threading settings
        threading_group = QGroupBox("Performance Settings")
        threading_layout = QGridLayout()
        
        self.max_threads_spinbox = QSpinBox()
        self.max_threads_spinbox.setRange(1, 8)
        self.max_threads_spinbox.setValue(4)
        
        # Bandwidth limiting
        self.bandwidth_limit_checkbox = QCheckBox("Limit bandwidth")
        self.bandwidth_limit_spinbox = QSpinBox()
        self.bandwidth_limit_spinbox.setRange(1, 10000)
        self.bandwidth_limit_spinbox.setValue(1000)
        self.bandwidth_limit_spinbox.setSuffix(" KB/s")
        self.bandwidth_limit_spinbox.setEnabled(False)
        
        self.bandwidth_limit_checkbox.toggled.connect(self.bandwidth_limit_spinbox.setEnabled)
        
        # Buffer size
        self.buffer_size_spinbox = QSpinBox()
        self.buffer_size_spinbox.setRange(1024, 65536)
        self.buffer_size_spinbox.setValue(8192)
        self.buffer_size_spinbox.setSuffix(" bytes")
        
        threading_layout.addWidget(QLabel("Max Threads:"), 0, 0)
        threading_layout.addWidget(self.max_threads_spinbox, 0, 1)
        threading_layout.addWidget(self.bandwidth_limit_checkbox, 1, 0)
        threading_layout.addWidget(self.bandwidth_limit_spinbox, 1, 1)
        threading_layout.addWidget(QLabel("Buffer Size:"), 2, 0)
        threading_layout.addWidget(self.buffer_size_spinbox, 2, 1)
        
        threading_group.setLayout(threading_layout)
        layout.addWidget(threading_group)
        
        # Auto-retry settings
        retry_group = QGroupBox("Advanced Retry Settings")
        retry_layout = QGridLayout()
        
        self.exponential_backoff_checkbox = QCheckBox("Use exponential backoff")
        self.exponential_backoff_checkbox.setChecked(True)
        
        self.retry_delay_spinbox = QDoubleSpinBox()
        self.retry_delay_spinbox.setRange(0.1, 60.0)
        self.retry_delay_spinbox.setValue(2.0)
        self.retry_delay_spinbox.setSuffix(" seconds")
        
        retry_layout.addWidget(self.exponential_backoff_checkbox, 0, 0, 1, 2)
        retry_layout.addWidget(QLabel("Base Retry Delay:"), 1, 0)
        retry_layout.addWidget(self.retry_delay_spinbox, 1, 1)
        
        retry_group.setLayout(retry_layout)
        layout.addWidget(retry_group)
        
        # Logging settings
        logging_group = QGroupBox("Logging Settings")
        logging_layout = QVBoxLayout()
        
        self.detailed_logging_checkbox = QCheckBox("Enable detailed logging")
        self.detailed_logging_checkbox.setChecked(True)
        
        self.log_to_file_checkbox = QCheckBox("Log to file")
        self.log_to_file_checkbox.setChecked(True)
        
        logging_layout.addWidget(self.detailed_logging_checkbox)
        logging_layout.addWidget(self.log_to_file_checkbox)
        
        logging_group.setLayout(logging_layout)
        layout.addWidget(logging_group)
        
        layout.addStretch()
        
        return tab
    
    def create_log_tab(self):
        """Create enhanced log tab"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # Log filters
        filter_group = QGroupBox("Log Filters")
        filter_layout = QHBoxLayout()
        
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["All", "Info", "Warning", "Error"])
        self.log_level_combo.currentTextChanged.connect(self.filter_logs)
        
        self.search_log_input = QLineEdit()
        self.search_log_input.setPlaceholderText("Search logs...")
        self.search_log_input.textChanged.connect(self.search_logs)
        
        filter_layout.addWidget(QLabel("Level:"))
        filter_layout.addWidget(self.log_level_combo)
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.search_log_input)
        filter_layout.addStretch()
        
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)
        
        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 9))
        self.log_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log_display)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.clear_log_btn = QPushButton("🗑️ Clear Log")
        self.clear_log_btn.clicked.connect(self.clear_log)
        
        self.save_log_btn = QPushButton("💾 Save Log")
        self.save_log_btn.clicked.connect(self.save_log)
        
        self.export_stats_btn = QPushButton("📊 Export Statistics")
        self.export_stats_btn.clicked.connect(self.export_statistics)
        
        button_layout.addWidget(self.clear_log_btn)
        button_layout.addWidget(self.save_log_btn)
        button_layout.addWidget(self.export_stats_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return tab
    
    def create_settings_tab(self):
        """Create enhanced settings tab"""
        tab = QWidget()
        tab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(tab)
        
        # Appearance
        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout()
        
        self.theme_toggle = QCheckBox("🌙 Dark Mode")
        self.theme_toggle.setChecked(self.dark_mode)
        self.theme_toggle.toggled.connect(self.toggle_theme)
        
        self.minimize_to_tray_checkbox = QCheckBox("Minimize to system tray")
        self.minimize_to_tray_checkbox.setChecked(self.settings.value("minimize_to_tray", True, type=bool))
        self.minimize_to_tray_checkbox.toggled.connect(lambda state: (self.settings.setValue("minimize_to_tray", state), self.settings.sync()))
        
        theme_layout.addWidget(self.theme_toggle)
        theme_layout.addWidget(self.minimize_to_tray_checkbox)
        theme_group.setLayout(theme_layout)
        layout.addWidget(theme_group)
        
        # Notifications
        notification_group = QGroupBox("Notifications")
        notification_layout = QVBoxLayout()
        
        self.notification_toggle = QCheckBox("Show system notification on completion")
        self.notification_toggle.setChecked(self.settings.value("notifications", True, type=bool))
        self.notification_toggle.toggled.connect(lambda state: (self.settings.setValue("notifications", state), self.settings.sync()))
        
        self.sound_notification_checkbox = QCheckBox("Play sound on completion")
        self.sound_notification_checkbox.setChecked(self.settings.value("sound_notifications", False, type=bool))
        self.sound_notification_checkbox.toggled.connect(lambda state: (self.settings.setValue("sound_notifications", state), self.settings.sync()))
        
        notification_layout.addWidget(self.notification_toggle)
        notification_layout.addWidget(self.sound_notification_checkbox)
        notification_group.setLayout(notification_layout)
        layout.addWidget(notification_group)
        
        # Auto-save settings
        autosave_group = QGroupBox("Auto-save")
        autosave_layout = QVBoxLayout()
        
        self.auto_save_session_checkbox = QCheckBox("Auto-save session on exit")
        self.auto_save_session_checkbox.setChecked(self.settings.value("auto_save_session", True, type=bool))
        self.auto_save_session_checkbox.toggled.connect(lambda state: (self.settings.setValue("auto_save_session", state), self.settings.sync()))
        
        self.restore_session_checkbox = QCheckBox("Restore last session on startup")
        self.restore_session_checkbox.setChecked(self.settings.value("restore_session", True, type=bool))
        self.restore_session_checkbox.toggled.connect(lambda state: (self.settings.setValue("restore_session", state), self.settings.sync()))
        
        autosave_layout.addWidget(self.auto_save_session_checkbox)
        autosave_layout.addWidget(self.restore_session_checkbox)
        autosave_group.setLayout(autosave_layout)
        layout.addWidget(autosave_group)
        
        # Application Control
        app_control_group = QGroupBox("Application Control")
        app_control_layout = QVBoxLayout()
        
        # Exit completely button
        exit_completely_btn = QPushButton("🚪 Exit Application Completely")
        exit_completely_btn.clicked.connect(self.quit_application)
        exit_completely_btn.setStyleSheet("background-color: #dc3545; color: white; padding: 10px; font-weight: bold;")
        exit_completely_btn.setToolTip("Exit the application completely, not just minimize to tray")
        
        # Minimize to tray button  
        minimize_to_tray_btn = QPushButton("📦 Minimize to System Tray")
        minimize_to_tray_btn.clicked.connect(self.hide)
        minimize_to_tray_btn.setStyleSheet("background-color: #28a745; color: white; padding: 8px;")
        minimize_to_tray_btn.setToolTip("Keep application running in background")
        
        app_control_layout.addWidget(minimize_to_tray_btn)
        app_control_layout.addWidget(exit_completely_btn)
        app_control_group.setLayout(app_control_layout)
        layout.addWidget(app_control_group)
        
        # Reset settings
        reset_group = QGroupBox("Reset")
        reset_layout = QVBoxLayout()
        
        reset_settings_btn = QPushButton("🔄 Reset All Settings")
        reset_settings_btn.clicked.connect(self.reset_settings)
        reset_settings_btn.setStyleSheet("background-color: #ff6b6b; color: white; padding: 8px;")
        
        reset_layout.addWidget(reset_settings_btn)
        reset_group.setLayout(reset_layout)
        layout.addWidget(reset_group)
        
        layout.addStretch()
        
        return tab
    
    # ===== EVENT HANDLERS =====
    
    def init_system_tray(self):
        """Initialize system tray icon"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
            
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        
        tray_menu = QMenu()
        show_action = tray_menu.addAction("🔍 Show")
        show_action.triggered.connect(self.show)
        
        tray_menu.addSeparator()
        
        start_action = tray_menu.addAction("🚀 Start Upload")
        start_action.triggered.connect(self.start_upload)
        
        pause_action = tray_menu.addAction("⏸️ Pause Upload")
        pause_action.triggered.connect(self.pause_upload)
        
        cancel_action = tray_menu.addAction("⏹️ Cancel Upload")
        cancel_action.triggered.connect(self.cancel_upload)
        
        tray_menu.addSeparator()
        
        quit_action = tray_menu.addAction("🚪 Exit Completely")
        quit_action.triggered.connect(self.quit_application)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
    def toggle_theme(self, dark_mode):
        """Toggle between light and dark themes"""
        self.dark_mode = dark_mode
        self.settings.setValue("dark_mode", dark_mode)
        self.settings.sync()  # Ensure immediate save
        
        if dark_mode:
            # Enhanced dark theme
            palette = QPalette()
            palette.setColor(QPalette.Window, QColor(45, 45, 45))
            palette.setColor(QPalette.WindowText, QColor(240, 240, 240))
            palette.setColor(QPalette.Base, QColor(35, 35, 35))
            palette.setColor(QPalette.AlternateBase, QColor(60, 60, 60))
            palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
            palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
            palette.setColor(QPalette.Text, QColor(240, 240, 240))
            palette.setColor(QPalette.Button, QColor(60, 60, 60))
            palette.setColor(QPalette.ButtonText, QColor(240, 240, 240))
            palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
            palette.setColor(QPalette.Link, QColor(42, 130, 218))
            palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
            palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
            
            QApplication.setPalette(palette)
            
            # Custom styles for enhanced UI
            self.log_display.setStyleSheet("""
                QTextEdit {
                    background-color: #2d2d2d;
                    color: #f0f0f0;
                    border: 1px solid #555;
                }
            """)
        else:
            # Light theme
            QApplication.setPalette(QApplication.style().standardPalette())
            self.log_display.setStyleSheet("")
    
    def add_files(self):
        """Add files through file dialog"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Select Files", 
            "", 
            "All Files (*.*)"
        )
        if file_paths:
            self.add_dropped_files(file_paths)
    
    def add_directory(self):
        """Add directory through directory dialog"""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dir_path:
            self.add_dropped_files([dir_path])
    
    def add_dropped_files(self, file_paths):
        """Add files from drag & drop or dialogs"""
        added_count = 0
        for file_path in file_paths:
            if file_path not in self.selected_files:
                self.selected_files.append(file_path)
                
                # Add to list with file info
                item_text = file_path
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path) / 1024 / 1024  # MB
                    item_text += f" ({size:.1f} MB)"
                elif os.path.isdir(file_path):
                    try:
                        file_count = sum(len(files) for _, _, files in os.walk(file_path))
                        item_text += f" ({file_count} files)"
                    except:
                        item_text += " (Directory)"
                
                self.file_list.addItem(item_text)
                added_count += 1
        
        if added_count > 0:
            self.statusBar().showMessage(f"Added {added_count} items")
    
    def clear_files(self):
        """Clear all selected files"""
        self.selected_files.clear()
        self.file_list.clear()
        self.file_progress.clear()
        self.statusBar().showMessage("File list cleared")
    
    def remove_selected_files(self):
        """Remove selected files from the list"""
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            # Find the corresponding file path
            item_text = item.text()
            original_path = None
            for path in self.selected_files:
                if item_text.startswith(path):
                    original_path = path
                    break
            
            if original_path:
                self.selected_files.remove(original_path)
                if original_path in self.file_progress:
                    del self.file_progress[original_path]
                    
            row = self.file_list.row(item)
            self.file_list.takeItem(row)
    
    def preview_files(self):
        """Show file preview dialog"""
        if not self.selected_files:
            QMessageBox.information(self, "Preview", "No files selected.")
            return
        
        total_size = 0
        file_count = 0
        dir_count = 0
        
        for path in self.selected_files:
            if os.path.isfile(path):
                file_count += 1
                total_size += os.path.getsize(path)
            elif os.path.isdir(path):
                dir_count += 1
                for root, dirs, files in os.walk(path):
                    file_count += len(files)
                    for file in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, file))
                        except:
                            pass
        
        preview_text = f"""
        📊 Upload Preview
        
        📁 Directories: {dir_count}
        📄 Files: {file_count}
        💾 Total Size: {total_size / 1024 / 1024:.1f} MB
        
        Estimated Upload Time (at 1 MB/s): {total_size / 1024 / 1024:.1f} seconds
        """
        
        QMessageBox.information(self, "Upload Preview", preview_text)
    
    def start_upload(self):
        """Start the enhanced upload process"""
        if not self.validate_inputs():
            return
        
        # Get upload configuration
        protocol = self.protocol_combo.currentText()
        uploader_config = self.get_uploader_config(protocol)
        
        if not uploader_config:
            QMessageBox.warning(self, "Configuration Error", "Failed to get uploader configuration.")
            return
        
        # Get upload options
        max_retries = self.retry_count_spinbox.value()
        ignore_patterns = [p.strip() for p in self.ignore_patterns_input.text().split(',') if p.strip()]
        compress_files = self.compress_files_checkbox.isChecked()
        include_hidden_files = self.include_hidden_files_checkbox.isChecked()
        max_threads = self.max_threads_spinbox.value()
        upload_directory_contents_only = self.upload_directory_contents_checkbox.isChecked()
        
        # Add bandwidth limit if enabled
        if self.bandwidth_limit_checkbox.isChecked():
            uploader_config['bandwidth_limit'] = self.bandwidth_limit_spinbox.value()
        
        # Update UI
        self.start_upload_btn.setEnabled(False)
        self.pause_upload_btn.setEnabled(True)
        self.cancel_upload_btn.setEnabled(True)
        
        # Reset progress
        self.file_progress.clear()
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setMaximum(100)  # Progress in percentage
        
        # Initialize tracking variables for ETA calculation
        self.upload_start_time = time.time()
        self.speed_history = []  # For calculating average speed
        self.eta_label.setText("ETA: Calculating...")
        
        # Create and start worker
        self.upload_worker = EnhancedUploadWorker(
            uploader_config,
            self.selected_files,
            uploader_config.get('remote_dir', ''),
            max_retries,
            ignore_patterns,
            compress_files,
            max_threads,
            include_hidden_files,
            upload_directory_contents_only
        )
        
        # Connect signals
        self.upload_worker.progress_signal.connect(self.update_file_progress)
        self.upload_worker.file_completed_signal.connect(self.file_completed)
        self.upload_worker.all_completed_signal.connect(self.all_completed)
        self.upload_worker.log_signal.connect(self.add_log)
        self.upload_worker.speed_signal.connect(self.update_speed)
        self.upload_worker.overall_progress_signal.connect(self.update_overall_progress)
        
        # Start worker
        self.upload_worker.start()
    
    def pause_upload(self):
        """Pause the current upload"""
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_worker.pause()
            self.pause_upload_btn.setText("▶️ Resume Upload")
            self.pause_upload_btn.clicked.disconnect()
            self.pause_upload_btn.clicked.connect(self.resume_upload)
            self.add_log("info", "Upload paused")
    
    def resume_upload(self):
        """Resume the paused upload"""
        if self.upload_worker:
            self.upload_worker.resume()
            self.pause_upload_btn.setText("⏸️ Pause Upload")
            self.pause_upload_btn.clicked.disconnect()
            self.pause_upload_btn.clicked.connect(self.pause_upload)
            self.add_log("info", "Upload resumed")
    
    def cancel_upload(self):
        """Cancel the current upload"""
        if self.upload_worker and self.upload_worker.isRunning():
            self.add_log("warning", "Canceling upload...")
            self.upload_worker.cancel()
    
    def get_uploader_config(self, protocol):
        """Get uploader configuration for the selected protocol"""
        if protocol not in self.protocol_fields:
            return None
        
        fields = self.protocol_fields[protocol]
        config = {'protocol': protocol}
        
        try:
            if protocol in ["FTP", "FTPS", "SFTP"]:
                config.update({
                    'host': fields['host'].text().strip(),
                    'port': fields['port'].value(),
                    'username': fields['username'].text().strip(),
                    'password': fields['password'].text(),
                    'remote_dir': fields['remote_dir'].text().strip()
                })
            elif protocol == "HTTP/HTTPS":
                headers_text = fields['headers'].toPlainText().strip()
                headers = {}
                if headers_text:
                    try:
                        headers = json.loads(headers_text)
                    except json.JSONDecodeError:
                        # Simple format: "key: value" per line
                        for line in headers_text.split('\n'):
                            if ':' in line:
                                key, value = line.split(':', 1)
                                headers[key.strip()] = value.strip()
                
                config.update({
                    'url': fields['url'].text().strip(),
                    'method': fields['method'].currentText(),
                    'auth_type': fields['auth_type'].currentText(),
                    'username': fields['username'].text().strip(),
                    'password': fields['password'].text(),
                    'headers': headers
                })
            elif protocol == "S3":
                config.update({
                    'access_key': fields['access_key'].text().strip(),
                    'secret_key': fields['secret_key'].text(),
                    'bucket_name': fields['bucket_name'].text().strip(),
                    'region': fields['region'].text().strip(),
                    'remote_dir': fields['remote_dir'].text().strip()
                })
            
            return config
            
        except Exception as e:
            self.add_log("error", f"Failed to get configuration: {str(e)}")
            return None
    
    def validate_inputs(self):
        """Enhanced input validation"""
        protocol = self.protocol_combo.currentText()
        
        if protocol not in self.protocol_fields:
            QMessageBox.warning(self, "Input Error", "Please select a valid protocol.")
            return False
        
        fields = self.protocol_fields[protocol]
        
        # Protocol-specific validation
        if protocol in ["FTP", "FTPS", "SFTP"]:
            if not fields['host'].text().strip():
                QMessageBox.warning(self, "Input Error", "Host address is required.")
                return False
            if not fields['username'].text().strip():
                QMessageBox.warning(self, "Input Error", "Username is required.")
                return False
        elif protocol == "HTTP/HTTPS":
            if not fields['url'].text().strip():
                QMessageBox.warning(self, "Input Error", "URL is required.")
                return False
        elif protocol == "S3":
            if not fields['access_key'].text().strip():
                QMessageBox.warning(self, "Input Error", "Access key is required.")
                return False
            if not fields['secret_key'].text():
                QMessageBox.warning(self, "Input Error", "Secret key is required.")
                return False
            if not fields['bucket_name'].text().strip():
                QMessageBox.warning(self, "Input Error", "Bucket name is required.")
                return False
        
        # Check if files are selected
        if not self.selected_files:
            QMessageBox.warning(self, "Input Error", "No files selected for upload.")
            return False
        
        return True
    
    def update_file_progress(self, file_path, percent):
        """Update individual file progress"""
        self.file_progress[file_path] = percent
        
        # Update file list item
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.text().startswith(file_path):
                display_path = file_path.split('/')[-1] if '/' in file_path else file_path.split('\\')[-1]
                item.setText(f"{display_path} ({percent:.1f}%)")
                break
    
    def update_overall_progress(self, uploaded_bytes, total_bytes, percent):
        """Update overall progress based on actual bytes uploaded"""
        self.overall_progress_bar.setValue(int(percent))
        
        # Format bytes for display
        def format_bytes(bytes_value):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if bytes_value < 1024.0:
                    return f"{bytes_value:.1f} {unit}"
                bytes_value /= 1024.0
            return f"{bytes_value:.1f} TB"
        
        # Update progress bar text
        uploaded_str = format_bytes(uploaded_bytes)
        total_str = format_bytes(total_bytes)
        self.overall_progress_bar.setFormat(f"{percent:.1f}% ({uploaded_str}/{total_str})")
        
        # Update overall progress label with detailed info
        elapsed_time = time.time() - self.upload_start_time
        if elapsed_time > 0:
            avg_speed_bps = uploaded_bytes / elapsed_time
            avg_speed_kbps = avg_speed_bps / 1024
            
            if avg_speed_kbps < 1024:
                speed_str = f"{avg_speed_kbps:.1f} KB/s"
            else:
                speed_str = f"{avg_speed_kbps / 1024:.1f} MB/s"
            
            self.overall_progress_label.setText(f"Overall Progress: {percent:.1f}% - Average Speed: {speed_str}")
        else:
            self.overall_progress_label.setText(f"Overall Progress: {percent:.1f}%")
    
    def file_completed(self, file_path, success, message, speed):
        """Handle file completion"""
        # Update file list item
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.text().startswith(file_path):
                display_path = file_path.split('/')[-1] if '/' in file_path else file_path.split('\\')[-1]
                status = "✅" if success else "❌"
                item.setText(f"{display_path} {status} ({speed:.1f} KB/s)")
                
                if success:
                    item.setForeground(QColor("green"))
                else:
                    item.setForeground(QColor("red"))
                break
    
    def all_completed(self, success, message, successful, failed):
        """Handle upload completion"""
        # Reset UI
        self.start_upload_btn.setEnabled(True)
        self.pause_upload_btn.setEnabled(False)
        self.cancel_upload_btn.setEnabled(False)
        
        # Reset pause button if needed
        self.pause_upload_btn.setText("⏸️ Pause Upload")
        try:
            self.pause_upload_btn.clicked.disconnect()
        except:
            pass
        self.pause_upload_btn.clicked.connect(self.pause_upload)
        
        # Final progress update
        if success:
            self.overall_progress_bar.setValue(100)
            self.eta_label.setText("ETA: Complete")
        
        # Calculate total upload time and final statistics
        total_time = time.time() - self.upload_start_time
        if hasattr(self.upload_worker, 'total_bytes') and total_time > 0:
            avg_speed = (self.upload_worker.total_bytes / 1024) / total_time  # KB/s
            if avg_speed < 1024:
                speed_info = f"{avg_speed:.1f} KB/s"
            else:
                speed_info = f"{avg_speed / 1024:.1f} MB/s"
            
            time_str = f"{total_time/60:.1f}m" if total_time >= 60 else f"{total_time:.1f}s"
            detailed_message = f"{message} in {time_str} (avg: {speed_info}) - ✅ {successful} succeeded, ❌ {failed} failed"
        else:
            detailed_message = f"{message} - ✅ {successful} succeeded, ❌ {failed} failed"
        
        # Update status
        self.statusBar().showMessage(detailed_message)
        self.add_log("info" if success else "error", detailed_message)
        
        # Show notification
        if self.notification_toggle.isChecked():
            if hasattr(self, 'tray_icon'):
                self.tray_icon.showMessage(
                    "📤 Upload Completed",
                    detailed_message,
                    QSystemTrayIcon.Information,
                    5000
                )
    
    def update_speed(self, speed_kbps):
        """Update upload speed display with improved ETA calculation"""
        # Add current speed to history for average calculation
        self.speed_history.append(speed_kbps)
        
        # Keep only last 10 speed measurements for average
        if len(self.speed_history) > 10:
            self.speed_history.pop(0)
        
        # Calculate average speed
        avg_speed = sum(self.speed_history) / len(self.speed_history) if self.speed_history else 0
        
        # Display current speed
        if avg_speed < 1024:
            self.speed_label.setText(f"Upload Speed: {avg_speed:.1f} KB/s (avg)")
        else:
            self.speed_label.setText(f"Upload Speed: {avg_speed / 1024:.1f} MB/s (avg)")
        
        # Calculate improved ETA based on actual progress and average speed
        if avg_speed > 0 and hasattr(self.upload_worker, 'total_bytes') and hasattr(self.upload_worker, 'uploaded_bytes'):
            remaining_bytes = self.upload_worker.total_bytes - self.upload_worker.uploaded_bytes
            if remaining_bytes > 0:
                eta_seconds = (remaining_bytes / 1024) / avg_speed  # remaining KB / KB/s
                
                # Format ETA display
                if eta_seconds < 60:
                    self.eta_label.setText(f"ETA: {eta_seconds:.0f}s")
                elif eta_seconds < 3600:
                    minutes = eta_seconds / 60
                    self.eta_label.setText(f"ETA: {minutes:.0f}m")
                elif eta_seconds < 86400:  # Less than a day
                    hours = eta_seconds / 3600
                    minutes = (eta_seconds % 3600) / 60
                    self.eta_label.setText(f"ETA: {hours:.0f}h {minutes:.0f}m")
                else:  # More than a day
                    days = eta_seconds / 86400
                    hours = (eta_seconds % 86400) / 3600
                    self.eta_label.setText(f"ETA: {days:.0f}d {hours:.0f}h")
            else:
                self.eta_label.setText("ETA: Complete")
        else:
            # Fallback for initial calculation when worker data isn't available yet
            current_progress = self.overall_progress_bar.value()
            if current_progress > 0 and current_progress < 100:
                elapsed_time = time.time() - self.upload_start_time
                if elapsed_time > 0:
                    estimated_total_time = elapsed_time * (100 / current_progress)
                    remaining_time = estimated_total_time - elapsed_time
                    
                    if remaining_time < 60:
                        self.eta_label.setText(f"ETA: {remaining_time:.0f}s")
                    elif remaining_time < 3600:
                        self.eta_label.setText(f"ETA: {remaining_time/60:.0f}m")
                    else:
                        self.eta_label.setText(f"ETA: {remaining_time/3600:.1f}h")
                else:
                    self.eta_label.setText("ETA: Calculating...")
            else:
                self.eta_label.setText("ETA: Calculating...")
    
    def test_connection(self):
        """Test connection to the remote server"""
        protocol = self.protocol_combo.currentText()
        config = self.get_uploader_config(protocol)
        
        if not config:
            QMessageBox.warning(self, "Configuration Error", "Please check your connection settings.")
            return
        
        # Disable test button during test
        self.test_connection_btn.setEnabled(False)
        self.test_connection_btn.setText("Testing...")
        self.statusBar().showMessage("Testing connection...")
        
        # Create test worker thread
        class TestWorker(QThread):
            result_signal = pyqtSignal(bool, str)
            
            def __init__(self, config):
                super().__init__()
                self.config = config
            
            def run(self):
                worker = EnhancedUploadWorker(self.config, [], "", 0, [], False, 1)
                uploader = worker.create_uploader()
                
                if uploader:
                    success, message = uploader.connect()
                    if success:
                        uploader.disconnect()
                    self.result_signal.emit(success, message)
                else:
                    self.result_signal.emit(False, "Failed to create uploader")
        
        def on_test_complete(success, message):
            self.test_connection_btn.setEnabled(True)
            self.test_connection_btn.setText("Test Connection")
            
            if success:
                QMessageBox.information(self, "Connection Test", "✅ Connection successful!")
                self.add_log("info", f"Connection test successful using {protocol}")
                self.statusBar().showMessage("Connection test successful")
            else:
                QMessageBox.critical(self, "Connection Test", f"❌ Connection failed:\n{message}")
                self.add_log("error", f"Connection test failed using {protocol}: {message}")
                self.statusBar().showMessage("Connection test failed")
        
        self.test_worker = TestWorker(config)
        self.test_worker.result_signal.connect(on_test_complete)
        self.test_worker.start()
    
    def add_log(self, level, message):
        """Enhanced logging with filtering"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Determine color and icon
        if level == "error":
            color = "#ff4444"
            icon = "❌"
        elif level == "warning":
            color = "#ff9900"
            icon = "⚠️"
        elif level == "info":
            color = "#00aa00" if "success" in message.lower() else "#ffffff"
            icon = "ℹ️"
        else:
            color = "#ffffff"
            icon = "📝"
        
        # Format log entry
        log_entry = f'<span style="color: #888888;">[{timestamp}]</span> <span style="color: {color};">{icon} {message}</span>'
        
        # Apply filter
        current_filter = self.log_level_combo.currentText()
        if current_filter != "All":
            if current_filter.lower() != level.lower():
                return
        
        # Apply search filter
        search_text = self.search_log_input.text().lower()
        if search_text and search_text not in message.lower():
            return
        
        # Add to display
        self.log_display.append(log_entry)
        self.log_display.moveCursor(QTextCursor.End)
        
        # Log to file if enabled
        if self.log_to_file_checkbox.isChecked():
            logger.log(
                logging.ERROR if level == "error" else 
                logging.WARNING if level == "warning" else 
                logging.INFO,
                message
            )
    
    def filter_logs(self, level):
        """Filter logs by level"""
        # This would require storing all log entries and re-filtering
        # For now, it affects future log entries
        pass
    
    def search_logs(self, text):
        """Search in logs"""
        # This would require storing all log entries and re-filtering
        # For now, it affects future log entries
        pass
    
    def clear_log(self):
        """Clear log display"""
        self.log_display.clear()
    
    def save_log(self):
        """Save log to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Log", 
            f"upload_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 
            "Text Files (*.txt);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    # Remove HTML formatting for plain text
                    import re
                    plain_text = re.sub(r'<[^>]+>', '', self.log_display.toPlainText())
                    f.write(plain_text)
                
                self.statusBar().showMessage(f"Log saved to {file_path}")
                self.add_log("info", f"Log saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save log: {str(e)}")
    
    def export_statistics(self):
        """Export upload statistics"""
        # TODO: Implement statistics export
        QMessageBox.information(self, "Export Statistics", "Statistics export will be implemented in a future version.")
    
    def reset_settings(self):
        """Reset all settings to default"""
        reply = QMessageBox.question(
            self, 
            "Reset Settings", 
            "Are you sure you want to reset all settings to default?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.settings.clear()
            QMessageBox.information(self, "Reset Complete", "Settings have been reset. Please restart the application.")
    
    def save_current_server(self):
        """Save current server configuration"""
        server_name = self.server_name_input.text().strip()
        
        if not server_name:
            QMessageBox.warning(self, "Input Error", "Please provide a server name.")
            return
        
        protocol = self.protocol_combo.currentText()
        config = self.get_uploader_config(protocol)
        
        if not config:
            QMessageBox.warning(self, "Configuration Error", "Please check your connection settings.")
            return
        
        # Save to settings
        servers = self.load_servers_from_settings()
        servers[server_name] = {
            'name': server_name,
            'protocol': protocol,
            'config': config
        }
        
        self.save_servers_to_settings(servers)
        self.update_server_list(servers)
        
        self.statusBar().showMessage(f"Server '{server_name}' saved")
        self.add_log("info", f"Saved server configuration: {server_name}")
    
    def load_server(self, item):
        """Load saved server configuration"""
        server_name = item.text()
        servers = self.load_servers_from_settings()
        
        if server_name in servers:
            server_data = servers[server_name]
            protocol = server_data['protocol']
            config = server_data['config']
            
            # Set protocol first
            self.protocol_combo.setCurrentText(protocol)
            
            # Set configuration fields
            if protocol in self.protocol_fields:
                fields = self.protocol_fields[protocol]
                
                if protocol in ["FTP", "FTPS", "SFTP"]:
                    fields['host'].setText(config.get('host', ''))
                    fields['port'].setValue(config.get('port', 21))
                    fields['username'].setText(config.get('username', ''))
                    fields['password'].setText(config.get('password', ''))
                    fields['remote_dir'].setText(config.get('remote_dir', ''))
                elif protocol == "HTTP/HTTPS":
                    fields['url'].setText(config.get('url', ''))
                    fields['method'].setCurrentText(config.get('method', 'POST'))
                    fields['auth_type'].setCurrentText(config.get('auth_type', 'none'))
                    fields['username'].setText(config.get('username', ''))
                    fields['password'].setText(config.get('password', ''))
                    headers = config.get('headers', {})
                    fields['headers'].setPlainText(json.dumps(headers, indent=2) if headers else '')
                elif protocol == "S3":
                    fields['access_key'].setText(config.get('access_key', ''))
                    fields['secret_key'].setText(config.get('secret_key', ''))
                    fields['bucket_name'].setText(config.get('bucket_name', ''))
                    fields['region'].setText(config.get('region', 'us-east-1'))
                    fields['remote_dir'].setText(config.get('remote_dir', ''))
            
            self.server_name_input.setText(server_name)
            self.add_log("info", f"Loaded server configuration: {server_name}")
    
    def load_saved_servers(self):
        """Load saved servers from settings"""
        servers = self.load_servers_from_settings()
        self.update_server_list(servers)
        
    def update_server_list(self, servers):
        """Update the server list widget"""
        self.server_list.clear()
        for server_name in sorted(servers.keys()):
            self.server_list.addItem(server_name)
            
    def delete_server(self):
        """Delete selected server"""
        selected_items = self.server_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Delete Error", "Please select a server to delete.")
            return
            
        server_name = selected_items[0].text()
        
        reply = QMessageBox.question(
            self, 
            "Delete Server", 
            f"Are you sure you want to delete '{server_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            servers = self.load_servers_from_settings()
            if server_name in servers:
                del servers[server_name]
                self.save_servers_to_settings(servers)
                self.update_server_list(servers)
                self.add_log("info", f"Deleted server: {server_name}")
    
    def load_servers_from_settings(self) -> Dict:
        """Load all servers from QSettings"""
        servers = self.settings.value("servers", {})
        return servers if isinstance(servers, dict) else {}

    def save_servers_to_settings(self, servers: Dict):
        """Save servers to QSettings"""
        self.settings.setValue("servers", servers)
        self.settings.sync()  # Ensure immediate save

    def closeEvent(self, event):
        """Handle window close event"""
        # Save window geometry
        self.settings.setValue("geometry", self.saveGeometry())
        
        # Check if there are active uploads
        if self.upload_worker and self.upload_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Upload in Progress",
                "There is an active upload. Do you want to:\n"
                "• Stop upload and exit completely\n"
                "• Minimize to tray and continue upload",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Cancel
            )
            
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Yes:
                self.cancel_upload()
                self.quit_application()
                event.accept()
                return
            # If No, continue to tray logic below
        
        # Ask user what they want to do
        if self.settings.value("minimize_to_tray", True, type=bool):
            reply = QMessageBox.question(
                self,
                "Close Application",
                "What would you like to do?\n\n"
                "• Click 'Yes' to minimize to system tray\n"
                "• Click 'No' to exit completely",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Yes:
                # Minimize to tray
                event.ignore()
                self.hide()
                if hasattr(self, 'tray_icon'):
                    self.tray_icon.showMessage(
                        "📤 Uploader Running",
                        "The application is minimized to system tray.\n"
                        "Right-click the tray icon to exit completely.",
                        QSystemTrayIcon.Information,
                        3000
                    )
                return
            else:
                # Exit completely
                self.quit_application()
                event.accept()
                return
        else:
            # Exit completely if minimize to tray is disabled
            self.quit_application()
            event.accept()
    
    def resizeEvent(self, event):
        """Handle window resize event"""
        super().resizeEvent(event)
        self.settings.setValue("geometry", self.saveGeometry())

    def quit_application(self):
        """Completely quit the application"""
        import sys
        
        # Save session if enabled
        if self.settings.value("auto_save_session", True, type=bool):
            self.save_session()
        
        # Ensure all settings are saved
        self.settings.sync()
        
        # Stop any running workers
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_worker.should_cancel = True
            self.upload_worker.terminate()
            if not self.upload_worker.wait(5000):
                self.upload_worker.quit()
        
        # Hide tray icon
        if hasattr(self, 'tray_icon'):
            self.tray_icon.hide()
        
        # Quit application
        QApplication.instance().quit()
        sys.exit(0)

    def save_session(self):
        """Save current session (selected files, etc.)"""
        session_data = {
            'selected_files': self.selected_files,
            'current_tab': self.tab_widget.currentIndex()
        }
        self.settings.setValue("session", session_data)
        self.add_log("info", "Session saved.")

    def load_session(self):
        """Load last session"""
        if not self.settings.value("restore_session", True, type=bool):
            return
            
        session_data = self.settings.value("session", None)
        if session_data and isinstance(session_data, dict):
            self.add_dropped_files(session_data.get('selected_files', []))
            self.tab_widget.setCurrentIndex(session_data.get('current_tab', 0))
            self.add_log("info", "Session restored.")
    
    # ===========================
    # SERVER BROWSER METHODS
    # ===========================
    
    def connect_for_browsing(self):
        """Connect to server for browsing files"""
        try:
            # Get current connection settings
            protocol = self.protocol_combo.currentText()
            config = self.get_uploader_config(protocol)
            
            if not config:
                QMessageBox.warning(self, "Configuration Error", 
                                  "Please configure connection settings in the Connection tab first.")
                return
            
            # Create uploader instance
            uploader_class = self.get_uploader_class(protocol)
            if not uploader_class:
                QMessageBox.warning(self, "Protocol Error", 
                                  f"Protocol {protocol} is not supported for browsing.")
                return
            
            # Update UI to show connecting state
            self.browser_connect_btn.setText("🔗 Connecting...")
            self.browser_connect_btn.setEnabled(False)
            
            # Connect
            self.current_browser_connection = uploader_class(**config)
            success, message = self.current_browser_connection.connect()
            
            if success:
                self.browser_connected = True
                self.browser_connect_btn.setText("🔌 Disconnect")
                self.browser_connect_btn.setEnabled(True)
                self.browser_connect_btn.clicked.disconnect()
                self.browser_connect_btn.clicked.connect(self.disconnect_browser)
                
                # Enable browser controls
                self.browser_refresh_btn.setEnabled(True)
                self.browser_navigate_btn.setEnabled(True)
                self.browser_up_btn.setEnabled(True)
                self.create_folder_btn.setEnabled(True)
                self.upload_to_current_btn.setEnabled(True)
                
                self.add_log("success", f"Connected to server for browsing: {message}")
                
                # Load root directory
                self.current_remote_path = "/"
                self.browser_path_input.setText("/")
                self.refresh_browser()
                
            else:
                self.browser_connected = False
                self.browser_connect_btn.setText("🔗 Connect to Browse")
                self.browser_connect_btn.setEnabled(True)
                self.add_log("error", f"Failed to connect for browsing: {message}")
                QMessageBox.critical(self, "Connection Failed", message)
                
        except Exception as e:
            self.browser_connected = False
            self.browser_connect_btn.setText("🔗 Connect to Browse")
            self.browser_connect_btn.setEnabled(True)
            self.add_log("error", f"Browser connection error: {str(e)}")
    
    def disconnect_browser(self):
        """Disconnect browser connection"""
        try:
            if self.current_browser_connection:
                self.current_browser_connection.disconnect()
            
            self.browser_connected = False
            self.current_browser_connection = None
            
            # Update UI
            self.browser_connect_btn.setText("🔗 Connect to Browse")
            self.browser_connect_btn.clicked.disconnect()
            self.browser_connect_btn.clicked.connect(self.connect_for_browsing)
            
            # Disable browser controls
            self.browser_refresh_btn.setEnabled(False)
            self.browser_navigate_btn.setEnabled(False)
            self.browser_up_btn.setEnabled(False)
            self.create_folder_btn.setEnabled(False)
            self.upload_to_current_btn.setEnabled(False)
            self.download_selected_btn.setEnabled(False)
            self.delete_selected_btn.setEnabled(False)
            
            # Clear tree
            self.server_file_tree.clear()
            self.selected_info_label.setText("Disconnected")
            
            self.add_log("info", "Browser disconnected")
            
        except Exception as e:
            self.add_log("error", f"Error disconnecting browser: {str(e)}")
    
    def refresh_browser(self):
        """Refresh current directory listing"""
        if not self.browser_connected or not self.current_browser_connection:
            return
        
        try:
            self.server_file_tree.clear()
            self.browser_progress_label.setText("Loading directory...")
            
            success, items = self.current_browser_connection.list_directory(self.current_remote_path)
            
            if success:
                # Sort items: directories first, then files
                items.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))
                
                for item in items:
                    tree_item = QTreeWidgetItem()
                    
                    # Set item data
                    name = item['name']
                    item_type = item['type']
                    size = self.format_file_size(item['size']) if item_type == 'file' else ''
                    modified = item.get('modified', '')
                    permissions = item.get('permissions', '')
                    
                    # Set icon based on type
                    if item_type == 'directory':
                        icon = "📁"
                        name = f"{icon} {name}"
                    else:
                        icon = self.get_file_icon(name)
                        name = f"{icon} {name}"
                    
                    tree_item.setText(0, name)
                    tree_item.setText(1, item_type.title())
                    tree_item.setText(2, size)
                    tree_item.setText(3, modified)
                    tree_item.setText(4, permissions)
                    
                    # Store full path in item data
                    tree_item.setData(0, Qt.UserRole, item['full_path'])
                    tree_item.setData(1, Qt.UserRole, item_type)
                    
                    self.server_file_tree.addTopLevelItem(tree_item)
                
                # Resize columns to content
                for i in range(5):
                    self.server_file_tree.resizeColumnToContents(i)
                
                self.browser_progress_label.setText(f"Loaded {len(items)} items")
                self.add_log("info", f"Browsed directory: {self.current_remote_path} ({len(items)} items)")
                
            else:
                self.browser_progress_label.setText("Failed to load directory")
                self.add_log("error", f"Failed to browse directory: {self.current_remote_path}")
                
        except Exception as e:
            self.browser_progress_label.setText("Error loading directory")
            self.add_log("error", f"Browser refresh error: {str(e)}")
    
    def navigate_to_path(self):
        """Navigate to specified path"""
        new_path = self.browser_path_input.text().strip()
        if not new_path:
            return
            
        self.current_remote_path = new_path
        self.refresh_browser()
    
    def go_up_directory(self):
        """Go up one directory level"""
        if self.current_remote_path == '/':
            return
            
        parent_path = '/'.join(self.current_remote_path.rstrip('/').split('/')[:-1])
        if not parent_path:
            parent_path = '/'
            
        self.current_remote_path = parent_path
        self.browser_path_input.setText(parent_path)
        self.refresh_browser()
    
    def on_server_item_double_click(self, item, column):
        """Handle double click on server item"""
        item_type = item.data(1, Qt.UserRole)
        full_path = item.data(0, Qt.UserRole)
        
        if item_type == 'directory':
            # Navigate into directory
            self.current_remote_path = full_path
            self.browser_path_input.setText(full_path)
            self.refresh_browser()
        else:
            # For files, show info or download option
            self.show_file_info(item)
    
    def show_server_context_menu(self, position):
        """Show context menu for server files"""
        item = self.server_file_tree.itemAt(position)
        if not item:
            return
            
        menu = QMenu(self)
        
        # Download action
        download_action = menu.addAction("💾 Download")
        download_action.triggered.connect(lambda: self.download_single_item(item))
        
        # Delete action
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ Delete")
        delete_action.triggered.connect(lambda: self.delete_single_item(item))
        delete_action.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        
        # Show info action
        menu.addSeparator()
        info_action = menu.addAction("ℹ️ Properties")
        info_action.triggered.connect(lambda: self.show_file_info(item))
        
        menu.exec_(self.server_file_tree.mapToGlobal(position))
    
    def download_selected_files(self):
        """Download selected files from server"""
        selected_items = self.server_file_tree.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select files or folders to download.")
            return
            
        download_path = self.download_folder_input.text().strip()
        if not download_path:
            download_path = QFileDialog.getExistingDirectory(self, "Select Download Folder")
            if not download_path:
                return
            self.download_folder_input.setText(download_path)
        
        # Start download process
        self.start_bulk_download(selected_items, download_path)
    
    def download_single_item(self, item):
        """Download a single item"""
        download_path = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if not download_path:
            return
            
        self.start_bulk_download([item], download_path)
    
    def start_bulk_download(self, items, download_path):
        """Start downloading multiple items"""
        if not self.current_browser_connection:
            return
            
        try:
            total_items = len(items)
            completed = 0
            
            self.browser_progress_bar.setMaximum(total_items)
            self.browser_progress_bar.setValue(0)
            
            for item in items:
                full_path = item.data(0, Qt.UserRole)
                item_type = item.data(1, Qt.UserRole)
                name = item.text(0).replace('📁 ', '').replace('📄 ', '').replace('🗄️ ', '')
                
                local_file_path = os.path.join(download_path, name)
                
                if item_type == 'file':
                    self.browser_progress_label.setText(f"Downloading: {name}")
                    
                    success, message = self.current_browser_connection.download_file(
                        full_path, local_file_path
                    )
                    
                    if success:
                        self.add_log("success", f"Downloaded: {name}")
                    else:
                        self.add_log("error", f"Failed to download {name}: {message}")
                
                completed += 1
                self.browser_progress_bar.setValue(completed)
                
            self.browser_progress_label.setText(f"Download completed: {completed}/{total_items} items")
            
        except Exception as e:
            self.add_log("error", f"Download error: {str(e)}")
    
    def upload_to_current_location(self):
        """Upload files to current remote directory"""
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Upload")
        if not files:
            return
            
        if not self.current_browser_connection:
            QMessageBox.warning(self, "Not Connected", "Please connect to server first.")
            return
        
        self.start_bulk_upload_to_current(files)
    
    def start_bulk_upload_to_current(self, files):
        """Upload files to current directory"""
        try:
            total_files = len(files)
            completed = 0
            
            self.browser_progress_bar.setMaximum(total_files)
            self.browser_progress_bar.setValue(0)
            
            for file_path in files:
                filename = os.path.basename(file_path)
                remote_path = f"{self.current_remote_path.rstrip('/')}/{filename}"
                
                self.browser_progress_label.setText(f"Uploading: {filename}")
                
                success, message = self.current_browser_connection.upload_file(file_path, remote_path)
                
                if success:
                    self.add_log("success", f"Uploaded: {filename}")
                else:
                    self.add_log("error", f"Failed to upload {filename}: {message}")
                
                completed += 1
                self.browser_progress_bar.setValue(completed)
            
            self.browser_progress_label.setText(f"Upload completed: {completed}/{total_files} files")
            
            # Refresh browser to show new files
            self.refresh_browser()
            
        except Exception as e:
            self.add_log("error", f"Upload error: {str(e)}")
    
    def create_new_folder(self):
        """Create new folder on server"""
        if not self.current_browser_connection:
            return
            
        folder_name, ok = QInputDialog.getText(self, "Create Folder", "Enter folder name:")
        if not ok or not folder_name.strip():
            return
            
        folder_name = folder_name.strip()
        remote_path = f"{self.current_remote_path.rstrip('/')}/{folder_name}"
        
        try:
            success, message = self.current_browser_connection.create_directory(remote_path)
            
            if success:
                self.add_log("success", f"Created folder: {folder_name}")
                self.refresh_browser()  # Refresh to show new folder
            else:
                self.add_log("error", f"Failed to create folder: {message}")
                QMessageBox.critical(self, "Create Folder Failed", message)
                
        except Exception as e:
            self.add_log("error", f"Create folder error: {str(e)}")
    
    def delete_selected_files(self):
        """Delete selected files from server"""
        selected_items = self.server_file_tree.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select files or folders to delete.")
            return
        
        # Confirm deletion
        item_names = [item.text(0) for item in selected_items]
        result = QMessageBox.warning(
            self, "Confirm Deletion", 
            f"Are you sure you want to delete {len(selected_items)} item(s)?\n\n" + 
            "\n".join(item_names[:5]) + ("..." if len(item_names) > 5 else ""),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if result == QMessageBox.Yes:
            self.perform_bulk_delete(selected_items)
    
    def delete_single_item(self, item):
        """Delete a single item"""
        item_name = item.text(0)
        result = QMessageBox.warning(
            self, "Confirm Deletion", 
            f"Are you sure you want to delete '{item_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if result == QMessageBox.Yes:
            self.perform_bulk_delete([item])
    
    def perform_bulk_delete(self, items):
        """Perform deletion of multiple items"""
        if not self.current_browser_connection:
            return
            
        try:
            total_items = len(items)
            completed = 0
            
            self.browser_progress_bar.setMaximum(total_items)
            self.browser_progress_bar.setValue(0)
            
            for item in items:
                full_path = item.data(0, Qt.UserRole)
                name = item.text(0)
                
                self.browser_progress_label.setText(f"Deleting: {name}")
                
                success, message = self.current_browser_connection.delete_file(full_path)
                
                if success:
                    self.add_log("success", f"Deleted: {name}")
                else:
                    self.add_log("error", f"Failed to delete {name}: {message}")
                
                completed += 1
                self.browser_progress_bar.setValue(completed)
                
            self.browser_progress_label.setText(f"Deletion completed: {completed}/{total_items} items")
            
            # Refresh browser to update listing
            self.refresh_browser()
            
        except Exception as e:
            self.add_log("error", f"Delete error: {str(e)}")
    
    def browse_download_folder(self):
        """Browse for download folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder:
            self.download_folder_input.setText(folder)
    
    def show_file_info(self, item):
        """Show detailed information about selected file"""
        if not self.current_browser_connection:
            return
            
        full_path = item.data(0, Qt.UserRole)
        
        try:
            success, info = self.current_browser_connection.get_file_info(full_path)
            
            if success:
                info_text = f"""
<b>Name:</b> {info.get('name', 'Unknown')}<br>
<b>Type:</b> {info.get('type', 'Unknown').title()}<br>
<b>Size:</b> {self.format_file_size(info.get('size', 0))}<br>
<b>Path:</b> {info.get('full_path', 'Unknown')}<br>
<b>Modified:</b> {info.get('modified', 'Unknown')}<br>
<b>Permissions:</b> {info.get('permissions', 'Unknown')}
                """
                self.selected_info_label.setText(info_text)
            else:
                self.selected_info_label.setText("Failed to get file information")
                
        except Exception as e:
            self.selected_info_label.setText(f"Error: {str(e)}")
    
    def get_file_icon(self, filename):
        """Get icon for file based on extension"""
        ext = os.path.splitext(filename.lower())[1]
        
        icons = {
            '.txt': '📝', '.md': '📝', '.doc': '📝', '.docx': '📝',
            '.pdf': '📕', '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', 
            '.gif': '🖼️', '.bmp': '🖼️', '.mp3': '🎵', '.mp4': '🎬',
            '.avi': '🎬', '.mov': '🎬', '.zip': '🗄️', '.rar': '🗄️',
            '.tar': '🗄️', '.gz': '🗄️', '.py': '🐍', '.js': '💛',
            '.html': '🌐', '.css': '🎨', '.json': '📋'
        }
        
        return icons.get(ext, '📄')
    
    def format_file_size(self, size_bytes):
        """Format file size in human readable format"""
        if not size_bytes:
            return '0 B'
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def get_uploader_class(self, protocol):
        """Get the appropriate uploader class for protocol"""
        from models.protocols.ftp import FTPUploader
        from models.protocols.sftp import SFTPUploader
        
        protocol_classes = {
            'FTP': FTPUploader,
            'FTPS': FTPUploader,
            'SFTP': SFTPUploader,
        }
        
        return protocol_classes.get(protocol)
