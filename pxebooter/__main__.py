import sys
from multiprocessing import Process
from .dhcp import run as dhcp_run
from .tftp import run as tftp_run
from .http import run as http_run

if __name__ == "__main__":
  if len(sys.argv) > 1:
    ip = sys.argv[1]
  else:
    ip = ""

  dhcp_process = Process(target=dhcp_run, args=(ip,))
  dhcp_process.start()

  tftp_process = Process(target=tftp_run, args=(ip,))
  tftp_process.start()

  http_run(ip)

  tftp_process.join()
  dhcp_process.join()
