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

import sys
import time
import select

class DisconnectedError(Exception):
    pass

class TimeoutError(Exception):
    pass

class Peer:
    READ_TIMEOUT = 1 #60 * 10
    WRITE_TIMEOUT = 1 #60

    def __init__(self, pair):
        (self._read_file, self._write_file) = pair
        self._read_file.setblocking(False)
        self._write_file.setblocking(False)
        self._write_buffer = None
        self._timeouts = {}
        self._timeouts["read"] = time.time() + self.READ_TIMEOUT

    def set_peer(self, peer):
        self.peer = peer

    def poll_setup(self, poll):
        mask = select.POLLHUP | select.POLLERR | select.POLLIN

        if self._write_buffer != None:
            mask |= select.POLLOUT

        # Overwrites old settings:
        poll.register(self._read_file, mask)
        poll.register(self._write_file, mask)

    def polled(self, eventmask):
        if eventmask & (select.POLLERR | select.POLLHUP):
            raise DisconnectedError

        if eventmask & select.POLLIN:
            data = self._read_file.recv(1024)
            if len(data) > 0:
                self._timeouts["read"] = time.time() + self.READ_TIMEOUT
                self.peer.add_to_write_buffer(data)

        if eventmask & select.POLLOUT and self._write_buffer != None:
            sent = self._write_file.send(self._write_buffer)
            if sent > 0:
                self._timeouts["write"] = time.time() + self.WRITE_TIMEOUT
                self._write_buffer = self._write_buffer[sent:]
                if self._write_buffer == "":
                    del self._timeouts["write"]
                    self._write_buffer = None

    def get_timeout(self):
        return min(self._timeouts.values())

    def check_timeouts(self):
        now = time.time()
        for t in self._timeouts.values():
            if now > t:
                raise TimeoutError

    def add_to_write_buffer(self, data):
        if self._write_buffer == None:
            self._timeouts["write"] = time.time() + self.WRITE_TIMEOUT
            self._write_buffer = data
        else:
            self._write_buffer += data

    def fds(self):
        return (self._read_file.fileno(), self._write_file.fileno())

class Relay:
    def __init__(self, a, b):
        self._a = Peer(a)
        self._b = Peer(b)
        self._a.set_peer(self._b)
        self._b.set_peer(self._a)

        self._poll = select.poll()

    def _update_poll_setup(self):
        self._a.poll_setup(self._poll)
        self._b.poll_setup(self._poll)

    def _poll_once(self):
        next_timeout = min([self._a.get_timeout(), self._b.get_timeout()])
        next_timeout -= time.time()

        self._update_poll_setup()
        events = self._poll.poll(next_timeout)

        self._a.check_timeouts()
        self._b.check_timeouts()

        for (fd, eventmask) in events:
            for peer in [self._a, self._b]:
                if fd in peer.fds():
                    peer.polled(eventmask)

    def run(self):
        try:
            while True:
                self._poll_once()
        except TimeoutError:
            return False
        except DisconnectedError:
            return False
        else:
            return True

def main():
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect("/home/daniel/.irssi/rstatus_sock")
    r = Relay((s, s), (sys.stdin, sys.stdout))
    r.run()

if __name__ == "__main__":
    main()
