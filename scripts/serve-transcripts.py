"""HTTP file server with a custom 404 page for missing transcripts."""

import http.server
import os
import sys
import tempfile
import re
from pathlib import Path

DIRECTORY = sys.argv[1] if len(sys.argv) > 1 else "/transcripts"
PORT = int(os.environ.get("PORT", "8080"))

ERROR_404_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Transcript Not Found</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 80px auto; padding: 0 20px; color: #333; }
    h1 { font-size: 1.4rem; }
    p { line-height: 1.6; color: #666; }
    a { color: #2563eb; }
    code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>Transcript not available</h1>
  <p>
    This session's transcript has not been generated. This happens when the
    original <code>.jsonl</code> session file is missing or incomplete.
  </p>
  <p><a href="/all/">Browse all available transcripts</a></p>
</body>
</html>
"""

EXPORT_BUTTON_SCRIPT = """
<script>
(function() {
  // Extract session ID from URL path
  const path = window.location.pathname;
  const sessionMatch = path.match(/\\/([a-f0-9-]{36})\\//);
  if (!sessionMatch) return;

  const sessionId = sessionMatch[1];
  const exportUrl = `/export/${sessionId}`;

  // Create export button
  const btn = document.createElement('a');
  btn.href = exportUrl;
  btn.download = `transcript-${sessionId}.html`;
  btn.textContent = '📥 Export Complete Transcript';
  btn.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    padding: 12px 20px;
    background: #2563eb;
    color: white;
    border-radius: 8px;
    text-decoration: none;
    font-family: system-ui, sans-serif;
    font-size: 14px;
    font-weight: 500;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    z-index: 9999;
    transition: all 0.2s;
  `;

  btn.addEventListener('mouseenter', () => {
    btn.style.background = '#1d4ed8';
    btn.style.transform = 'translateY(-2px)';
    btn.style.boxShadow = '0 6px 8px rgba(0,0,0,0.15)';
  });

  btn.addEventListener('mouseleave', () => {
    btn.style.background = '#2563eb';
    btn.style.transform = 'translateY(0)';
    btn.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
  });

  document.body.appendChild(btn);
})();
</script>
"""


class TranscriptHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        # Handle export endpoint
        if self.path.startswith("/export/"):
            self.handle_export()
        # For HTML files, check if we should inject export button
        elif re.search(r'/[a-f0-9-]{36}/', self.path) and (self.path.endswith('.html') or self.path.endswith('/')):
            self.serve_html_with_export_button()
        else:
            super().do_GET()

    def serve_html_with_export_button(self):
        """Serve HTML file with export button injected."""
        # Translate path to file system path
        import os
        path = self.translate_path(self.path)

        # If path is a directory, serve index.html from it
        if os.path.isdir(path):
            path = os.path.join(path, 'index.html')

        try:
            with open(path, 'rb') as f:
                content = f.read()

            # Inject export button before </body>
            if b'</body>' in content:
                content = content.replace(
                    b'</body>',
                    EXPORT_BUTTON_SCRIPT.encode('utf-8') + b'</body>',
                    1  # Only replace first occurrence
                )

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        except (FileNotFoundError, IsADirectoryError):
            # If path is directory or file not found, fall back to default handler
            super().do_GET()

    def handle_export(self):
        """Generate and serve a merged single-file transcript."""
        # Extract session ID from path: /export/SESSION_ID
        path_parts = self.path.strip("/").split("/")
        if len(path_parts) != 2:
            self.send_error(400, "Invalid export path")
            return

        session_id = path_parts[1]
        transcript_dir = Path(DIRECTORY) / session_id

        if not transcript_dir.exists() or not (transcript_dir / "index.html").exists():
            self.send_error(404, "Transcript not found")
            return

        try:
            # Import merge function
            sys.path.insert(0, os.path.dirname(__file__))
            from merge_transcript import merge_transcripts

            # Create temporary file for merged output
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as tmp_file:
                tmp_path = Path(tmp_file.name)

            # Merge transcript
            merge_transcripts(transcript_dir, tmp_path)

            # Serve the merged file
            with open(tmp_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Disposition", f'attachment; filename="transcript-{session_id}.html"')
            self.end_headers()
            self.wfile.write(content)

            # Clean up temp file
            tmp_path.unlink()

        except Exception as e:
            print(f"Error generating export: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Export failed: {str(e)}")

    def send_error(self, code, message=None, explain=None):
        if code == 404:
            body = ERROR_404_HTML.encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().send_error(code, message, explain)


if __name__ == "__main__":
    with http.server.HTTPServer(("", PORT), TranscriptHandler) as httpd:
        print(f"Serving {DIRECTORY} on port {PORT}")
        httpd.serve_forever()
