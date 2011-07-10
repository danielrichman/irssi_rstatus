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

class FakeIrssiWindow:
    def __init__(self, name, refnum, data_level):
        self.refnum = refnum
        self.data_level = data_level

        if name[0] == '#':
            self.active = FakeIrssiIrcChannel(name)
        else:
            self.active = FakeIrssiQuery(name)

class FakeIrssiChannel:
    def __init__(self, nicks, server):
        self._nicks = nicks + [server.nick]

    def nicks(self):
        return self._nicks

class FakeIrssiServer:
    def __init__(self, nick):
        self.nick = nick
        self.channels = {}

    def channel_find(self, name):
        if name not in self.channels:
            return None
        else:
            return self.channels[name]

class FakeIrssiIrcChannel:
    def __init__(self, name):
        self.name = name

class FakeIrssiQuery:
    def __init__(self, name):
        self.name = name

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

            if first_timeout[2] != None:
                first_timeout[1](first_timeout[2])
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
                        ret = func(data)
                    else:
                        ret = func()

                    if ret != True:
                        remove.append(key)

            for key in remove:
                if key in self.iowatches:
                    del self.iowatches[key]

class FakeSocketClass:
    def __init__(self, family=None, stype=None, client=False):
        self.family = family
        self.stype = stype
        self.client = client
        self.called_bind = False
        self.called_listen = False
        self.called_setblocking = False
        self.acceptable = []
        self.sendable = 0
        self.sent = []
        self.recvable = []
        self.closed = False
        self.send_error = False

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
        assert not self.send_error
        sent = min(self.sendable, len(data))
        self.sendable = max(0, self.sendable - len(data))
        self.sent.append((sent, data, data[:sent]))
        return sent

    def recv(self, data):
        assert self.client
        assert self.called_setblocking
        assert not self.closed
        return self.recvable.pop(0)

    def close(self):
        self.closed = True

class FakeSocketModule:
    AF_UNIX = 123346
    SOCK_STREAM = 1244356

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
            "message public": self.rstatus.pubmsg
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
        window = FakeIrssiWindow("#achannel", 36, 1)
        self.rstatus.windowhilight(window)
        assert self.infos == [ {
            "name": "#achannel",
            "refnum": 36,
            "level": 1,
            "wtype": "channel",
            "type": "window_level"
        } ]
        self.infos = []

        window = FakeIrssiWindow("nickname", 123, 3)
        self.rstatus.windowhilight(window)
        assert self.infos == [ {
            "name": "nickname",
            "refnum": 123,
            "level": 3,
            "wtype": "query",
            "type": "window_level"
        } ]

    def test_privmsg(self):
        self.rstatus.privmsg(None, "Hello", "Sibling", None, None)
        assert self.infos == [ {
            "name": "sibling",
            "type": "message",
            "wtype": "query",
            "message": "Hello"
        } ]

    def test_pubmsg(self):
        server = FakeIrssiServer("mynickname")
        self.rstatus.pubmsg(server, "no hilight here", "source", None, "#ch")
        self.rstatus.pubmsg(server, "no hilight here", "hilight", None, "#ab")
        self.rstatus.pubmsg(server, "asdfmynicknameasdf", "source", None, "#c")
        self.rstatus.pubmsg(server, "mynickname: hi", "good", None, "#ch4nnel")
        self.rstatus.pubmsg(server, "you, mynickname: y", "gooD", None, "#d")
        self.rstatus.pubmsg(server, "???mynickname???", "Good", None, "#e")
        self.rstatus.pubmsg(server, "mynickname", "gOOd", None, "#f")
        assert len(self.infos) == 4
        assert map(lambda x: x["who"], self.infos) == ["good"] * 4
        assert self.infos[0] == {
            "name": "#ch4nnel",
            "who": "good",
            "type": "message",
            "wtype": "channel",
            "message": "mynickname: hi"
        }

        self.infos = []
        server = FakeIrssiServer("mynick,name")
        server.channels["#sym"] = FakeIrssiChannel(["mynick!name"], server)
        self.rstatus.pubmsg(server, "???mynick!name???", "none", None, "#sym")
        self.rstatus.pubmsg(server, "mynick!name", "gOOd", None, "#fff")
        assert map(lambda x: x["who"], self.infos) == ["good"]

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
        self.rstatus.privmsg(None, "Hello", "Blah", None, None)
        self.rstatus.privmsg(None, "Hello", "Sibling", None, None)
        self.rstatus.pubmsg(server, "mynickname: hi", "good", None, "#spam")

    def example_hilights(self):
        self.rstatus.windowhilight(FakeIrssiWindow("nickname", 123, 3))
        self.rstatus.windowhilight(FakeIrssiWindow("#importantstuff", 223, 3))

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

    def test_override_ignore(self):
        self.infos = []
        self.rstatus.settings["default_queries"] = False
        self.rstatus.settings["override_ignore"] = ["#spam"]
        self.example_messages()
        assert map(lambda x: x[1]["name"], self.infos) == ["#ch4nnel"]

        self.infos = []
        self.rstatus.settings["default_queries"] = True
        self.rstatus.settings["default_channels"] = False
        self.rstatus.settings["override_ignore"] = ["blah"]
        self.rstatus.settings["override_notify"] = ["#spam"]
        self.example_messages()
        assert map(lambda x: x[1]["name"], self.infos) == \
            ["sibling", "#spam"]

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
        assert self.rstatus.socket_activity(self.socket) == True
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
                func = self.rstatus.client_drop
                iotype = getattr(FakeIrssiModule, "IO_" + watch_what.upper())

            (a, b, c, d) = fakes["irssi"].iowatches[watch_id]
            if b == self.rstatus.client_drop:
                c = c[0]
            assert (a, b, c, d) == (client, func, client, iotype)

        assert len(clientinfo["timeouts"])
        assert len(fakes["irssi"].timeouts) == 1
        (a, b, c) = fakes["irssi"].timeouts[clientinfo["timeouts"]["recv"]]
        assert (a, b, c[0]) == \
            (HEARTBEAT * 1000, self.rstatus.client_drop, client)

        del clientinfo["watches"]
        del clientinfo["timeouts"]
        assert self.rstatus.clients[client] == \
            {"send_queue": "", "recv_buffer": "", "send_messages": False}

    def test_accept_err(self):
        self.rstatus.socket_activity(self.socket)
        assert self.socket.closed
        assert self.rstatus.socket == None

    def test_accept_other(self):
        self.rstatus.socket_activity(FakeSocketClass())
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
        fakes["irssi"]._windows.append(FakeIrssiWindow("asdf", 0, 0))
        (client, clientinfo) = self.create_client(sendable=1)

        self.rstatus.client_timeout_set(client, "test", 10, "function", 4)
        self.rstatus.client_timeout_set(client, "tes2", 10, "function", 4)
        self.rstatus.client_timeout_set(client, "tes3", 10, "function", 4)
        assert len(fakes["irssi"].timeouts) == 5
        assert len(fakes["irssi"].iowatches) == 5
        assert self.rstatus.clients[client]["send_queue"] != ""

        self.rstatus.client_drop((client, "TEST"), notify=True)
        assert len(fakes["irssi"].timeouts) == 0
        assert len(fakes["irssi"].iowatches) == 1
        assert self.rstatus.clients == {}

    def test_client_drop_notify(self):
        (client, clientinfo) = self.create_client()

        self.rstatus.client_drop((client, "TEST"), notify=True)
        assert len(fakes["irssi"].iowatches) == 1
        assert self.rstatus.clients == {}
        assert fakes["irssi"].timeouts.values()[0] == \
            [DROP_NOTIFY * 1000, client.close, None]

    def check_timeout(self, name, time, client, clientinfo, func=None):
        tid = clientinfo["timeouts"][name]
        (a, b, c) = fakes["irssi"].timeouts[tid]
        if func == None:
            func = self.rstatus.client_drop
            assert (a, b, c[0]) == (time * 1000, func, client)

    def test_client_try_recv(self):
        client = FakeSocketClass(client=True)
        assert self.rstatus.client_try_recv(client) == False

        for i in [None, (client.recvable.append, None)]:
            (client, clientinfo) = self.create_client()
            if i: i[0](i[1])
            assert client in self.rstatus.clients
            assert self.rstatus.client_try_recv(client) == False
            assert client.closed
            assert client not in self.rstatus.clients

        data = []
        self.rstatus.client_recv = lambda x,y: data.append(y)
        (client, clientinfo) = self.create_client()

        o1 = {"asdf": "Hello World", "abc": 123}
        o2 = {"whatever": "you say", "boo": True}
        o3 = {"a long string": "of random garbagewarbagewarble"}

        client.recvable.append(json.dumps(o1) + "\n")
        assert self.rstatus.client_try_recv(client) == True
        assert data == [o1]
        assert clientinfo["recv_buffer"] == ""

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        s2 = json.dumps(o2) + "\n"
        s3 = json.dumps(o3) + "\n"
        s = s2 + s3
        p = len(s2) + 1 + (len(s3) / 2)
        client.recvable.append(s[:p])
        client.recvable.append(s[p:])

        assert self.rstatus.client_try_recv(client) == True
        assert clientinfo["recv_buffer"] != ""
        assert data == [o1, o2]

        self.check_timeout("recv", TXRX, client, clientinfo)

        assert self.rstatus.client_try_recv(client) == True
        assert clientinfo["recv_buffer"] == ""
        assert data == [o1, o2, o3]

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        client.recvable.append(s)
        assert self.rstatus.client_try_recv(client) == True
        assert data == [o1, o2, o3, o2, o3]
        assert client in self.rstatus.clients

        self.check_timeout("recv", HEARTBEAT, client, clientinfo)

        client.recvable.append("json, what][dsf[a]sd[f\n\nasdfSDFGDS\n")
        assert self.rstatus.client_try_recv(client) == False
        fakes["irssi"].time_advance(DROP_NOTIFY)
        assert client.closed
        assert client not in self.rstatus.clients
        assert len(data) == 5

    def test_client_try_send(self):
        client = FakeSocketClass(client=True)
        assert self.rstatus.client_try_send(client) == False

        for i in [("send_error", True), ("sendable", 0)]:
            (client, clientinfo) = self.create_client()
            setattr(client, i[0], i[1])
            assert client in self.rstatus.clients
            assert self.rstatus.client_try_send(client) == False
            assert client.closed
            assert client not in self.rstatus.clients

        (client, clientinfo) = self.create_client()
        clientinfo["send_queue"] = "aaacbbbbbb"

        client.sendable = 4
        assert self.rstatus.client_try_send(client) == True

        self.check_timeout("send", TXRX, client, clientinfo)

        assert "send" in clientinfo["watches"]
        assert len(fakes["irssi"].iowatches) == 5

        client.sendable = 100
        assert self.rstatus.client_try_send(client) == False
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

        for test in [(True, true_object), (False, false_object),
                     (False, true_object), (True, false_object)]:
            s = json.dumps(test[1]) + "\n"
            if test[0]:
                p = max(2, len(s) / 2 - 4)
                client.recvable.append(s[:p])
                client.recvable.append(s[p:])

                assert self.rstatus.client_try_recv(client) == True
                assert self.rstatus.client_try_recv(client) == True
            else:
                client.recvable.append(s)
                assert self.rstatus.client_try_recv(client) == True

            assert client.recvable == []
            assert clientinfo["send_messages"] == test[1]["send_messages"]

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

    def test_client_new(self):
        fakes["irssi"]._windows.append(FakeIrssiWindow("asdf", 4, 1))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#spam", 5, 0))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#blah", 6, 3))
        self.rstatus.settings["override_ignore"].add("#spam")

        (client, clientinfo) = self.create_client(sendable=20000)

        assert map(lambda x: x[1][-1], client.sent) == ["\n"] * 2
        assert map(lambda x: json.loads(x[1][:-1]), client.sent) == \
            [ { "name": "asdf", "refnum": 4, "level": 1,
                "wtype": "query", "type": "window_level" },
              { "name": "#blah", "refnum": 6, "level": 3,
                "wtype": "channel", "type": "window_level" } ]

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
        fakes["irssi"]._windows.append(FakeIrssiWindow("ASdf", 4, 1))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#Spam", 5, 0))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#blah", 6, 3))
        fakes["irssi"]._windows.append(FakeIrssiWindow("#bleh", 7, 0))
        self.rstatus.settings["override_ignore"] = "#spam"

    def test_lagless(self):
        self.create_windows()
        client = self.create_client(sendable=60000)
        data = ''.join(map(lambda x: x[1], client.sent))
        data = map(json.loads, data.strip().split("\n"))

        assert data == \
            [ { "name": "asdf", "refnum": 4, "level": 1,
                "wtype": "query", "type": "window_level" },
              { "name": "#blah", "refnum": 6, "level": 3,
                "wtype": "channel", "type": "window_level" },
              { "name": "#bleh", "refnum": 7, "level": 0,
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
            { "name": "#bleh", "who": "dude", "type": "message",
              "wtype": "channel", "message": "mynickname: hi" }
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

        self.rstatus.privmsg(None, "Hello", "Sibling", None, None)
        assert len(laggy_client.sent) == 1
        assert json.loads(laggy_client.sent[0][1]) == \
            {"name": "sibling", "type": "message", "wtype": "query",
             "message": "Hello" }

        laggy_client.recvable.append("\n")
        fakes["irssi"].proc_io()
        fakes["irssi"].time_advance(HEARTBEAT - 1)

        assert disconnect_client.closed
        assert not laggy_client.closed

        self.rstatus.privmsg(None, "Hello", "Sibling", None, None)
        assert len(laggy_client.sent) == 2

    def test_mute(self):
        client = FakeSocketClass(client=True)
        self.socket.acceptable.append((client, ''))
        self.rstatus.socket_activity(self.socket)
        assert not client.closed
        fakes["irssi"].time_advance(HEARTBEAT - 1)
        assert not client.closed
        fakes["irssi"].time_advance(2)
        assert client.closed