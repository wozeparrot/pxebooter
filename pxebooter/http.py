import socket, socketserver, json
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

try:
  with open("bootspec.json") as f:
    BOOT_SPEC = json.load(f)
except FileNotFoundError:
  BOOT_SPEC = {}

def HTTPHandlerFactory():
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.connect(("10.254.254.254", 1))
  server_ip = s.getsockname()[0]

  class HTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
      if self.path != "/boot":
        print("  invalid path")
        self.send_response(404)
        self.end_headers()
        return

      # get parameters
      content_length = int(self.headers["Content-Length"])
      post_data = self.rfile.read(content_length)
      print("  got post data")
      print("  ", post_data)

      # parse serial and uuid
      uuid = ""
      for param in post_data.decode("utf-8").split("&"):
        if param.startswith("uuid="):
          uuid = unquote(param.split("=")[1])
      print("  uuid:", uuid)

      filename = "fallback.ipxe"
      if uuid in BOOT_SPEC:
        filename = BOOT_SPEC[uuid]

      print("  sending", filename)

      with open(filename, "r") as f:
        data = f.read()
        data = data.replace("{{ip}}", server_ip)
        data = data.encode("utf-8")

      self.send_response(200)
      self.send_header("Content-Length", str(len(data)))
      self.send_header("Content-Type", "application/octet-stream")
      self.end_headers()
      self.wfile.write(data)

    def do_GET(self):
      if self.path != "/ipxe.efi" and self.path != "/autoexec.ipxe":
        print("  invalid path")
        self.send_response(404)
        self.end_headers()
        return

      if self.path == "/ipxe.efi":
        print("  sending ipxe.efi")
        with open("ipxe.efi", "rb") as f:
          data = f.read()
      elif self.path == "/autoexec.ipxe":
        print("  sending autoexec.ipxe")

        # patch autoexec to replace {{ip}} with server_ip
        with open("autoexec.ipxe", "r") as f:
          data = f.read()
          data = data.replace("{{ip}}", server_ip)
          data = data.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(data)
  return HTTPHandler

def run():
  print("starting http")
  server = socketserver.ThreadingTCPServer(("", 11000), HTTPHandlerFactory())
  server.allow_reuse_address = True
  server.serve_forever()

if __name__ == "__main__":
  run()
