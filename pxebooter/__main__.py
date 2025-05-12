from multiprocessing import Process
from .dhcp import run as dhcp_run
from .tftp import run as tftp_run
from .http import run as http_run

if __name__ == "__main__":
  dhcp_process = Process(target=dhcp_run)
  dhcp_process.start()

  tftp_process = Process(target=tftp_run)
  tftp_process.start()

  http_run()

  tftp_process.join()
  dhcp_process.join()
