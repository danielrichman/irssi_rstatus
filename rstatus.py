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

import irssi
import os
import string
import traceback
import time
import errno
import socket
import json
import pprint

# Emulate irssi's nick_match_msg
def fuzzymatch_trtbl_gen():
    keep = [
        string.digits,
        string.uppercase,
        string.lowercase
    ]

    table = list('.' * 256)

    for data in keep:
        first = ord(data[0])
        table[first:first + len(data)] = string.lower(data)

    table = ''.join(table)
    return table

def fuzzymatch(msg, nick, other_channel_nicks):
    tmsg = '.' + string.translate(msg, fuzzymatch_trtbl) + '.'
    tnick = '.' + string.translate(nick, fuzzymatch_trtbl) + '.'

    if tnick not in tmsg:
        return False

    # extract the bit that matched
    p = tmsg.find(tnick) - 1 + 1
    match = msg[p:p + len(nick)]

    if match in other_channel_nicks:
        return False

    return True

fuzzymatch_trtbl = fuzzymatch_trtbl_gen()


class RStatus:
    timeout_txrx = 60
    timeout_heartbeat = 60 * 10
    timeout_drop_notify = 10
    cbuffer_limit = 8192

    def __init__(self, debug=False):
        self.debug = debug
        self.lasts = {}
        self.create_settings()
        self.load_settings()
        self.create_socket()

        if self.debug:
            irssi.prnt("RStatus loaded. Windows:")
            irssi.prnt(pprint.pformat(self.window_all()))

        irssi.signal_add("setup changed", self.load_settings)
        irssi.signal_add("setup reread", self.load_settings)

        irssi.signal_add("window hilight", self.windowhilight)
        irssi.signal_add("message private", self.privmsg)
        irssi.signal_add("message public", self.pubmsg)

        irssi.signal_add("channel destroyed", self.channeldestroyed)
        irssi.signal_add("query destroyed", self.querydestroyed)

        irssi.command_bind("rstatus", self.status)

    def status(self, data, server, window):
        irssi.prnt("RStatus: Current Status: ")
        irssi.prnt("Connected clients: {0}".format(len(self.clients)))
        irssi.prnt("Server Socket OK? {0}".format(self.socket != False))

        for key, (info, etime) in self.lasts.items():
            etime = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(etime))
            irssi.prnt("Last {0}: {1} at {2}".format(key, info, etime))

    def last_set(self, key, info):
        self.lasts[key] = (info, time.time())

    def update(self, info):
        if not self.filter_event(info):
            return

        if self.debug:
            irssi.prnt("RStatus update: " + pprint.pformat(info))

        for conn, client_info in self.clients.items():
            if info["type"] == "message" and not client_info["send_messages"]:
                continue

            self.client_send(conn, info)

    def windowhilight(self, window):
        self.update(self.window_info(window))

    def privmsg(self, server, msg, nick, address):
        info = {
            "nick": nick,
            "server": server.tag,
            "type": "message",
            "wtype": "query",
            "message": msg
        }
        self.update(info)

    def pubmsg(self, server, msg, nick, address, target):
        channel = server.channel_find(target)
        if channel:
            nicks = channel.nicks()
        else:
            nicks = []

        if not fuzzymatch(msg, server.nick, nicks):
            return

        info = {
            "channel": target,
            "nick": nick,
            "server": server.tag,
            "type": "message",
            "wtype": "channel",
            "message": msg
        }
        self.update(info)

    def channeldestroyed(self, channel):
        info = {
            "channel": channel.name,
            "server": channel.server.tag,
            "wtype": "channel",
            "level": 0,
            "type": "window_level"
        }
        self.update(info)

    def querydestroyed(self, query):
        info = {
            "nick": query.name,
            "server": query.server.tag,
            "wtype": "query",
            "level": 0,
            "type": "window_level"
        }
        self.update(info)

    def window_all(self):
        return map(self.window_info, irssi.windows())

    def window_info(self, window):
        if not window.active:
            return False

        if isinstance(window.active, irssi.IrcChannel):
            wtype = "channel"
            wprop = "channel"
        elif isinstance(window.active, irssi.Query):
            wtype = "query"
            wprop = "nick"
        else:
            return False

        if len(window.active.name) == 0:
            return False

        info = {
            wprop: window.active.name,
            "server": window.active.server.tag,
            "level": window.data_level,
            "wtype": wtype,
            "type": "window_level"
        }

        return info

    def filter_event(self, info):
        if info == False:
            return False

        if info["wtype"] == "channel":
            default = self.settings["default_channels"]
            name = info["channel"].lower()
        elif info["wtype"] == "query":
            default = self.settings["default_queries"]
            name = info["nick"].lower()
        else:
            return False

        if name in self.settings["override_notify"]:
            return True
        if name in self.settings["override_ignore"]:
            return False

        return default

    def create_settings(self):
        irssi.settings_add_str("rstatus", "socket", "~/.irssi/rstatus_sock")
        irssi.settings_add_str("rstatus", "default_channels", "notify")
        irssi.settings_add_str("rstatus", "default_queries", "notify")
        irssi.settings_add_str("rstatus", "override_notify", "")
        irssi.settings_add_str("rstatus", "override_ignore", "")

    def load_settings(self, *args):
        nikeys = ["default_channels", "default_queries"]
        setkeys = ["override_notify", "override_ignore"]
        keys = nikeys + setkeys + ["socket"]

        settings = {}

        for key in keys:
            settings[key] = irssi.settings_get_str(key)

        for key in setkeys:
            settings[key] = set([i.lower() for i in settings[key].split()])

        for key in nikeys:
            if settings[key] not in ["notify", "ignore"]:
                irssi.prnt("RStatus: Warning: option " + key + " is invalid")

            settings[key] = (settings[key] == "notify")

        settings["socket"] = os.path.expanduser(settings["socket"])

        self.settings = settings

    def create_socket(self):
        self.clients = {}
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        try:
            os.unlink(self.settings["socket"])
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise
        self.socket.bind(self.settings["socket"])

        self.socket.setblocking(0)
        self.socket.listen(5)

        irssi.get_script().io_add_watch(self.socket, self.socket_activity,
                                        self.socket)

    def socket_activity(self, fd, condition, sock):
        if sock != self.socket or sock.fileno() != fd:
            return False

        try:
            (conn, address) = self.socket.accept()
        except:
            irssi.prnt("RStatus: Socket error:")
            irssi.prnt(traceback.format_exc())

            self.socket.close()
            self.socket = None
            return False

        if self.debug:
            irssi.prnt("RStatus: new client connected")

        if address == '':
            address = 'UNIX Socket'
        self.last_set("connect", address)

        conn.setblocking(False)

        clientinfo = {
            "send_queue": "",
            "recv_buffer": "",
            "send_messages": False,
            "watches": {},
            "timeouts": {}
        }

        clientinfo["watches"]["recv"] = \
            irssi.get_script().io_add_watch(conn, self.client_try_recv,
                                            conn, irssi.IO_IN)
        clientinfo["watches"]["err"] = \
            irssi.get_script().io_add_watch(conn, self.client_drop_ioerror,
                                            conn, irssi.IO_ERR)
        clientinfo["watches"]["hup"] = \
            irssi.get_script().io_add_watch(conn, self.client_drop_ioerror,
                                            conn, irssi.IO_HUP)

        self.clients[conn] = clientinfo

        self.client_timeout_set(conn, "recv", self.timeout_heartbeat,
                self.client_drop_timeout, (conn, "RECV Timeout (HB, F)"))
        self.client_new(conn)

        return True

    def client_timeout_set(self, conn, name, timeout, func, data=None):
        clientinfo = self.clients[conn]

        if name in clientinfo["timeouts"]:
            irssi.get_script().source_remove(clientinfo["timeouts"][name])

        clientinfo["timeouts"][name] = \
            irssi.get_script().timeout_add(timeout * 1000, func, data)

    def client_sendwatch_add(self, conn, watch):
        clientinfo = self.clients[conn]
        assert "send" not in clientinfo["watches"]

        clientinfo["watches"]["send"] = \
            irssi.get_script().io_add_watch(conn, self.client_try_send,
                                            conn, irssi.IO_OUT)

    def client_drop_timeout(self, conn, reason):
        self.client_drop(conn, reason)
        return False

    def client_drop_ioerror(self, fd, condition, conn):
        if conn not in self.clients or conn.fileno() != fd:
            return False

        if condition == irssi.IO_HUP:
            reason = "IO Hangup"
        elif condition == irssi.IO_ERR:
            reason = "IO Error"
        else:
            reason = "IO Error (U)"

        self.client_drop(conn, reason)
        return False

    def client_conn_close(self, conn):
        conn.shutdown(socket.SHUT_RDWR)
        conn.close()

    def client_drop(self, conn, reason, notify=False):
        if self.debug:
            irssi.prnt("RStatus: Dropping client: '{0}'".format(reason))
        self.last_set("drop", reason)

        clientinfo = self.clients[conn]
        del self.clients[conn]

        tags = clientinfo["watches"].values() + clientinfo["timeouts"].values()
        for tag in tags:
            irssi.get_script().source_remove(tag)

        if notify and len(clientinfo["send_queue"]) == 0:
            try:
                conn.send(json.dumps({"type": "disconnect_notice"}) + "\n")
            except:
                self.client_conn_close(conn)
            else:
                irssi.get_script().timeout_add(self.timeout_drop_notify * 1000,
                                               self.client_conn_close, conn)
        else:
            self.client_conn_close(conn)

    def client_try_recv(self, fd, condition, conn):
        if conn not in self.clients or conn.fileno() != fd:
            return False

        try:
            data = conn.recv(1024)
        except:
            if self.debug:
                irssi.prnt("RStatus: Client IO error:")
                irssi.prnt(traceback.format_exc())

            self.client_drop(conn, "RECV IO Error")
            return False

        if not data:
            if self.debug:
                irssi.prnt("RStatus: Client read failed")

            self.client_drop(conn, "RECV failed (EOF)")
            return False

        self.clients[conn]["recv_buffer"] += data

        if len(self.clients[conn]["recv_buffer"]) > self.cbuffer_limit:
            self.client_drop(conn, "RECV Buffer Overflow", notify=True)

        if "\n" in self.clients[conn]["recv_buffer"]:
            data_parts = self.clients[conn]["recv_buffer"].split("\n")
            self.clients[conn]["recv_buffer"] = data_parts[-1]
            data_parts = data_parts[:-1]

            for data in data_parts:
                if data == "":
                    continue

                try:
                    data = json.loads(data)
                    assert isinstance(data, dict)
                    self.client_recv(conn, data)
                except:
                    if self.debug:
                        irssi.prnt("RStatus: Client parse failed")
                        irssi.prnt(traceback.format_exc())

                    self.client_drop(conn, "RECV BAD JSON", notify=True)
                    return False

        if len(self.clients[conn]["recv_buffer"]) > 0:
            timeout = self.timeout_txrx
            reason = "RX"
        else:
            timeout = self.timeout_heartbeat
            reason = "HB"
        reason = "RECV Timeout ({0})".format(reason)

        self.client_timeout_set(conn, "recv", timeout,
                                self.client_drop_timeout, (conn, reason))

        return True

    def client_try_send(self, fd, condition, conn, init=False):
        if conn not in self.clients or (not init and conn.fileno() != fd):
            return False

        try:
            sent = conn.send(self.clients[conn]["send_queue"])
            if not init:
                assert sent > 0
        except Exception, e:
            if isinstance(e, socket.error) and e.errno == errno.EAGAIN and \
               init:
                sent = 0
            else:
                if self.debug:
                    irssi.prnt("RStatus: Client send failed")
                    irssi.prnt(traceback.format_exc())

                self.client_drop(conn, "SEND IO Error")
                return False

        self.clients[conn]["send_queue"] = \
            self.clients[conn]["send_queue"][sent:]

        if len(self.clients[conn]["send_queue"]) > 0:
            self.client_timeout_set(conn, "send", self.timeout_txrx,
                    self.client_drop_timeout, (conn, "SEND Timeout (TX)"))

            if "send" not in self.clients[conn]["watches"]:
                self.client_sendwatch_add(conn, True)

            return True
        else:
            self.client_timeout_set(conn, "send", self.timeout_heartbeat,
                                    self.client_heartbeat_send, conn)
            return False

    def client_reset(self, conn):
        self.client_send(conn, {"type": "reset"})
        self.client_new(conn)

    def client_new(self, conn):
        for window in filter(self.filter_event, self.window_all()):
            self.client_send(conn, window)

    def client_recv(self, conn, data):
        if data["type"] == "settings":
            if data["send_messages"]:
                self.clients[conn]["send_messages"] = True
            else:
                self.clients[conn]["send_messages"] = False
        elif data["type"] == "reset_request":
            self.client_reset(conn)

    def client_send(self, conn, data):
        data = json.dumps(data)
        assert "\n" not in data and len(data) < self.cbuffer_limit
        data += "\n"

        if len(self.clients[conn]["send_queue"]) != 0:
            self.clients[conn]["send_queue"] += data
            if len(self.clients[conn]["send_queue"]) > self.cbuffer_limit:
                self.client_drop(conn, "SEND Buffer Overflow")
        else:
            self.clients[conn]["send_queue"] = data
            self.client_try_send(None, None, conn, init=True)

    def client_heartbeat_send(self, conn):
        clientinfo = self.clients[conn]
        assert len(clientinfo["send_queue"]) == 0
        clientinfo["send_queue"] = "\n"
        self.client_try_send(None, None, conn, init=True)
        return False

if not getattr(irssi, "test_mode", False):
    rstatus = RStatus()
