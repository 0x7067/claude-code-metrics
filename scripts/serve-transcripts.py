"""HTTP file server with a custom 404 page for missing transcripts."""

import http.server
import os
import sys

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


class TranscriptHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

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
