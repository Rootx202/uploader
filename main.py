"""
Enhanced Main Application Entry Point
Features:
- Secure password migration on startup
- Better error handling
- Performance monitoring
- Security checks
"""

import sys
import os
import logging
import time
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont

# Import our modules
from models.ui import EnhancedMainWindow
from models.security import PasswordManager, migrate_existing_passwords

class EnhancedApplication(QApplication):
    """Enhanced QApplication with security and performance features"""
    
    def __init__(self, argv):
        super().__init__(argv)
        
        # Application metadata
        self.setApplicationName("Enhanced Remote File Uploader")
        self.setApplicationVersion("2.1.0")
        self.setOrganizationName("YourOrganization")
        self.setOrganizationDomain("yourcompany.com")
        
        # Setup logging
        self.setup_logging()
        
        # Security initialization
        self.password_manager = PasswordManager()
        
        # Performance monitoring
        self.startup_time = time.time()
        
        # Setup application properties
        self.setup_application()
    
    def setup_logging(self):
        """Enhanced logging configuration"""
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Configure detailed logging
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler("logs/uploader.log"),
                logging.FileHandler("logs/uploader_debug.log", mode='w'),  # Fresh debug log each run
                logging.StreamHandler()
            ]
        )
        
        # Set specific log levels for different components
        logging.getLogger("paramiko").setLevel(logging.WARNING)
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 50)
        self.logger.info("Enhanced Remote File Uploader Starting...")
        self.logger.info("=" * 50)
    
    def setup_application(self):
        """Setup application-wide properties"""
        # Set application style
        self.setStyle('Fusion')  # Better cross-platform consistency
        
        # Enable high DPI support
        self.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        self.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    def perform_security_checks(self):
        """Perform security checks and migrations"""
        try:
            self.logger.info("Performing security checks...")
            
            # Migrate existing passwords if needed
            migrated_count = migrate_existing_passwords()
            if migrated_count > 0:
                self.logger.info(f"Successfully migrated {migrated_count} passwords to secure storage")
                
                # Show user notification
                QMessageBox.information(
                    None,
                    "Security Enhancement",
                    f"🔐 Security Upgrade Complete!\n\n"
                    f"We've securely encrypted {migrated_count} saved passwords.\n"
                    f"Your credentials are now better protected.\n\n"
                    f"No action needed from you - everything will work as before!"
                )
            
            # Check for security issues
            self.check_permissions()
            
            self.logger.info("Security checks completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Security check failed: {e}")
            QMessageBox.warning(
                None,
                "Security Check Warning", 
                f"Some security checks failed:\n{e}\n\nThe application will continue but may be less secure."
            )
            return False
    
    def check_permissions(self):
        """Check file system permissions"""
        # Check write permissions for logs
        test_file = Path("logs/permission_test.tmp")
        try:
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            self.logger.warning(f"Limited write permissions detected: {e}")
    
    def show_splash_screen(self):
        """Show enhanced splash screen"""
        # Create simple splash screen
        splash = QSplashScreen()
        splash.showMessage(
            "Enhanced Remote File Uploader v2.1\n"
            "🔐 Initializing Security...\n"
            "⚡ Loading Components...",
            Qt.AlignCenter | Qt.AlignBottom,
            Qt.white
        )
        splash.show()
        
        # Process events to show splash
        self.processEvents()
        
        return splash
    
    def startup_performance_log(self):
        """Log startup performance metrics"""
        startup_duration = time.time() - self.startup_time
        self.logger.info(f"Application startup completed in {startup_duration:.2f} seconds")
        
        # Log system info
        try:
            import psutil
            memory_info = psutil.virtual_memory()
            self.logger.info(f"System Memory: {memory_info.total / (1024**3):.1f}GB total, {memory_info.percent}% used")
        except ImportError:
            self.logger.info("psutil not available - install for system monitoring")

def check_dependencies():
    """Check for required dependencies and suggest installation"""
    missing_deps = []
    optional_deps = []
    
    # Required dependencies
    required = {
        'PyQt5': 'PyQt5>=5.15.0',
        'paramiko': 'paramiko>=2.7.0',
        'requests': 'requests>=2.25.0',
        'cryptography': 'cryptography>=3.4.0',
    }
    
    # Optional dependencies
    optional = {
        'psutil': 'psutil>=5.8.0',
        'keyring': 'keyring>=23.0.0',
        'qrcode': 'qrcode>=7.3.0',
    }
    
    for module, requirement in required.items():
        try:
            __import__(module.replace('-', '_'))
        except ImportError:
            missing_deps.append(requirement)
    
    for module, requirement in optional.items():
        try:
            __import__(module.replace('-', '_'))
        except ImportError:
            optional_deps.append(requirement)
    
    if missing_deps:
        print("❌ Missing required dependencies:")
        for dep in missing_deps:
            print(f"   - {dep}")
        print("\\nPlease install with: pip install " + " ".join(missing_deps))
        return False
    
    if optional_deps:
        print("⚠️  Missing optional dependencies (for enhanced features):")
        for dep in optional_deps:
            print(f"   - {dep}")
        print("\\nInstall with: pip install " + " ".join(optional_deps))
    
    return True

def main():
    """Enhanced main function"""
    print("🚀 Enhanced Remote File Uploader v2.1")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        print("\\n❌ Please install missing dependencies and try again.")
        return 1
    
    # Create application
    app = EnhancedApplication(sys.argv)
    
    # Show splash screen
    splash = app.show_splash_screen()
    
    try:
        # Perform security setup
        splash.showMessage(
            "🔐 Performing security checks...",
            Qt.AlignCenter | Qt.AlignBottom,
            Qt.white
        )
        app.processEvents()
        
        security_ok = app.perform_security_checks()
        
        # Create main window
        splash.showMessage(
            "⚡ Loading main interface...",
            Qt.AlignCenter | Qt.AlignBottom,
            Qt.white
        )
        app.processEvents()
        
        window = EnhancedMainWindow()
        
        # Close splash and show main window
        splash.finish(window)
        window.show()
        
        # Log performance metrics
        app.startup_performance_log()
        
        # Show security status
        if security_ok:
            app.logger.info("🔐 Application started with enhanced security")
        else:
            app.logger.warning("⚠️  Application started with limited security")
        
        # Run application
        return app.exec_()
        
    except Exception as e:
        app.logger.critical(f"Critical error during startup: {e}")
        QMessageBox.critical(
            None,
            "Startup Error",
            f"A critical error occurred during startup:\\n{e}\\n\\n"
            f"Please check the logs for more details."
        )
        return 1
        
    finally:
        if 'splash' in locals():
            splash.close()

if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    # Handle high DPI displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Run application
    try:
        exit_code = main()
        print(f"\\n👋 Application closed with exit code: {exit_code}")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\\n👋 Application interrupted")
        sys.exit(0)