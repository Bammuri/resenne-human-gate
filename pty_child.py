"""Establish a controlling terminal before replacing this helper with the shell."""
import fcntl
import os
import sys
import termios

os.setsid()
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
os.tcsetpgrp(0, os.getpgrp())
os.execv(sys.argv[1], sys.argv[1:])
