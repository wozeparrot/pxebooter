import socket, socketserver, struct, threading

def DHCPHandlerFactory(proxy:bool):
  # get local ip addr
  s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  s.connect(("10.254.254.254", 1))
  server_ip = s.getsockname()[0]

  url = f"http://${server_ip}:11000/ipxe.efi"

  class DHCPHandler(socketserver.BaseRequestHandler):
    DHCP_MAGIC_COOKIE = b"\x63\x82\x53\x63"
    def handle(self):
      data, sock = self.request
      if len(data) < 240: return
      if data[236:240] != self.DHCP_MAGIC_COOKIE: return

      try:
        packet = struct.unpack("!BBBBLHH4s4s4s4s16s64s128s", data[:236])
        op, htype, hlen, hops, xid, secs, flags, ciaddr, yiaddr, siaddr, giaddr, chaddr, sname, file = packet
        if not (options := DHCPHandler._parse_dhcp_options(data[240:])): return
      except struct.error:
        return

      message_type = options.get(53)
      if message_type is None: return
      message_type = message_type[0]

      vendor_class_id = options.get(60)
      if vendor_class_id is None: return
      try: vendor_class_id = vendor_class_id.decode("ascii", errors="ignore")
      except UnicodeDecodeError: return

      if proxy:
        print("proxy")
      else:
        print("direct")

      print(f"  client mac: {chaddr[:hlen].hex(':')}, client ip: {socket.inet_ntoa(ciaddr)}, options: {options}")
      print(f"    yiaddr: {socket.inet_ntoa(yiaddr)}, giaddr: {socket.inet_ntoa(giaddr)}, flags: {hex(flags)}, secs: {secs}")

      res_siaddr = socket.inet_aton(server_ip)
      dhcp_offer = struct.pack("!BBBBLHH4s4s4s4s16s64s128s", 2, htype, hlen, hops, xid, secs, flags,
                               ciaddr, ciaddr, res_siaddr, giaddr, chaddr,
                               server_ip.encode("ascii").ljust(64, b"\x00"), "ipxe.efi".encode("ascii").ljust(128, b"\x00"))
      dhcp_offer += self.DHCP_MAGIC_COOKIE
      if "HTTPClient" in vendor_class_id:
        match (op, message_type):
          case (1, 1):  # DHCP Discover
            print("    dhcp discover")
            dhcp_offer += self._build_http_dhcp_options(2, options)
          case (1, 3):  # DHCP Request
            print("    dhcp request")
            requested_server_ip = options.get(54)
            if requested_server_ip is None: return
            requested_server_ip = socket.inet_ntoa(requested_server_ip)
            print(f"    requested server ip: {requested_server_ip}")
            if requested_server_ip != server_ip: return

            dhcp_offer += self._build_http_dhcp_options(5, options)
          case _:
            return
      elif "PXEClient" in vendor_class_id:
         match (op, message_type):
          case (1, 1):  # DHCP Discover
            print("    dhcp discover")
            dhcp_offer += self._build_pxe_dhcp_options(2, options)
          case (1, 3):  # DHCP Request
            print("    dhcp request")
            dhcp_offer += self._build_pxe_dhcp_options(5, options)
          case _:
            return

      if giaddr != b"\x00\x00\x00\x00":
        dest_ip = socket.inet_ntoa(giaddr)
        dest_port = 67 if not proxy else self.client_address[1]
      elif ciaddr != b"\x00\x00\x00\x00" and not (flags & 0x8000):
        dest_ip = socket.inet_ntoa(ciaddr)
        dest_port = 68 if not proxy else self.client_address[1]
      else:
        dest_ip = "255.255.255.255"
        dest_port = 68 if not proxy else self.client_address[1]

      if dest_ip == "255.255.255.255": sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
      sock.sendto(dhcp_offer, (dest_ip, dest_port))
      if dest_ip == "255.255.255.255": sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 0)
      print(f"  sent dhcp offer to {dest_ip}:{dest_port}")

    @staticmethod
    def _build_common_options(message_type, opt):
      options = bytearray()
      options += bytes([53, 1, message_type])
      options += bytes([54, 4]) + socket.inet_aton(server_ip)
      if (guid := opt.get(97)) is not None:
        options += bytes([97, len(guid)]) + guid
      return options

    @staticmethod
    def _build_http_dhcp_options(message_type, opt):
      options = DHCPHandler._build_common_options(message_type, opt)

      vendor_class = b"HTTPClient"
      options += bytes([60, len(vendor_class)]) + vendor_class

      bootfile_url_bytes = url.encode("ascii")
      options += bytes([67, len(bootfile_url_bytes)]) + bootfile_url_bytes

      options += bytes([255])
      return bytes(options)

    @staticmethod
    def _build_pxe_dhcp_options(message_type, opt):
      options = DHCPHandler._build_common_options(message_type, opt)

      vendor_class = b"PXEClient"
      options += bytes([60, len(vendor_class)]) + vendor_class

      pxe_file = "ipxe.efi".encode("ascii").ljust(128, b"\x00")
      options += bytes([67, len(pxe_file)]) + pxe_file

      if proxy:
        pxe_options = DHCPHandler._build_pxe_suboptions()
        options += bytes([43, len(pxe_options)]) + pxe_options

      options += bytes([255])
      return bytes(options)

    @staticmethod
    def _build_pxe_suboptions():
      options = bytearray()
      options += bytes([6, 1]) + b"\x08"
      options += bytes([255])
      return bytes(options)

    @staticmethod
    def _parse_dhcp_options(options_bytes):
      parsed_options = {}
      i = 0
      while i < len(options_bytes):
        opt_code = options_bytes[i]
        if opt_code == 255: break
        if opt_code == 0:
          i += 1
          continue

        if i + 1 >= len(options_bytes): break
        opt_len = options_bytes[i+1]
        if i + 2 + opt_len > len(options_bytes): break

        opt_val_start = i + 2
        opt_val_end = opt_val_start + opt_len
        opt_val = options_bytes[opt_val_start:opt_val_end]
        parsed_options[opt_code] = opt_val
        i = opt_val_end
      return parsed_options
  return DHCPHandler

def run_proxy():
  print("starting proxy dhcp")
  server = socketserver.UDPServer(("", 4011), DHCPHandlerFactory(True))
  server.allow_reuse_address = True
  server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
  server.serve_forever()

def run():
  print("starting dhcp")

  threading.Thread(target=run_proxy, daemon=True).start()

  server = socketserver.UDPServer(("", 67), DHCPHandlerFactory(False))
  server.allow_reuse_address = True
  server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
  server.serve_forever()

if __name__ == "__main__":
  run()
