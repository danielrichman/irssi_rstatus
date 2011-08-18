# Copyright 2011 (C) Daniel Richman
#
# This file is part of irssi_rstatus
#
# irssi_rstatus is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# irssi_rstatus is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with irssi_rstatus.  If not, see <http://www.gnu.org/licenses/>.

# Warning: This client, while heartbeating, does not care about the
# server timing out!

import sys
import socket
import select
import time
import json

hb_per = 60 * 9
next_hb = int(time.time()) + hb_per

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/home/daniel/.irssi/rstatus_sock")
s.setblocking(False)

s.send(json.dumps({"type": "settings", "send_messages": True}) + "\n")
messages = True

p = select.poll()
p.register(s, select.POLLIN)
p.register(sys.stdin, select.POLLIN)

while True:
    timeout = next_hb - int(time.time())

    ready = p.poll(timeout)
    files = [f for (f, e) in ready]

    if s.fileno() in files:
        data = s.recv(1024)
        sys.stdout.write(data)
    
    if sys.stdin.fileno() in files:
        line = sys.stdin.readline()
        o = None

        if line == "reset\n":
            o = {"type": "reset_request"}
        elif line == "msgs\n":
            messages = not messages
            o = {"type": "settings", "send_messages": messages}
        else:
            sys.stderr.write("Commands: reset, msgs\n")

        if o:
            s.send(json.dumps(o) + "\n")

    if time.time() >= next_hb:
        next_hb = int(time.time()) + hb_per
        s.send("\n")
