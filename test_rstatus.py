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
import json
import collections
import errno

class FakeIrssiWindow:
    def __init__(self, name, data_level):
        self.data_level = data_level

        if name[0] == '#':
            self.active = FakeIrssiIrcChannel(name)
        else:
            self.active = FakeIrssiQuery(name)

class FakeIrssiServer:
    def __init__(self, nick="whatever", tag="TheServer"):
        self.nick = nick
        self.channels = {}
        self.tag = tag

    def channel_find(self, name):
        if name not in self.channels:
            return None
        else:
            return self.channels[name]

class FakeIrssiIrcChannel:
    def __init__(self, name, nicks=None, server=None):
        self.name = name
        self._nicks = []

        if nicks:
            self._nicks += nicks
        if server:
            self.server = server
            self._nicks += [server.nick]
        else:
            self.server = FakeIrssiServer()

    def nicks(self):
        return self._nicks

class FakeIrssiQuery:
    def __init__(self, name, server=None):
        self.name = name

        if server:
            self.server = server
        else:
            self.server = FakeIrssiServer()

class FakeIrssiModule:
    test_mode = True

    IrcChannel = FakeIrssiIrcChannel
    Query = FakeIrssiQuery

    (IO_IN, IO_OUT, IO_ERR, IO_HUP) = range(4, 8)

    def __init__(self):
        self.reset()

    def get_script(self):
        return self

    def reset(self):
        self.signals = {}
        self.timeouts = {}
        self.settings = {}
        self.iowatches = {}
        self._windows = []
        self.sourceid = 1

    def signal_add(self, name, func):
        assert name not in self.signals
        self.signals[name] = func

    def timeout_add(self, time, func, data=None):
        i = self.sourceid
        self.sourceid += 1
        self.timeouts[i] = [time, func, data]
        return i

    def io_add_watch(self, fd, func, data=None, iotype=None):
        i = self.sourceid
        self.sourceid += 1
        self.iowatches[i] = (fd, func, data, iotype)
        return i

    def source_remove(self, sid):
        if sid in self.iowatches:
            del self.iowatches[sid]
        elif sid in self.timeouts:
            del self.timeouts[sid]

    def settings_add_str(self, section, name, default):
        assert name not in self.settings
        self.settings[name] = {
            "section": section,
            "default": default,
            "value": default
        }

    def settings_get_str(self, name):
        return self.settings[name]["value"]

    def settings_set_str(self, name, value):
        self.settings[name]["value"] = value

    def prnt(self, text):
        for line in text.split("\n"):
            print "Irssi: " + line

    def add_window(self, window):
        self._windows.append(window)

    def windows(self):
        return self._windows

    def time_advance(self, amount):
        amount *= 1000

        while True:
            timeouts = self.timeouts.items()
            timeouts.sort(key=lambda x: x[1][0])

            if len(timeouts) == 0:
                break

            (first_id, first_timeout) = timeouts[0]
            step = min(amount, first_timeout[0])

            amount -= step
            for tid in self.timeouts:
                self.timeouts[tid][0] -= step

            if first_timeout[0] != 0:
                break

            data = first_timeout[2]
            if data != None:
                if not isinstance(data, collections.Sequence):
                    data = (data, )

                first_timeout[1](*data)
            else:
                first_timeout[1]()

            if first_id in self.timeouts:
                del self.timeouts[first_id]

    def proc_io(self):
        remove = []
        did_something = True

        while did_something:
            did_something = False

            for (key, (sock, func, data, typ)) in self.iowatches.items():
                call = False

                if sock.client:
                    if (typ == self.IO_ERR or typ == self.IO_HUP) and \
                       sock.closed:
                        call = True
                    if typ == self.IO_OUT and sock.sendable > 0:
                        call = True
                    if typ == self.IO_IN and sock.recvable != []:
                        call = True
                else:
                    if sock.acceptable:
                        call = True

                if call:
                    did_something = True

                    if data != None:
                        if not isinstance(data, collections.Sequence):
                            data = (data, )

                        ret = func(sock._fd, typ, *data)
                    else:
                        ret = func(sock._fd, typ)

                    if ret != True:
                        remove.append(key)

            for key in remove:
                if key in self.iowatches:
                    del self.iowatches[key]

class FakeSocketClass:
    next_fd = 0

    @classmethod
    def get_fd(cls):
        cls.next_fd += 1
        return cls.next_fd
    
    def __init__(self, family=None, stype=None, client=False):
        self.family = family
        self.stype = stype
        self.client = client
        self.called_bind = False
        self.called_listen = False
        self.called_setblocking = False
        self.called_shutdown = False
        self.acceptable = []
        self.sendable = 0
        self.sent = []
        self.recvable = []
        self.closed = False
        self.send_error = False
        self._fd = self.get_fd()

    def fileno(self):
        return self._fd

    def bind(self, addr):
        assert not self.client
        assert not self.called_bind
        assert not self.called_listen
        assert not self.closed
        self.called_bind = True
        self.addr = addr

    def setblocking(self, v):
        assert v == False
        assert not self.closed
        self.called_setblocking = True

    def listen(self, num):
        assert not self.client
        assert self.called_bind
        assert not self.closed
        assert num > 0
        self.called_listen = True

    def accept(self):
        assert not self.client
        assert not self.closed
        return self.acceptable.pop(0)

    def send(self, data):
        assert self.client
        assert self.called_setblocking
        assert not self.closed
        if self.send_error:
            raise self.send_error
        sent = min(self.sendable, len(data))
        self.sendable = max(0, self.sendable - len(data))
        self.sent.append((sent, data, data[:sent]))
        return sent

    def recv(self, data):
        assert self.client
        assert self.called_setblocking
        assert not self.closed
        return self.recvable.pop(0)

    def shutdown(self, arg):
        assert arg == FakeSocketModule.SHUT_RDWR
        self.called_shutdown = True

    def close(self):
        assert not self.client or self.called_shutdown
        self.closed = True

class FakeSocketError(Exception):
    errno = errno.EAGAIN

class FakeSocketModule:
    AF_UNIX = 123346
    SOCK_STREAM = 1244356
    SHUT_RDWR = 99

    error = FakeSocketError

    def __init__(self):
        self.reset()

    def reset(self):
        self.sockets = []

    def socket(self, family, stype):
        s = FakeSocketClass(family, stype)
        self.sockets.append(s)
        return s

class FakeOSPathModule:
    def expanduser(self, path):
        if len(path) and path[0:2] == '~/':
            return "/home/theuser/" + path[2:]
        else:
            return path

class FakeOSModule:
    def __init__(self):
        self.path = FakeOSPathModule()
        self.reset()

    def reset(self):
        self.unlinked_files = []

    def unlink(self, name):
        self.unlinked_files.append(name)

fakes = {}

# Irssi will fail to import so we have to add it manually beforehand...
sys.modules["irssi"] = fakes["irssi"] = FakeIrssiModule()
import rstatus

# The other modules can be swapped out
rstatus.socket = fakes["socket"] = FakeSocketModule()
rstatus.os = fakes["os"] = FakeOSModule()

# And now some constants
HEARTBEAT = 60 * 10
TXRX = 60
DROP_NOTIFY = 10
CBUFFER_LIMIT = 8192

def prepare_rstatus():
    for name, module in fakes.items():
        module.reset()

    return rstatus.RStatus(debug=True)

class TestSetup:
    def setup(self):
        self.rstatus = prepare_rstatus()

    def test_creates_settings(self):
        test_settings = {}
        for key, val in fakes["irssi"].settings.items():
            test_settings[key] = val["default"]

        assert test_settings == {
            "socket": "~/.irssi/rstatus_sock",
            "default_channels": "notify",
            "default_queries": "notify",
            "override_notify": "",
            "override_ignore": ""
        }

    def test_creates_socket(self):
        assert len(fakes["socket"].sockets) == 1
        s = fakes["socket"].sockets[0]
        assert s.called_bind
        assert s.called_setblocking
        assert s.called_listen
        assert fakes["irssi"].iowatches.values() == \
            [ (s, self.rstatus.socket_activity, s, None) ]

    def test_adds_signals(self):
        assert fakes["irssi"].signals == {
            "setup changed": self.rstatus.load_settings,
            "setup reread": self.rstatus.load_settings,
            "window hilight": self.rstatus.windowhilight,
            "message private": self.rstatus.privmsg,
            "message public": self.rstatus.pubmsg,
            "channel destroyed": self.rstatus.channeldestroyed,
            "query destroyed": self.rstatus.querydestroyed
        }
        assert fakes["irssi"].timeouts == {}

class TestConfig:
    def setup(self):
        self.rstatus = prepare_rstatus()

    def test_default(self):
        assert self.rstatus.settings == {
            "socket": "/home/theuser/.irssi/rstatus_sock",
            "default_channels": True,
            "default_queries": True,
            "override_notify": set(),
            "override_ignore": set()
        }

    def test_other(self):
        new_settings = {
            "socket": "asdfasdfasdf",
            "default_channels": "ignore",
            "default_queries": "notify",
            "override_notify": '#SUPERcoolchannel mUm',
            "override_ignore": 'sibling   \t\t\n #sPAm\tsibling'
        }
        for key, value in new_settings.items():
            fakes["irssi"].settings_set_str(key, value)
        self.rstatus.load_settings()

        assert self.rstatus.settings == {
            "socket": "asdfasdfasdf",
            "default_channels": False,
            "default_queries": True,
            "override_notify": set(["#supercoolchannel", "mum"]),
            "override_ignore": set(["sibling", "#spam"])
        }

class TestSignals:
    def setup(self):
        self.rstatus = prepare_rstatus()
        self.rstatus.update = self.grab_info
        self.infos = []

    def grab_info(self, info):
        self.infos.append(info)

    def test_windowhilight(self):
        window = FakeIrssiWindow("#achannel", 1)
        self.rstatus.windowhilight(window)
        assert self.infos == [ {
            "channel": "#achannel",
            "level": 1,
            "wtype": "channel",
            "type": "window_level",
            "server": "TheServer"
        } ]
        self.infos = []

        window = FakeIrssiWindow("nickname", 3)
        self.rstatus.windowhilight(window)
        assert self.infos == [ {
            "nick": "nickname",
            "server": "TheServer",
            "level": 3,
            "wtype": "query",
            "type": "window_level"
        } ]

    def test_privmsg(self):
        self.rstatus.privmsg(FakeIrssiServer(), "Hello", "Sibling", None)
        assert self.infos == [ {
            "nick": "Sibling",
            "server": "TheServer",
            "type": "message",
            "wtype": "query",
            "message": "Hello"
        } ]

    def test_pubmsg(self):
        server = FakeIrssiServer("mynicknamE")
        self.rstatus.pubmsg(server, "no hilight here", "source", None, "#ch")
        self.rstatus.pubmsg(server, "no hilight here", "hilight", None, "#ab")
        self.rstatus.pubmsg(server, "asdfmynicknameasdf", "source", None, "#c")
        self.rstatus.pubmsg(server, "mynickname: hi", "good", None, "#ch4nnel")
        self.rstatus.pubmsg(server, "you, MYnickname: y", "good", None, "#d")
        self.rstatus.pubmsg(server, "???mynickname???", "good", None, "#e")
        self.rstatus.pubmsg(server, "mynickname", "good", None, "#f")
        assert len(self.infos) == 4
        assert map(lambda x: x["nick"], self.infos) == ["good"] * 4
        assert self.infos[0] == {
            "channel": "#ch4nnel",
            "nick": "good",
            "type": "message",
            "wtype": "channel",
            "message": "mynickname: hi",
            "server": "TheServer"
        }

        self.infos = []
        server = FakeIrssiServer("mynick,name")
        server.channels["#sym"] = FakeIrssiIrcChannel("#sym", ["mynick!name"],
                                                      server)
        self.rstatus.pubmsg(server, "???mynick!name???", "none", None, "#sym")
        self.rstatus.pubmsg(server, "mynick!name", "good", None, "#fff")
        assert map(lambda x: x["nick"], self.infos) == ["good"]

    def test_channeldestroyed(self):
        channel = FakeIrssiIrcChannel("#sYm")
        self.rstatus.channeldestroyed(channel)
        assert self.infos == \
            [{"channel": "#sYm", "server": "TheServer", "level": 0,
              "type": "window_level", "wtype": "channel"}]

    def test_querydestroyed(self):
        query = FakeIrssiQuery("asdfblaH")
        self.rstatus.querydestroyed(query)
        assert self.infos == \
            [{"nick": "asdfblaH", "server": "TheServer", "level": 0,
              "type": "window_level", "wtype": "query"}]

class TestFiltering:
    def setup(self):
        self.rstatus = prepare_rstatus()
        self.rstatus.client_send = self.grab_info

        self.rstatus.clients["msgs"] = {"send_messages": True}
        self.rstatus.clients["nomsgs"] = {"send_messages": False}

    def grab_info(self, client, info):
        self.infos.append((client, info))

    def example_messages(self):
        server = FakeIrssiServer("mynickname")
        self.rstatus.pubmsg(server, "mynickname: hi", "good", None, "#ch4nnel")
        self.rstatus.privmsg(server, "Hello", "Blah", None)
        self.rstatus.privmsg(server, "Hello", "Sibling", None)
        self.rstatus.pubmsg(server, "mynickname: hi", "good", None, "#spaM")

    def example_hilights(self):
        self.rstatus.windowhilight(FakeIrssiWindow("nickname", 3))
        self.rstatus.windowhilight(FakeIrssiWindow("#importantstuff", 3))

    def test_messages_defaults(self):
        self.infos = []
        self.example_messages()
        assert map(lambda x: x[0], self.infos) == ["msgs"] * 4

        self.infos = []
        self.rstatus.settings["default_queries"] = False
        self.example_messages()
        assert map(lambda x: x[1]["wtype"], self.infos) == ["channel"] * 2

        self.infos = []
        self.rstatus.settings["default_queries"] = True
        self.rstatus.settings["default_channels"] = False
        self.example_messages()
        assert map(lambda x: x[1]["wtype"], self.infos) == ["query"] * 2

    def get_name(self, obj):
        if obj[1]["wtype"] == "channel":
            return obj[1]["channel"]
        else:
            return obj[1]["nick"]

    def test_override_ignore(self):
        self.infos = []
        self.rstatus.settings["default_queries"] = False
        self.rstatus.settings["override_ignore"] = ["#spam"]
        self.example_messages()
        assert map(lambda x: x[1]["channel"], self.infos) == ["#ch4nnel"]

        self.infos = []
        self.rstatus.settings["default_queries"] = True
        self.rstatus.settings["default_channels"] = False
        self.rstatus.settings["override_ignore"] = ["blah"]
        self.rstatus.settings["override_notify"] = ["#spam"]
        self.example_messages()
        assert map(self.get_name, self.infos) == ["Sibling", "#spaM"]

    def test_client_msgs(self):
        self.infos = []
        self.example_hilights()
        self.example_messages()

        assert len(filter(lambda x: x[0] == "msgs", self.infos)) == 6
        nmis = filter(lambda x: x[0] == "nomsgs", self.infos)
        assert map(lambda x: x[1]["type"], nmis) == ["window_level"] * 2

class TestIO:
    def setup(self):
        self.rstatus = prepare_rstatus()
        self.socket = fakes["socket"].sockets[0]
        self.nops = 0

    def create_client(self, sendable=None):
        client = FakeSocketClass(client=True)
        if sendable:
            client.sendable = sendable
        self.socket.acceptable.append((client, ''))
        assert self.rstatus.socket_activity(self.socket._fd, None, self.socket)
        clientinfo = self.rstatus.clients[client]
        return (client, clientinfo)

    def client_nop(self, *args, **kwargs):
        self.nops += 1

    def test_accept(self):
        self.rstatus.new_client = self.client_nop
        (client, clientinfo) = self.create_client()
        assert not self.socket.closed and self.rstatus.socket
        assert self.socket.acceptable == []
        assert client.called_setblocking

        assert set(clientinfo["watches"].keys()) == \
            set(["recv", "err", "hup"])
        assert len(fakes["irssi"].iowatches) == 4

        for watch_what, watch_id in clientinfo["watches"].items():
            if watch_what == "recv":
                func = self.rstatus.client_try_recv
                iotype = FakeIrssiModule.IO_IN
            else:
                func = self.rstatus.client_drop_ioerror
                iotype = getattr(FakeIrssiModule, "IO_" + watch_what.upper())

            watch = fakes["irssi"].iowatches[watch_id]
            assert watch == (client, func, client, iotype)

        assert len(clientinfo["timeouts"])
        assert len(fakes["irssi"].timeouts) == 1
        (a, b, c) = fakes["irssi"].timeouts[clientinfo["timeouts"]["recv"]]
        assert (a, b, c[0]) == \
            (HEARTBEAT * 1000, self.rstatus.client_drop_timeout, client)

        del clientinfo["watches"]
        del clientinfo["timeouts"]
        assert self.rstatus.clients[client] == \
            {"send_queue": "", "recv_buffer": "", "send_messages": False}

    def test_accept_err(self):
        self.rstatus.socket_activity(self.socket._fd, None, self.socket)
        assert self.socket.closed
        assert self.rstatus.socket == None

    def test_accept_other(self):
        assert not self.rstatus.socket_activity(FakeSocketClass()._fd, None,
                                                self.socket)
        assert not self.rstatus.socket_activity(self.socket._fd, None,
                                                FakeSocketClass())
        assert self.rstatus.socket == self.socket
        assert not self.socket.closed

    def test_client_timeout_set(self):
        self.rstatus.clients["c"] = { "timeouts": {} }
        self.rstatus.client_timeout_set("c", "test", 100, "function", 123)
        tid = self.rstatus.clients["c"]["timeouts"]["test"]
        assert fakes["irssi"].timeouts[tid] == \
            [100000, "function", 123]
        self.rstatus.client_timeout_set("c", "test", 10, "function", 4)
        assert tid not in fakes["irssi"].timeouts
        tid2 = self.rstatus.clients["c"]["timeouts"]["test"]
        assert fakes["irssi"].timeouts[tid2] == \
            [10000, "function", 4]

    def test_client_drop(self):
        fakes["irssi"]._windows.append(FakeIrssiWindow("asdf", 0))
        (client, clientinfo) = self.create_client(sendable=1)

        self.rstatus.client_timeout_set(client, "test", 10, "function", 4)
        self.rstatus.client_timeout_set(client, "tes2", 10, "function", 4)
        self.rstatus.client_timeout_set(client, "tes3", 10, "function", 4)
        assert len(fakes["irssi"].timeouts) == 5
        assert len(fakes["irssi"].iowatches) == 5
        assert self.rstatus.clients[client]["send_queue"] != ""

        self.rstatus.client_drop(client, "TEST", notify=True)
        assert len(fakes["irssi"].timeouts) == 0
        assert len(fakes["irssi"].iowatches) == 1
        assert self.rstatus.clients == {}

    def test_client_drop_notify(self):
        (client, clientinfo) = self.create_client()

        self.rstatus.client_drop(client, "TEST", notify=True)
        assert len(fakes["irssi"].iowatches) == 1
        assert self.rstatus.clients == {}
        assert fakes["irssi"].timeouts.values()[0] == \
            [DROP_NOTIFY * 1000, self.rstatus.client_conn_close, client]

    def check_timeout(self, name, time, client, clientinfo, func=None):
        tid = clientinfo["timeouts"][name]
        (a, b, c) = fakes["irssi"].timeouts[tid]
        if func == None:
            func = self.rstatus.client_drop_timeout
            assert (a, b, c[0]) == (time * 1000, func, client)

    def test_client_try_recv(self):
        client = FakeSocketClass(client=True)
        rargs = (client._fd, None, client)
        assert self.rstatus.client_try_recv(*rargs) == False

        for i in [None, (client.recvable.append, None)]:
            (client, clientinfo) = self.create_client()
            rargs = (client._fd, None, client)
            if i: i[0](i[1])
            assert client in self.rstatus.clients
            assert self.rstatus.client_try_recv(*rargs) == False
            assert client.closed
            assert client not in self.rstatus.clients

        data = []
        self.rstatus.client_recv = lambda x,y: data.append(y)
        (client, clientinfo) = self.create_client()
        rargs = (client._fd, None, client)

        o1 = {"asdf": "Hello World", "abc": 123}
        o2 = {"whatever": "you say", "boo": True}
        o3 = {"a long string": "of random garbagewarbagewarble"}

        client.recvable.append(json.dumps(o1) + "\n")
        assert self.rstatus.client_try_recv(*rargs) == True
        assert data == [o1]
        assert clientinfo["recv_buffer"] == ""

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        s2 = json.dumps(o2) + "\n"
        s3 = json.dumps(o3) + "\n"
        s = s2 + s3
        p = len(s2) + 1 + (len(s3) / 2)
        client.recvable.append(s[:p])
        client.recvable.append(s[p:])

        assert self.rstatus.client_try_recv(*rargs) == True
        assert clientinfo["recv_buffer"] != ""
        assert data == [o1, o2]

        self.check_timeout("recv", TXRX, client, clientinfo)

        assert self.rstatus.client_try_recv(*rargs) == True
        assert clientinfo["recv_buffer"] == ""
        assert data == [o1, o2, o3]

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        client.recvable.append(s)
        assert self.rstatus.client_try_recv(*rargs) == True
        assert data == [o1, o2, o3, o2, o3]
        assert client in self.rstatus.clients

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        client.recvable.append("json, what][dsf[a]sd[f\n\nasdfSDFGDS\n")
        assert self.rstatus.client_try_recv(*rargs) == False
        fakes["irssi"].time_advance(DROP_NOTIFY)
        assert client.closed
        assert client not in self.rstatus.clients
        assert len(data) == 5

    def test_client_try_send(self):
        client = FakeSocketClass(client=True)
        sargs = (client._fd, None, client)
        assert self.rstatus.client_try_send(*sargs) == False

        for i in [("send_error", Exception), ("sendable", 0),
                  ("send_error", fakes["socket"].error)]:
            (client, clientinfo) = self.create_client()
            sargs = (client._fd, None, client)
            setattr(client, i[0], i[1])
            assert client in self.rstatus.clients
            assert self.rstatus.client_try_send(*sargs) == False
            assert client.closed
            assert client not in self.rstatus.clients

        (client, clientinfo) = self.create_client()
        sargs = (client._fd, None, client)
        client.send_error = fakes["socket"].error()
        clientinfo["send_queue"] = "aaacbbbbbb"
        assert self.rstatus.client_try_send(*sargs, init=True) == True
        self.rstatus.client_drop(client, "TEST")

        (client, clientinfo) = self.create_client()
        sargs = (client._fd, None, client)
        clientinfo["send_queue"] = "aaacbbbbbb"

        client.sendable = 4
        assert self.rstatus.client_try_send(*sargs) == True

        self.check_timeout("send", TXRX, client, clientinfo)

        assert "send" in clientinfo["watches"]
        assert len(fakes["irssi"].iowatches) == 5

        client.sendable = 100
        assert self.rstatus.client_try_send(*sargs) == False
        self.check_timeout("send", HEARTBEAT, client, clientinfo,
                           func=self.rstatus.client_heartbeat_send)
        assert client.sent == [
            (4, "aaacbbbbbb", "aaac"),
            (6, "bbbbbb", "bbbbbb")
        ]

    def test_client_send(self):
        test_object = {
            "avalue": "a quite long string of data data num num num num",
            "bvalue": "a quite long string of data data num num num num",
            "cvalue": "a quite long string of data data num num num num",
            "dvalue": "a quite long string of data data num num num num"
        }
        test_strings = []
        test_strings_nonewl = []

        (client, clientinfo) = self.create_client()

        client.sendable = 8192
        assert clientinfo["send_queue"] == ""
        self.rstatus.client_send(client, test_object)
        assert len(client.sent) == 1
        test_strings.append(client.sent[0][1])

        self.rstatus.client_try_send = self.client_nop

        client.sendable = 8192
        assert clientinfo["send_queue"] == ""
        self.rstatus.client_send(client, test_object)
        test_strings.append(clientinfo["send_queue"])
        assert self.nops == 1

        client.sendable = 10
        clientinfo["send_queue"] = ""
        self.rstatus.client_send(client, test_object)
        assert self.nops == 2
        self.rstatus.client_send(client, test_object)
        assert self.nops == 2
        p = clientinfo["send_queue"].split("\n")
        assert len(p) == 3 and p[2] == ""
        test_strings_nonewl += p[:2]

        for s in test_strings:
            assert s[-1] == "\n"
            test_strings_nonewl.append(s[:-1])

        for s in test_strings_nonewl:
            assert json.loads(s) == test_object

        while len(clientinfo["send_queue"]) <= CBUFFER_LIMIT:
            assert self.nops == 2
            self.rstatus.client_send(client, test_object)

        # Test dropped
        assert client.closed
        assert client not in self.rstatus.clients

    def test_client_recv(self):
        true_object = {
            "type": "settings",
            "send_messages": True
        }
        false_object = true_object.copy()
        false_object["send_messages"] = False

        (client, clientinfo) = self.create_client()
        assert clientinfo["send_messages"] == False

        for test in [true_object, false_object, true_object, false_object]:
            self.rstatus.client_recv(client, test)
            assert clientinfo["send_messages"] == test["send_messages"]

        rargs = (client._fd, None, client)

        for test in [(True, true_object), (False, false_object),
                     (False, true_object), (True, false_object)]:
            s = json.dumps(test[1]) + "\n"
            if test[0]:
                p = max(2, len(s) / 2 - 4)
                client.recvable.append(s[:p])
                client.recvable.append(s[p:])

                assert self.rstatus.client_try_recv(*rargs) == True
                assert self.rstatus.client_try_recv(*rargs) == True
            else:
                client.recvable.append(s)
                assert self.rstatus.client_try_recv(*rargs) == True

            assert client.recvable == []
            assert clientinfo["send_messages"] == test[1]["send_messages"]

        client.sendable = 60000
        test_object = {"type": "reset_request"}
        self.rstatus.client_recv(client, test_object)
        assert json.loads(client.sent[0][1]) == {"type": "reset"}

        client.sent = []
        self.newtest_windows_create()
        self.rstatus.client_recv(client, test_object)
        assert json.loads(client.sent.pop(0)[1]) == {"type": "reset"}
        self.newtest_windows_check(client)

    def test_client_heartbeat_send(self):
        (client, clientinfo) = self.create_client()

        client.sendable = 1
        self.rstatus.client_heartbeat_send(client)
        assert client.sent == [(1, "\n", "\n")]
        assert clientinfo["send_queue"] == ""

        self.rstatus.client_try_send = self.client_nop
        self.rstatus.client_heartbeat_send(client)
        assert clientinfo["send_queue"] == "\n"
        assert self.nops == 1

    def newtest_windows_create(self):
        fakes["irssi"]._windows.append(FakeIrssiWindow("asdf", 1))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#spam", 0))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#blah", 3))
        self.rstatus.settings["override_ignore"].add("#spam")

    def test_client_new(self):
        self.newtest_windows_create()
        (client, clientinfo) = self.create_client(sendable=20000)
        self.newtest_windows_check(client)

    def newtest_windows_check(self, client):
        assert map(lambda x: x[1][-1], client.sent) == ["\n"] * 2
        assert map(lambda x: json.loads(x[1][:-1]), client.sent) == \
            [ { "nick": "asdf", "level": 1, "server": "TheServer",
                "wtype": "query", "type": "window_level" },
            { "channel": "#blah", "level": 3, "server": "TheServer",
                "wtype": "channel", "type": "window_level" } ]

    def test_hup(self):
        (client, clientinfo) = self.create_client(sendable=20000)
        client.closed = True
        fakes["irssi"].proc_io()

        assert client not in self.rstatus.clients

class TestExampleClients:
    def setup(self):
        self.rstatus = prepare_rstatus()
        self.socket = fakes["socket"].sockets[0]

    def create_client(self, sendable):
        client = FakeSocketClass(client=True)
        client.sendable = sendable
        self.socket.acceptable.append((client, ''))
        fakes["irssi"].proc_io()
        return client

    def create_windows(self):
        fakes["irssi"]._windows.append(FakeIrssiWindow("ASdf", 1))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#Spam", 0))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#blah", 3))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#bleh", 0))
        self.rstatus.settings["override_ignore"] = "#spam"

    def test_lagless(self):
        self.create_windows()
        client = self.create_client(sendable=60000)
        data = ''.join(map(lambda x: x[1], client.sent))
        data = map(json.loads, data.strip().split("\n"))

        assert data == \
            [ { "nick": "ASdf", "level": 1, "server": "TheServer",
                "wtype": "query", "type": "window_level" },
              { "channel": "#blah", "level": 3, "server": "TheServer",
                "wtype": "channel", "type": "window_level" },
              { "channel": "#bleh", "level": 0, "server": "TheServer",
                "wtype": "channel", "type": "window_level" } ]
        client.sent = []

        client.recvable.append(json.dumps({"type": "settings",
                                           "send_messages": True}) + "\n")
        fakes["irssi"].proc_io()

        fakes["irssi"].time_advance(HEARTBEAT - 1)
        client.recvable.append("\n")
        fakes["irssi"].proc_io()
        fakes["irssi"].time_advance(2)

        assert client.sent[0][1] == "\n"

        server = FakeIrssiServer("mynickname")
        self.rstatus.pubmsg(server, "mynickname: hi", "dude", None, "#spam")
        self.rstatus.pubmsg(server, "mynickname: hi", "dude", None, "#bleh")
        assert json.loads(client.sent[1][1][:-1]) == \
            { "channel": "#bleh", "nick": "dude", "type": "message",
              "wtype": "channel", "message": "mynickname: hi",
              "server": "TheServer" }
        assert len(client.sent) == 2

        client.recvable.append(json.dumps({"type": "settings",
                                           "send_messages": False}) + "\n")
        fakes["irssi"].proc_io()

        client.sent = []

        self.rstatus.pubmsg(server, "mynickname: hi", "dude", None, "#bleh")
        assert len(client.sent) == 0

        fakes["irssi"].time_advance((HEARTBEAT / 2) + 3)
        client.recvable.append("\n")
        fakes["irssi"].proc_io()
        assert not client.closed

        for i in xrange(10):
            fakes["irssi"].time_advance(HEARTBEAT - 1)
            assert not client.closed
            client.recvable.append("\n")
            fakes["irssi"].proc_io()
            assert not client.closed

        for s in client.sent:
            assert s == (1, "\n", "\n")
        assert len(client.sent) > 4

        client.sent = []
        client.recvable.append(json.dumps({"type": "reset_request"}) + "\n")
        fakes["irssi"].proc_io()

        ndata = ''.join(map(lambda x: x[1], client.sent))
        ndata = map(json.loads, ndata.strip().split("\n"))
        assert ndata == [{"type": "reset"}] + data


    def test_laggy(self):
        self.create_windows()
        # two clients. one laggy, one disconnect
        # test read and send buffers

        laggy_client = self.create_client(sendable=10)
        disconnect_client = self.create_client(sendable=60000)

        s = json.dumps({"type": "settings", "send_messages": True}) + "\n"
        p = len(s) / 2
        laggy_client.recvable.append(s[:p])
        fakes["irssi"].proc_io()
        fakes["irssi"].time_advance(2)
        laggy_client.recvable.append(s[p:])
        fakes["irssi"].proc_io()

        k = 0
        while laggy_client.sendable == 0:
            fakes["irssi"].time_advance(1)
            laggy_client.sendable = 50
            fakes["irssi"].proc_io()
            k += 1
        assert k > 4 and k < 30

        laggy_client.sent = []
        laggy_client.sendable = 60000

        self.rstatus.privmsg(FakeIrssiServer(), "Hello", "Sibling", None)
        assert len(laggy_client.sent) == 1
        assert json.loads(laggy_client.sent[0][1]) == \
            {"nick": "Sibling", "type": "message", "wtype": "query",
             "message": "Hello", "server": "TheServer" }

        laggy_client.recvable.append("\n")
        fakes["irssi"].proc_io()
        fakes["irssi"].time_advance(HEARTBEAT - 1)

        assert disconnect_client.closed
        assert not laggy_client.closed

        self.rstatus.privmsg(FakeIrssiServer(), "Hello", "Sibling", None)
        assert len(laggy_client.sent) == 2

    def test_mute(self):
        client = FakeSocketClass(client=True)
        self.socket.acceptable.append((client, ''))
        self.rstatus.socket_activity(self.socket._fd, None, self.socket)
        assert not client.closed
        fakes["irssi"].time_advance(HEARTBEAT - 1)
        assert not client.closed
        fakes["irssi"].time_advance(2)
        assert client.closed
