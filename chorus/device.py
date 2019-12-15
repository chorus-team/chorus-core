# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Device base classes.
"""

import threading
import re
import ipaddress

from . import connection
from .log import getLog
from .config import Config
import sys
PY3 = (sys.version_info[0] >= 3)


class Device(object):
    """The base class for device.
    """
    prompt = "#"
    '''the default prompt after first login, or for all commands if no prompt_after defined in init_cmds.
    Accepts regular expression.
    '''
    init_cmds = {"cmds": [], "prompt_after": None}
    '''The default commands issued after each login of the device. These commands may also change the prompt.
    If so, use *prompt_after* to specify the new prompt.
    '''
    supported_con = []
    '''All supported connection methods by plugin name.
    '''
    #
    DEFAULT_ROOT = "root"
    DEFAULT_USER = "ubuntu"
    DEFAULT_PASSWORD = "ubuntu"

    def __init__(self, name="", **usrkwargs):
        """The supported connections,
            supported_con: the symbolic names of the supported connecion types, the first one is default
        """
        # pass params to extensions, also filters out garbase parameters
        super(Device, self).__init__()
        # named connections maintained by a device, default_* is the default
        # connection
        self.name = name
        self._connection = {}
        self.__dict__.update(usrkwargs)
        # The default connection
        self._c = None
        self.log = getLog(self.name)
        self._mac = {}
        self.default_conn_method = self.supported_con[0]
        # update default prompt
        pa = self.init_cmds.get("prompt_after")
        if pa:
            self.prompt = "%s|%s" % (self.prompt, pa)
        else:
            self.prompt = self.__class__.prompt

    def _getConnection(self, method='', tag=None, opened=False):
        """Get the device connection
        Connection are index with two parameters: thread ID and connection method.
        It's also possible to have multi connections on the same thread with the same method by specifying an extra tag
        """
        if not method:
            method = self.default_conn_method
        elif str(method).lower() not in self.supported_con:
            raise DeviceException(
                "Connection %s is not supported by device %s" %
                (method, self.name))
        method = str(method).lower()
        # For single connections like console, there is only one copy
        conn_name = self.name
        t = threading.currentThread()
        if not connection.uniqConn(method):
            conn_name = conn_name + "_%s_%s" % (t.name, method)
        elif t.name != "MainThread":
            # Give some warnning on multithread
            self.log.warning(
                "Single connection used with multi thread, conflict may happen")

        # Extra name tag in case multi connections required in one thread
        # Notice: Repetitive name found in vesa. check the reason
        if tag:
            conn_name = conn_name + "_" + tag

        # new connection only necessary
        if conn_name not in self._connection:
            # WARN An implicit arg passing, make sure args of parameter and
            # name of topo keywords are the same
            self._connection[conn_name] = connection.newConn(
                conn_name, method, **self.__dict__)

        if opened and not self._connection[conn_name].isOpen():
            self._connection[conn_name].prompt = self.prompt
            self._connection[conn_name].open()
            self.onFirstConnect(self._connection[conn_name])

        return self._connection[conn_name]

    def onFirstConnect(self, conn):
        """Execute init commands on specific connection"""
        # issue initial commands
        self.log.info(
            "Connecting for the first time, issuing initial commands.")
        cmd_key = "cmds"
        if conn.conn_name in self.init_cmds:
            # issue connection specific commands instead
            cmd_key = conn.conn_name
        for cmd in self.init_cmds[cmd_key]:
            conn.cmd(cmd)
        if "prompt_after" in self.init_cmds and self.init_cmds["prompt_after"] is not None:
            conn.prompt = self.init_cmds["prompt_after"]

    def setDefaultConnMethod(self, method):
        if method in self.supported_con:
            self.default_conn_method = method
        else:
            raise DeviceException(
                "Connection method %s not supported by %s" %
                (method, self.name))

    def connect(self, method=None, tag=None):
        """Connect to device"""
        self.log.info("Connecting to device: %s", self.name)
        self._getConnection(method, tag, opened=True)

    def reconnect(self, method=None, tag=None):
        """Reconnect the default connection"""
        self.log.info("Reconnecting to device: %s", self.name)
        self.disconnect(method, tag)
        self.connect(method=method, tag=tag)

    def reconnectAll(self):
        """Reconnect all existing connections, used for reboot"""
        for conn in self._connection.values():
            self.log.info("Reconnecting to device: %s, %s",
                          self.name, conn.name)
            # TODO: duplicate logic with `_getConnection`, combine them
            conn.prompt = self.prompt
            conn.reopen()
            self.onFirstConnect(conn)

    def disconnect(self, method=None, tag=None, force=False):
        """Disconnect the default connection"""
        self.log.info("Disconnecting device: %s", self.name)
        self._getConnection(method, tag).close(force)

    def disconnectAll(self):
        """Disconnect the default connection"""
        for conn_name, conn in self._connection.items():
            self.log.info("Disconncting device: %s, %s", self.name, conn_name)
            conn.close()

    def cmd(
            self,
            cmd,
            method=None,
            prompt=None,
            mid_prompts={},
            mid_ignore=False,
            timeout=None,
            control=False,
            nonewline=False,
            tag=None,
            failcontinue=False):
        """Send command to the device, and return the output, the parameters are the same as Connection:cmd"""
        self.log.info("Sending command: %s", cmd)
        # retry 3 times
        for _ in range(3):
            try:
                conn = self._getConnection(opened=True, method=method, tag=tag)
                out = conn.cmd(
                    cmd,
                    prompt=prompt,
                    mid_prompts=mid_prompts,
                    mid_ignore=mid_ignore,
                    timeout=timeout,
                    control=control,
                    nonewline=nonewline,
                    failcontinue=failcontinue)
                return out
            except Exception:
                self.log.warn("Command send failed, retrying...")
                self.reconnect(method, tag)
        raise DeviceException(
            "Failed issuing commend to device %s: '%s'" % (self.name, cmd))

    def testCmd(
            self,
            cmd,
            testreg,
            method=None,
            prompt=None,
            mid_prompts={},
            mid_ignore=False,
            timeout=None):
        """Send command to the device, check if the output match the teststings in sequence, return None or math object"""
        out = self.cmd(
            cmd,
            method=method,
            prompt=prompt,
            mid_prompts=mid_prompts,
            mid_ignore=mid_ignore,
            timeout=timeout)
        self.log.debug(
            "Check if string '%s' is contained in command: %s", testreg, cmd)
        return re.search(testreg, out, flags=0)

    def setIfIP(self, ifname, ipmask):
        """Set the ip address of a interface"""
        raise DeviceException(
            "Device %s do not support ip setting" % self.name)

    def getIfName(self, macaddress):
        """get the name of a interface by mac address"""
        raise DeviceException(
            "Device %s do not getting ifname by mac" % self.name)

    def reset(self):
        """Reset the device to initial state, should be overridden by subclasses"""
        self.disconnectAll()


############################
# Upgradable interface.
class Upgradable(object):
    """Upgradable device interface
    """

    def upgrade(self, server, image, user='', password=''):
        pass

    def upgradeDailybuild(self, path=None):
        pass


############################
# Interface classes, maybe need to be moved to elsewhere
class Interface(object):
    """Interface class"""

    def __init__(self, device, name):
        super(Interface, self).__init__()
        self.device = device
        self.intf = name
        self.name = name
        self._intf = None
        self.ip = None
        self.subnet = None
        self.netmask = None
        self.ipmask = None
        self.mac = None
        # track guest ip assignment state here
        self.guestipset = False

    def setIP(self, ipmask="", ip="", subnet=""):
        """Set the ip address from ipmask or ip + subnet"""
        # try ip mask first
        if ipmask:
            if PY3:
                self._intf = ipaddress.ip_interface(ipmask)
            else:
                self._intf = ipaddress.ip_interface(ipmask.decode('utf-8'))
        elif ip and subnet:
            if PY3:
                network = ipaddress.ip_network(subnet)
                self._intf = ipaddress.ip_interface(
                    ip + "/" + str(network.prefixlen))
            else:
                network = ipaddress.ip_network(subnet.decode('utf-8'))
                self._intf = ipaddress.ip_interface(
                    ip.decode('utf-8') + "/" + str(network.prefixlen))
        else:
            self.device.log.warn(
                "Cannot set interface ipaddress for: %s:%s" %
                (self.device.name, self.name))
            return False
        # beware of vesa
        self.ip = str(self._intf.ip)
        self.netmask = str(self._intf.netmask)
        self.ipmask = str(self._intf.with_prefixlen)
        return True

    def setMac(self, mac):
        self.mac = mac


############################
# Exception handling
class DeviceException(Exception):
    """Exception handling class for connection"""

    def __init__(self, value):
        super(DeviceException, self).__init__()
        self.value = "Connection Error due to: " + value
        getLog().exception("Connection Error happens: %s!!", value)

    def __str__(self):
        return repr(self.value)


########################
# methods
def getDevice(**kwargs):
    """Get a instance of a device

    :param kwargs: the arguments of the device class, among them `os` is a required argument which specifies the plugin tag.
    :return: a instance of the device
    """
    getLog().debug("Generating devices with the following parameters:")
    getLog().debug(kwargs)
    if "os" not in kwargs:
        raise DeviceException("Device type not specified")

    cls = Config().get_plugin("device", kwargs["os"].lower())
    if not cls:
        raise DeviceException("No such kind of device: %s" % kwargs["os"])
    return cls(**kwargs)
