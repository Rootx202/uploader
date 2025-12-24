# Enhanced Remote File Uploader

![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.7+-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

A powerful PyQt5-based desktop application for uploading files to remote servers using multiple protocols with enhanced security features.

## Features

- **Multiple Protocols**: FTP, SFTP, HTTP/HTTPS, AWS S3, Google Drive, Dropbox, WebDAV, OneDrive
- **Secure Storage**: Encrypted password management using Fernet encryption
- **Modern UI**: Drag-and-drop support, dark mode, system tray integration
- **Multi-threading**: Upload multiple files concurrently with progress tracking
- **Auto-migration**: Automatically encrypts existing plaintext passwords

## Requirements

- Python 3.7+
- PyQt5, paramiko, boto3, requests, cryptography
- Optional: keyring, psutil, qrcode

## Installation

```bash
# Clone the repository
git clone https://github.com/Rootx202/uploader.git
cd uploader

# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. Select protocol from dropdown
2. Enter connection details (host, port, credentials)
3. Browse or drag-and-drop files
4. Click Upload and monitor progress

## Project Structure

```
uploader/
├── main.py              # Application entry point
├── requirements.txt     # Dependencies
├── models/
│   ├── ui.py           # Main UI window
│   ├── worker.py       # Upload worker thread
│   ├── security.py     # Password encryption
│   └── protocols/      # Protocol implementations
└── logs/               # Application logs
```

## Security

- Passwords encrypted using Fernet (AES-128)
- Automatic migration of plaintext passwords on first run
- Secure credential storage with keyring integration
- No sensitive data in logs

## Troubleshooting

**Missing dependencies:**
```bash
pip install -r requirements.txt
```

**Permission denied:**
```bash
mkdir logs
chmod 755 logs
```

**SFTP connection failed:**
- Verify port (usually 22)
- Check credentials and SSH server status
- Review firewall settings

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please:
1. Fork the project
2. Create a feature branch
3. Commit your changes
4. Push and open a Pull Request
