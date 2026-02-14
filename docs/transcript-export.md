# Transcript Export Feature

## Overview

The transcript server now supports exporting paginated transcripts as a single HTML file.

## Features

### 1. Export Button

A floating "📥 Export Complete Transcript" button appears on all transcript pages with a valid session ID. The button:
- Floats in the bottom-right corner
- Has hover animations
- Triggers a download of the merged transcript
- Works on both index and paginated pages

### 2. Export Endpoint

**Endpoint**: `http://localhost:8080/export/{session-id}`

**Behavior**:
- Merges all paginated HTML files (index.html, page-001.html, etc.) into a single HTML file
- Removes pagination controls from the merged file
- Returns the file as a downloadable attachment
- Preserves all styling and functionality

### 3. Merge Script

**Location**: `scripts/merge-transcript.py`

**Usage**:
```bash
# Standalone usage
uv run scripts/merge-transcript.py <transcript_dir> <output_file>

# Example
uv run scripts/merge-transcript.py /tmp/transcripts/abc-123 output.html
```

**As module**:
```python
from merge_transcript import merge_transcripts
from pathlib import Path

merge_transcripts(
    transcript_dir=Path("/transcripts/session-id"),
    output_file=Path("output.html")
)
```

## Implementation Details

### Files Modified

1. **scripts/serve-transcripts.py**
   - Added `/export/{session-id}` endpoint handler
   - Added JavaScript injection for export button
   - Modified `do_GET()` to intercept transcript page requests

2. **scripts/merge-transcript.py** (new)
   - Uses BeautifulSoup4 to parse and merge HTML
   - Removes pagination elements
   - Appends messages from all pages to single document

3. **scripts/Dockerfile.transcripts**
   - Added `beautifulsoup4` dependency
   - Added `merge-transcript.py` to container

### How It Works

1. User opens transcript at `http://localhost:8080/{session-id}/`
2. Server detects UUID pattern in path
3. Server reads `index.html`, injects export button JavaScript before `</body>`
4. JavaScript extracts session ID from URL and creates button
5. Clicking button requests `/export/{session-id}`
6. Server merges all pages and returns as download

## Testing

```bash
# Access transcript with button
open http://localhost:8080/318b3349-e897-4814-8d76-40764539a363/

# Test export endpoint directly
curl -O http://localhost:8080/export/318b3349-e897-4814-8d76-40764539a363
```

## Future Enhancements

- [ ] Add export options (with/without subagents)
- [ ] Support exporting multiple sessions as ZIP
- [ ] Add "Copy Link" button to share export URL
- [ ] Cache merged transcripts to avoid regeneration
