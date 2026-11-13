"""Local test server with correct MIME types (.mjs, .wasm, .webmanifest).
Usage: python tests\\serve_static.py [port] [directory]   (default directory: C:\\thesis\\web_static)"""
import functools, http.server, mimetypes, sys

mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/manifest+json", ".webmanifest")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


class H(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript", ".wasm": "application/wasm",
                      ".webmanifest": "application/manifest+json"}

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", port),
                                functools.partial(H, directory=sys.argv[2] if len(sys.argv) > 2 else r"C:\thesis\web_static")).serve_forever()
