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
import os
import os.path
import signal
import subprocess
import fcntl
import select
import atexit
import time
import json
import logging
import glib
import gtk
import pynotify

class RStatusNotify:
    heartbeat = 60 * 10
    heartbeat_leeway = 60
    nobj_prune = 20
    txtimeout = 60
    level_names = ["none", "none", "message", "hilight"]

    def __init__(self, config):
        self.config = config

    def cleanup(self):
        self._p.stdout.close()
        self._p.stdin.close()
        self._p.terminate()

    def set_nb(self, f):
        flags = fcntl.fcntl(f, fcntl.F_GETFL)
        flags |= os.O_NONBLOCK
        fcntl.fcntl(f, fcntl.F_SETFL)

    def prepare(self):
        self.write_buffer = ""
        self.read_buffer = ""
        self.read_watch = None
        self.timeouts = {}
        self.windows = {}
        self.notifications = {}

        self.icon = gtk.StatusIcon()
        self.status_update()

    def open_ssh(self):
        self._p = subprocess.Popen(config["connect_command"],
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE)
        atexit.register(self.cleanup)

        self.set_nb(self._p.stdin)
        self.set_nb(self._p.stdout)

    def cb_io_problem(self, source, condition):
        logging.info("io_problem: " + repr(condition))
        gtk.main_quit()

    def run(self):
        self.prepare()
        self.open_ssh()

        glib.io_add_watch(self._p.stdout, glib.IO_ERR | glib.IO_HUP,
                          self.cb_io_problem)
        glib.io_add_watch(self._p.stdin, glib.IO_ERR | glib.IO_HUP,
                          self.cb_io_problem)

        glib.io_add_watch(self._p.stdout, glib.IO_IN,
                          self.cb_io_in)

        self.update_hb_timeout("read", 1, self.timeout_drop)
        self.update_hb_timeout("sendhb", -1, self.send_heartbeat)

        self.output({"type": "settings", "send_messages": True})

        gtk.main()

    def update_timeout(self, name, t, callback):
        if name in self.timeouts:
            glib.source_remove(self.timeouts[name])
            del self.timeouts[name]

        if t != None:
            glib.timeout_add_seconds(t, callback)

    def update_hb_timeout(self, name, leeway, callback):
        t = self.heartbeat + (leeway * self.heartbeat_leeway)
        self.update_timeout(name, t, callback)

    def timeout_drop(self):
        logging.error("Heartbeat timed out")
        gtk.main_quit()

    def send_heartbeat(self):
        self.update_hb_timeout("sendhb", -1, self.send_heartbeat)
        self.write_buffer += "\n"
        self.cb_io_out(None, None)

    def cb_io_in(self, source, condition):
        data = os.read(self._p.stdout.fileno(), 1024)
        self.read_buffer += data

        if data:
            self.update_hb_timeout("read", 1, self.timeout_drop)

        if "\n" in self.read_buffer:
            lines = self.read_buffer.split("\n")
            self.read_buffer = lines[-1]

            for line in lines[:-1]:
                obj = json.loads(line)
                logging.debug("Processing obj: " + repr(obj))
                self.handle_input(obj)

        return True

    def cb_io_out(self, source, condition):
        bytes_written = os.write(self._p.stdin.fileno(), self.write_buffer)
        self.write_buffer = self.write_buffer[bytes_written:]

        if len(self.write_buffer) == 0:
            self.update_timeout("senddata", None, None)
            self.write_watch = None
            return False

        if bytes_written or "senddata" not in self.timeouts:
            self.update_timeout("senddata", self.txtimeout, self.timeout_drop)

        if self.write_watch == None:
            self.write_watch = glib.io_add_watch(self._p.stdin, glib.IO_OUT,
                                                 self.cb_io_out)

        return True

    def output(self, obj):
        logging.debug("Sending obj: " + repr(obj))
        self.update_hb_timeout("sendhb", -1, self.send_heartbeat)
        self.write_buffer += json.dumps(obj) + "\n"
        self.cb_io_out(None, None)

    def handle_input(self, obj):
        if obj["type"] == "reset":
            self.handle_reset()
        if obj["type"] == "message":
            self.handle_message(obj)
        if obj["type"] == "window_level":
            self.handle_window_level(obj)
        if obj["type"] == "disconnect_notice":
            logging.error("got a disconnect notice (?)")
            sys.exit(1)

    def handle_message(self, obj):
        if obj["wtype"] == "query":
            key = (obj["server"], "query", obj["nick"])
            title = "{nick} ({server})".format(**obj)
            message = obj["message"]
        elif obj["wtype"] == "channel":
            key = (obj["server"], "channel", obj["channel"], obj["nick"])
            title = "{nick} in {channel} ({server})".format(**obj)
            message = obj["message"]

        self.show_notification(key, title, message)

    def show_notification(self, key, title, message):
        logging.debug("Showing or updating notification: " + repr(key))

        if key in self.notifications:
            n = self.notifications[key]
            assert n["title"] == title

            glib.source_remove(n["timeout"])
            n["timeout"] = \
                glib.timeout_add_seconds(self.nobj_prune, self.gc_nobj, key)

            n["lines"].append(message)
            n["lines"][:-5] = []
            n["nobj"].update(title, "\n".join(n["lines"]))
            n["nobj"].show()

        else:
            timeout = \
                glib.timeout_add_seconds(self.nobj_prune, self.gc_nobj, key)
            nobj = pynotify.Notification(title, message)
            n = {"title": title, "lines": [message],
                 "nobj": nobj, "timeout": timeout}
            self.notifications[key] = n
            nobj.show()

    def gc_nobj(self, key):
        logging.debug("Pruning notification " + repr(key))
        del self.notifications[key]
        logging.debug("Notifications left: " + str(len(self.notifications)))
        return False

    def handle_window_level(self, obj):
        if obj["wtype"] == "channel":
            name = obj["channel"]
        elif obj["wtype"] == "query":
            name = obj["nick"]

        window = (obj["server"], obj["wtype"], name)
        level = obj["level"]
        assert self.level_names[level]

        if level:
            self.windows[window] = level
        else:
            if window in self.windows:
                del self.windows[window]

        self.status_update()

    def handle_reset(self):
        self.windows.clear()
        self.status_update()

    def status_update(self):
        if self.windows:
            max_level = max(self.windows.values())
        else:
            max_level = 0

        level_name = self.level_names[max_level]
        icon_name = "irssi_{0}.png".format(level_name)
        icon_name = os.path.join(config["icons_dir"], icon_name)

        logging.debug("Setting icon level to " + str(max_level))
        logging.debug("Using " + icon_name)

        self.icon.set_from_file(icon_name)
        self.icon.set_blinking(level_name == "hilight")

if __name__ == "__main__":
    config = {
        "connect_command": ("ssh", "anapnea", "socat", "-T", "700",
                            "unix-client:.irssi/rstatus_sock",
                            "stdin!!stdout"),
        "icons_dir": os.path.realpath(os.path.dirname(__file__))
    }

    logging.basicConfig(level=logging.DEBUG)
    pynotify.init("RStatus")

    for sig in [signal.SIGINT, signal.SIGTERM]:
        signal.signal(sig, lambda a, b: gtk.main_quit())

    RStatusNotify(config).run()
