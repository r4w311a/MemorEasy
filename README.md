# MemorEasy Snapchat ZIP Export Processor

This project is a fork of the original [bransoned/MemorEasy](https://github.com/bransoned/MemorEasy) project.

The original project was built for Snapchat exports that contained a `memories_history.html` file with download links. Snapchat changed its export format and no longer provides those old download endpoints. New Snapchat data exports now include the actual photo and video files inside one or more ZIP files, plus a `json/memories_history.json` file that contains the date, media type, and location information.

This fork keeps the useful media preparation parts of MemorEasy and updates the workflow for Snapchat's newer ZIP export format.

## What This Tool Does

This tool takes the ZIP files you download from Snapchat and creates a clean folder of photos and videos that are ready to copy or import to your iPhone.

It will:

- Read all Snapchat ZIP files from your export.
- Find the real JPG and MP4 Memories already included by Snapchat.
- Read each Memory's date, time, media type, and GPS location from `json/memories_history.json`.
- Match each photo or video to the correct metadata.
- Merge Snapchat overlay PNG files back onto the matching photo or video when an overlay exists.
- Write correct date/time metadata into JPG and MP4 files.
- Write GPS location metadata when Snapchat included it.
- Set the file modified time to the Memory time.
- Rename files in a readable chronological format.
- Create a final `iphone_ready_memories/media` folder.
- Create reports showing what was processed.

## What This Tool No Longer Does

This fork does not download Memories from Snapchat servers. Snapchat now includes the actual media files in your downloaded ZIP export, so the old downloader code is no longer needed.

This fork also does not use the old `memories_history.html` download-link workflow.

## What You Need

You need:

- Your Snapchat Memories export ZIP files.
- Python 3.10 or newer.
- `ffmpeg`.
- `exiftool`.
- The Python packages listed in `requirements.txt`.

You do not need to be a developer to run it. You only need to copy a few commands into Terminal, PowerShell, or Command Prompt.

## Step 1: Download Your Snapchat Data

1. Open Snapchat's data download page:
   [Download My Data from Snapchat](https://help.snapchat.com/hc/en-us/articles/7012305371156-How-do-I-download-my-data-from-Snapchat)
2. Request your Memories data.
3. Wait for Snapchat to prepare the download.
4. Download every ZIP file Snapchat gives you.

Snapchat may give you one ZIP file or many ZIP files. Keep all of them.

Example ZIP names may look like this:

```text
mydata~123456789.zip
mydata~123456789-2.zip
mydata~123456789-3.zip
```

Do not manually rename the files unless you know what you are doing.

## Step 2: Put the ZIP Files Somewhere Easy

The easiest place is a folder named `snapchat-zips`.

Example:

- macOS: `/Users/yourname/Downloads/snapchat-zips`
- Windows: `C:\Users\yourname\Downloads\snapchat-zips`
- Linux: `/home/yourname/Downloads/snapchat-zips`

Put all Snapchat ZIP files in that folder.

You do not need to unzip them first.

## Step 3: Install Required Tools

### macOS

Install Homebrew if you do not already have it:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then install the required tools:

```sh
brew install python ffmpeg exiftool
```

### Windows

Install Python:

- Download it from [python.org](https://www.python.org/downloads/windows/).
- During installation, enable "Add Python to PATH".

Install `ffmpeg` and `exiftool`:

- `ffmpeg`: [FFmpeg Windows builds](https://github.com/BtbN/FFmpeg-Builds/releases)
- `exiftool`: [ExifTool Windows download](https://exiftool.org/)

Make sure both tools can be run from Command Prompt or PowerShell.

To check:

```powershell
python --version
ffmpeg -version
exiftool -ver
```

### Linux

On Ubuntu or Debian:

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg libimage-exiftool-perl
```

## Step 4: Install This Project

Open a terminal in the folder where you want this project to live.

Clone the repo:

```sh
git clone https://github.com/YOUR_USERNAME/MemorEasy.git
cd MemorEasy
```

If you downloaded the repo as a ZIP from GitHub instead, unzip it and open a terminal inside the unzipped `MemorEasy` folder.

Create a Python virtual environment:

### macOS and Linux

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Windows Command Prompt

```bat
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Step 5: Run a Safe Preview

A preview checks the ZIP files and matching logic without creating the final media folder.

### macOS or Linux

```sh
python process_export.py "/path/to/snapchat-zips/*.zip" --dry-run
```

Example:

```sh
python process_export.py "$HOME/Downloads/snapchat-zips/*.zip" --dry-run
```

### Windows PowerShell

```powershell
python process_export.py "C:\Users\yourname\Downloads\snapchat-zips\*.zip" --dry-run
```

If the preview says `Failed: 0`, continue to the next step.

## Step 6: Create the iPhone-Ready Folder

### macOS or Linux

```sh
python process_export.py "/path/to/snapchat-zips/*.zip"
```

Example:

```sh
python process_export.py "$HOME/Downloads/snapchat-zips/*.zip"
```

### Windows PowerShell

```powershell
python process_export.py "C:\Users\yourname\Downloads\snapchat-zips\*.zip"
```

This can take a while for large exports.

When it finishes, you should see a summary like:

```text
MemorEasy export summary
==================================================
Input ZIPs: 8
Metadata rows: 6615
Main media files: 6610
Overlay files: 297
Matched media: 6610
Missing media rows: 5
Unmatched media files: 0
Created: 6610
Skipped: 0
Failed: 0
```

## Where Your Ready Photos Are

The final ready-to-import files are here:

```text
iphone_ready_memories/media
```

Inside that folder, files are named like this:

```text
2026-05-27-144813_564F24E8-76B0-4346-901A-35435B29389C.jpg
```

The first part is the Memory date and time:

```text
YYYY-MM-DD-HHMMSS
```

## Reports

The tool also creates reports here:

```text
iphone_ready_memories/reports
```

Important files:

- `summary.json`: a summary of the whole run.
- `manifest.csv`: one row for each processed photo or video.

These reports are useful if you want to check whether anything was missing or skipped.

## Copying to iPhone

You can import the files from:

```text
iphone_ready_memories/media
```

Use whichever import method you normally use:

- Photos app on macOS.
- iCloud Photos.
- AirDrop.
- Finder sync on macOS.
- Windows Photos or iTunes-style file transfer tools.

The media files should carry the corrected date/time and GPS metadata.

## Common Notes

### Snapchat says there are more metadata rows than files

This can happen. Snapchat may include a row in `memories_history.json` even when the matching media file is not included in the ZIP export. The report will count these as missing media rows.

If `Unmatched media files` is `0` and `Failed` is `0`, the run is usually healthy.

### Do I need to unzip the Snapchat files?

No. Give the tool the ZIP files directly.

### Can I choose a different output folder?

Yes:

```sh
python process_export.py "/path/to/snapchat-zips/*.zip" --output "/path/to/output"
```

Your ready files will be in:

```text
/path/to/output/media
```

### Can I rerun it?

Yes. By default, existing files are skipped.

To overwrite the output files:

```sh
python process_export.py "/path/to/snapchat-zips/*.zip" --force
```

## Project Files

The active code path is intentionally small:

- `process_export.py`: command you run.
- `src/export_processor.py`: reads ZIP files, matches metadata, writes output and reports.
- `src/media_processing.py`: merges Snapchat overlay PNG files onto JPG/MP4 media.
- `src/metadata.py`: writes EXIF/QuickTime metadata and file timestamps.
- `src/dependencies.py`: finds `ffmpeg` and `exiftool`.
- `src/exceptions.py`: shared error types.

The old downloader/parser workflow from the original project has been removed from this fork because Snapchat's new export format already includes the media files.

## Credit

This fork is built on top of the original [bransoned/MemorEasy](https://github.com/bransoned/MemorEasy) project. The original project solved the earlier Snapchat Memories export problem and provided the base media-processing ideas used here.

This fork exists because Snapchat changed its export format and the old endpoint-based workflow no longer works.

## License

See [license.txt](license.txt).
