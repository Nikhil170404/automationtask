# Index2 Downloader

A web application and automation tool for downloading Index-2 documents from the Maharashtra IGR (Inspector General of Registration) website.

## Overview

This tool automates the process of searching and downloading Index-2 property documents from the Maharashtra government's IGR service website. It handles:

- Navigating to the search page
- Solving CAPTCHAs automatically using OCR
- Filling search forms with property details
- Downloading Index-2 documents as PDFs
- Organizing downloaded files in a structured folder hierarchy
- Uploading documents to Google Drive with the same folder structure
- Providing a web interface for users to search for documents

## Requirements

### System Requirements
- Python 3.8 or higher
- Tesseract OCR engine
- Chrome or Chromium browser

### Python Packages
- Flask
- selenium
- undetected-chromedriver
- pytesseract
- Pillow
- google-api-python-client
- google-auth
- beautifulsoup4

## Installation

### 1. Install Python and pip
Ensure Python 3.8+ is installed on your system.

```bash
# Check Python version
python --version
```

### 2. Install Tesseract OCR

#### For Windows:
1. Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
2. Install and add to PATH
3. The default installation path is `C:\Program Files\Tesseract-OCR\tesseract.exe`

#### For MacOS:
```bash
brew install tesseract
```

#### For Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

### 3. Clone the repository
```bash
git clone https://github.com/yourusername/index2-downloader.git
cd index2-downloader
```

### 4. Set up a virtual environment (recommended)
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# For Windows
venv\Scripts\activate
# For MacOS/Linux
source venv/bin/activate
```

### 5. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 6. Set up Google Drive API
1. Create a project in Google Cloud Console
2. Enable the Google Drive API
3. Create service account credentials
4. Download the service account key file as JSON
5. Rename the file to `service_account.json` and place it in the project root

### 7. Set the file paths
- In the code, update the Tesseract path if needed:
```python
# Set your Tesseract path if it's different from the default
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```
- Update the Google Drive folder ID with your own folder ID:
```python
self.drive_folder_id = 'YOUR_FOLDER_ID_HERE'  # Replace with your folder ID
```

## Usage

### Running the Web Interface
```bash
python app.py
```
This will start the Flask server at http://localhost:5008

### Using the API
You can also use the tool programmatically:

```python
from index2_downloader import Index2Downloader

downloader = Index2Downloader(headless=False, downloads_path="downloads")
downloader.initialize()

try:
    # Search and download a document
    result = downloader.download_document({
        'year': '2023',
        'district_name': 'पुणे',
        'taluka_name': 'हवेली',
        'village_name': 'कसबा पेठ',
        'property_number': '123/45',
        'download_all': True
    })
    print(result)
finally:
    downloader.close()
```

## Command Line Interface
The tool also provides a command-line interface:

```bash
python index2_downloader.py --year 2023 --district "पुणे" --taluka "हवेली" --village "कसबा पेठ" --property "123/45" --download-all
```

## Requirements.txt file
Create a file named `requirements.txt` with the following content:

```
Flask==2.3.3
selenium==4.11.2
undetected-chromedriver==3.5.3
pytesseract==0.3.10
Pillow==10.0.0
google-api-python-client==2.95.0
google-auth==2.22.0
beautifulsoup4==4.12.2
```

Then install dependencies with:
```bash
pip install -r requirements.txt
```

## Project Structure
```
index2_downloader/
├── app.py                  # Flask web application
├── index2_downloader.py    # Main downloader class
├── requirements.txt        # Python dependencies
├── service_account.json    # Google Drive API credentials
├── downloads/              # Downloaded documents
├── templates/              # HTML templates
│   ├── index.html          # Search form template
│   ├── result.html         # Results page template
│   └── error.html          # Error page template
├── static/                 # Static assets (CSS, JS)
└── README.md               # Project documentation
```

## Features

- **Automatic CAPTCHA Solving**: Uses OCR to automatically solve CAPTCHAs.
- **Robust Page Navigation**: Handles slow government websites with retries and exponential backoff.
- **Multiple Document Handling**: Can download all documents for a property from multiple pages.
- **Organized Storage**: Creates a structured folder hierarchy based on year, district, taluka, etc.
- **Google Drive Integration**: Uploads documents to Google Drive with the same folder structure.
- **Web Interface**: Provides a user-friendly web interface for searching and downloading documents.
- **Detailed Logging**: Comprehensive logging for debugging and monitoring.
- **Error Handling**: Robust error handling for various scenarios.

## Troubleshooting

### Common Issues

1. **CAPTCHA Recognition Failures**
   - The OCR may sometimes fail to recognize CAPTCHAs correctly.
   - Solution: Adjust the contrast settings in the `solve_captcha` method.

2. **Browser Initialization Issues**
   - If the browser fails to initialize, check Chrome/Chromium installation.
   - Solution: Update Chrome to the latest version.

3. **Slow Website Response**
   - The government website can be very slow at times.
   - Solution: Increase timeout values in the code.

4. **Google Drive Upload Failures**
   - Check if the service account has proper permissions.
   - Solution: Share the destination folder with the service account email.

5. **Tesseract OCR Issues**
   - If OCR is not working, check Tesseract installation.
   - Solution: Ensure the path to Tesseract executable is correctly set.

### Debugging

The application creates detailed logs and screenshots for debugging:
- Check the `downloads` folder for screenshots of each step
- Enable more detailed logging by changing the log level
- Use the `navigation_only` mode to test without downloading documents

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is provided for educational and legitimate personal use only. Please ensure you comply with all applicable terms of service and legal requirements when using this tool to access government websites.
