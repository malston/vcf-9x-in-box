#!/usr/bin/env python3

# See https://williamlam.com/2025/01/quick-tip-easily-host-vmware-cloud-foundation-vcf-offline-depot-using-python-simplehttpserver-with-authentication.html
# Extended python -m http.serve with --username and --password parameters for
# basic auth, based on https://gist.github.com/fxsjy/5465353
# Further extended https://gist.github.com/mauler/593caee043f5fe4623732b4db5145a82 (with help from ChatGPT) to add support for HTTPS
#
# Example:
#   python3 http_server_auth.py --bind 192.168.30.4 --user vcf --password vcf123! --port 443 --directory /Volumes/Storage/Software/depot --certfile ~/cert.crt --keyfile ~/key.pem
#   ./scripts/http_server_auth.py --bind 0.0.0.0 --user vcf --password vcf123! --port 8888 --directory /Users/markalston/Storage/Software
#   ./scripts/http_server_auth.py --bind 0.0.0.0 --user vcf --password vcf123! --port 8888 --directory /Volumes/vcf-content/Software/depot

from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler, test
import base64
import os
import ssl
import argparse


class AuthHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Main class to present webpages and authentication."""

    def __init__(self, *args, **kwargs):
        username = kwargs.pop("username")
        password = kwargs.pop("password")
        self._auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        super().__init__(*args, **kwargs)

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Test"')
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        """Present front page with user authentication."""
        if self.headers.get("Authorization") is None:
            self.do_AUTHHEAD()
            self.wfile.write(b"no auth header received")
        elif self.headers.get("Authorization") == "Basic " + self._auth:
            SimpleHTTPRequestHandler.do_GET(self)
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get("Authorization").encode())
            self.wfile.write(b"not authenticated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cgi", action="store_true", help="Run as CGI Server")
    parser.add_argument(
        "--bind",
        "-b",
        metavar="ADDRESS",
        default="127.0.0.1",
        help="Specify bind address [default: 127.0.0.1]",
    )
    parser.add_argument(
        "--directory",
        "-d",
        default=os.getcwd(),
        help="Specify alternative directory [default: current directory]",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Specify alternate port [default: 8000]",
    )
    parser.add_argument("--username", "-u", required=True, metavar="USERNAME")
    parser.add_argument("--password", "-P", required=True, metavar="PASSWORD")

    # New TLS arguments
    parser.add_argument(
        "--certfile", metavar="CERTFILE", help="Path to TLS certificate file"
    )
    parser.add_argument("--keyfile", metavar="KEYFILE", help="Path to TLS key file")

    args = parser.parse_args()

    handler_class = partial(
        AuthHTTPRequestHandler,
        username=args.username,
        password=args.password,
        directory=args.directory,
    )

    # Create HTTP Server
    httpd = HTTPServer((args.bind, args.port), handler_class)

    # Enable TLS if certificate and key files are provided
    if args.certfile and args.keyfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=args.certfile, keyfile=args.keyfile)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        print(f"🔒 Serving HTTPS on https://{args.bind}:{args.port} ...")
    else:
        print(f"🌐 Serving HTTP on http://{args.bind}:{args.port} ...")

    httpd.serve_forever()
