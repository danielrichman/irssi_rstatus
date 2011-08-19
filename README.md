irssi rstatus
=============

Licensing
---------

irssi_rstatus is Copyright (C) 2011  Daniel Richman

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

For a full copy of the GNU General Public License, 
see <http://www.gnu.org/licenses/>.

---

irssi_none.png, irssi_message.png, irssi_hilight.png aree derived from the
banner image http://irssi.org/images/irssitop.png from http://irssi.org/.
That file is Copyright (C) 2000-2011 The Irssi project.

Building and installing irssi-python
------------------------------------

The guide at http://sector-5.net/archives/irssi-python-for-irssi-0-8-15/ worked
perfectly for me, but I've included a patched tarball of the source in github
to make it easier.

Download irssi-python, irssi (for the headers). You'll need the python headers
available; these will be available in your distribution's package management.

Execute these commands on the server that will be running irssi.

    $ sudo aptitude install python-dev
    $ mkdir irssi-python-build
    $ cd irssi-python-build
    $ wget https://github.com/downloads/danielrichman/irssi_rstatus/irssi-python-ac.tar.gz
    $ wget http://irssi.org/files/irssi-0.8.15.tar.gz
    $ tar xvf irssi-python-ac.tar.gz
    $ tar xvf irssi-0.8.15.tar.gz
    $ cd irssi-python
    $ ./configure --with-irssi=../irssi-0.8.15
    $ make -C src constants
    $ make

libpython.so will then be at src/.libs/libpytho.so

It is then trivial to install irssi-python for your user (i.e., not system
wide) like so:

    $ mkdir -p ~/.irssi/modules ~/.irssi/scripts/autorun
    $ cp src/.libs/libpython.so ~/.irssi/modules/
    $ echo "load python" >> ~/.irssi/startup
    $ cp src/irssi.py src/irssi_startup.py ~/.irssi/scripts

Finally, add the irssi_rstatus plugin...

    $ cd ..
    $ git clone git://github.com/danielrichman/irssi_rstatus.git
    $ cp irssi_rstatus/rstatus.py ~/.irssi/scripts/autorun/

And clean up:

    $ cd ..
    $ rm -Rf irssi-python-build

Installing the client (Ubuntu)
------------------------------

The client is experimental/beta. Configuring it is a little ugly at the
moment. Don't worry, I'll make it nicer in the future; but if you want it now:

To install:

    $ git clone git://github.com/danielrichman/irssi_rstatus.git

Dependencies:

    $ sudo aptitude install python-gtk2 python-notify

Configuration:

    $ gedit irssi_rstatus/rstatus_notify.py

Scroll to the bottom, and look for:

    config = {
        "connect_command": ("ssh", "anapnea", "socat", "-T", "700",
                            "unix-client:.irssi/rstatus_sock",
                            "stdin!!stdout"),
        "icons_dir": os.path.realpath(os.path.dirname(__file__))
    }

You need to edit connect_command so that when that command is executed,
irssi_rstatus.py will be connected on standard in and standard out
to ~/.irssi/rstatus_sock on the server running irssi. To do this, I'm
using socat installed on the server, and I've got a ssh public key and
my ssh config setup so that when I type ssh anapnea, it connects to
my account at anapnea.net.

And now, to run it:

    $ python irssi_rstatus/rstatus_notify.py

You can put the irssi_rstatus folder somewhere where it won't bother you and
add python irssi_rstatus/rstatus_notify.py to execute on startup.
