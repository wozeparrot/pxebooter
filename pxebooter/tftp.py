import socket, socketserver, struct

def TFTPHandlerFactory(server_ip:str=""):
  if not server_ip:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.254.254.254", 1))
    server_ip = s.getsockname()[0]

  class TFTPHandler(socketserver.BaseRequestHandler):
    def handle(self):
      data, sock = self.request
      if len(data) < 4: return

      opcode = int.from_bytes(data[:2], "big")
      print(f"client ip: {self.client_address[0]}, opcode: {opcode}")

      if opcode != 1: return

      parts = data[2:].split(b"\x00")
      if len(parts) < 2: return
      filename = parts[0].decode("ascii", errors="ignore")
      mode = parts[1].decode("ascii", errors="ignore").lower()

      print(f"  filename: {filename}, mode: {mode}")
      if (filename != "ipxe.efi" and filename != "autoexec.ipxe") or mode != "octet":
        print("  invalid filename or mode")
        error_packet = self._error_packet(1, "File not found")
        sock.sendto(error_packet, self.client_address)
        return

      # check for options
      want_size = False
      try:
        parts.index(b"tsize")
        # client wants size
        want_size = True
      except ValueError: pass

      if filename == "ipxe.efi":
        with open("ipxe.efi", "rb") as f:
          data = f.read()
      elif filename == "autoexec.ipxe":
        with open("autoexec.ipxe", "r") as f:
          data = f.read()
          data = data.replace("{{ip}}", server_ip)
          data = data.encode("utf-8")

      tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      tsock.bind((server_ip, 0))
      try:
        block_number = 1
        if want_size:
          packet = struct.pack("!BB8s4s6s", 0, 6, b"blksize\x00", b"512\x00", b"tsize\x00")
          packet += str(len(data)).encode("ascii") + b"\x00"
          tsock.sendto(packet, self.client_address)

        while True:
          datab = data[(block_number - 1) * 512:block_number * 512]
          packet = self._data_packet(block_number, datab)
          tsock.sendto(packet, self.client_address)

          if len(data) < 512:
            print("  transfer complete")
            break

          try:
            ack, _ = tsock.recvfrom(256)
          except socket.timeout:
            print("  timeout")
            break
          ack_opcode = int.from_bytes(ack[:2], "big")
          ack_block_number = int.from_bytes(ack[2:4], "big")
          if ack_opcode != 4 or ack_block_number != block_number:
            print(f"  invalid ack: {ack_opcode}, {ack_block_number}")
            if ack_opcode == 5:
              error_code = int.from_bytes(ack[2:4], "big")
              error_message = ack[4:-1].decode("ascii", errors="ignore")
              print(f"  error code: {error_code}, message: {error_message}")
            break
          block_number += 1
          if block_number > 65535:
            block_number = 0
      finally:
        tsock.close()

    @staticmethod
    def _error_packet(error, error_message):
      error_message_bytes = error_message.encode("ascii")
      format_str = f"!HH{len(error_message_bytes)}sb"
      return struct.pack(format_str, 5, error, error_message_bytes, 0)

    @staticmethod
    def _data_packet(block_number, data):
      format_str = f"!HH{len(data)}s"
      return struct.pack(format_str, 3, block_number, data)
  return TFTPHandler

def run(ip:str=""):
  print("starting tftp")
  server = socketserver.ThreadingUDPServer((ip, 69), TFTPHandlerFactory(ip))
  server.allow_reuse_address = True
  server.serve_forever()

if __name__ == "__main__":
  run()
