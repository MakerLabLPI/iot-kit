#!/usr/bin/env python3
# A tiny HTTP server for the "secret" exercise: GET /secret answers
# "Hello World", everything else is 404. Standard library only, no pip.
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8001


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/secret":
            body = b"Hello World\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    # One line per request on stdout, so "docker compose logs" shows them
    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
