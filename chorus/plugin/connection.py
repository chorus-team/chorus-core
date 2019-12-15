# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Connection class. pexpect based
"""
import os
import pexpect

from ..log import log, sleep
from ..connection import PexpectConnection, ConnException, ConnCloseException, ConnTimeoutException


#
class Telnet(PexpectConnection):
    """telnet connection"""
    conn_name = "telnet"

    def __init__(self, cname, ip="", port=23, user="", password="",
                 prompt="", timeout=30, force_clear_echo=False,
                 telnet_ip=None, telnet_port=None, **kwargs):
        if telnet_ip:
            ip = telnet_ip
        if telnet_port:
            port = telnet_port
        super(
            Telnet,
            self).__init__(
            cname,
            "telnet",
            "%s %s" %
            (ip,
             port),
            prompt,
            timeout,
            force_clear_echo)
        self.ip = ip
        self.port = port
        self.user = user
        self.password = password
        if len(kwargs) > 0:
            log.debug("Extra arguments for telnet connection: %s" % kwargs)

    def login(self, presend_user=False):
        """Login with telnet, presend_user means if send username whenever connected, for StoneOS console login"""
        retry = 1
        # switch to indicate if username has been sent, to avoid noise in
        # telnet welcome banners
        user_sent = False
        if presend_user:
            # wait for telnet prompt, timeout is set to a short one because its
            # irrelavent to the target connection
            i = self._exp.expect(
                ["Escape character is '\^\]'\.", pexpect.EOF, pexpect.TIMEOUT], timeout=3)
            if i == 1:
                raise ConnCloseException("connection closed unexpectly.")
            # continue on match and timeout
            self._exp.sendline(self.user)
            user_sent = True

        while True:
            i = self._exp.expect(["[Ll]ogin:",
                                  "[Pp]assword:",
                                  "Login incorrect",
                                  self.prompt,
                                  pexpect.EOF,
                                  pexpect.TIMEOUT],
                                 timeout=self.timeout)
            if i == 0:
                if retry < 0:
                    raise ConnException("login failed.")
                elif not user_sent:
                    self._exp.sendline(self.user)
                    user_sent = True
                    retry = retry - 1
                else:
                    raise ConnException("Incorrect user name.")
            elif i == 1:
                self._exp.sendline(self.password)
            elif i == 2:
                user_sent = False
            elif i == 3:
                self.last_prompt = self._exp.after
                break
            elif i == 4:
                raise ConnCloseException("connection closed unexpectly.")
            elif i == 5:
                if retry <= 0:
                    raise ConnTimeoutException("login timeout.")
                elif not user_sent:
                    self._exp.sendline(self.user)
                    user_sent = True
                retry = retry - 1

    def open(self, autologin=True):
        if self._opened:
            return
        super(Telnet, self).open()
        if autologin:
            try:
                self.login()
            except Exception as e:
                log.error("Error login to %s: %s" % (self.name, e))


#
class SSH(PexpectConnection):
    """SSH connection"""
    conn_name = "ssh"

    def __init__(self, cname, ip="", port=22,
                 user="", password="", prompt="",
                 timeout=30, force_clear_echo=False,
                 ssh_ip=None, ssh_port=None, **kwargs):
        if ssh_ip:
            ip = ssh_ip
        if ssh_port:
            port = ssh_port
        super(
            SSH,
            self).__init__(
            cname,
            "ssh",
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o HashKnownHosts=no -p %s %s@%s" %
            (port,
             user,
             ip),
            prompt,
            timeout,
            force_clear_echo)
        self.ip = ip
        self.user = user
        self.password = password
        if len(kwargs) > 0:
            log.debug("Extra arguments for ssh connection: %s" % kwargs)

    def login(self):
        retry = 3
        while True:
            i = self._exp.expect(["\(yes\/no\)\?",
                                  "[Pp]assword:",
                                  self.prompt,
                                  pexpect.EOF,
                                  pexpect.TIMEOUT],
                                 timeout=3 * self.timeout)
            if i == 0:
                self._exp.sendline("yes")
            elif i == 1:
                if retry <= 0:
                    raise ConnException("login failed.")
                self._exp.sendline(self.password)
                retry = retry - 1
            elif i == 2:
                break
            elif i == 3:
                raise ConnCloseException("connection closed unexpectly.")
            elif i == 4:
                raise ConnTimeoutException("login timeout.")

    def open(self):
        if self._opened:
            # log.debug("Connection already opened: %s %s", self.prog, self.params)
            return
        super(SSH, self).open()
        try:
            self.login()
        except Exception as e:
            log.warn("Error login to %s: %s" % (self.name, e))
            self.close()


# TODO: refactor console server class
class Console(Telnet):
    """Cisco Console connection, a subclass of telnet"""
    conn_name = "console"
    uniq = True

    def __init__(
            self,
            cname,
            con_ip="",
            con_port="",
            user="",
            password="",
            prompt="",
            timeout=30,
            force_clear_echo=False,
            **kwargs):
        super(
            Console,
            self).__init__(
            cname,
            con_ip,
            con_port,
            user=user,
            password=password,
            prompt=prompt,
            timeout=timeout,
            force_clear_echo=force_clear_echo)
        self.con_ip = con_ip
        self.con_port = con_port
        self.user = user
        self.password = password
        if len(kwargs) > 0:
            log.debug("Extra arguments for console connection: %s" % kwargs)

    def clearLine(self):
        tscon = Telnet(self.name, ip=self.con_ip, user="",
                       password="cisco", prompt='.+[>#]')
        tscon.open()
        tscon.cmd("cisco")
        tscon.cmd("enable", mid_prompts={"Password:": "cisco\n"})
        tscon.cmd("clear line %d" % (int(self.con_port) %
                                     2000), mid_prompts={"\[confirm\]": "\n"})
        tscon.close()
        sleep(3)

    def open(self, autologin=True):
        if self._opened:
            #log.debug("Connection already opened: %s %s", self.prog, self.params)
            return
        if str(self.con_port).startswith("20"):
            log.debug("Cisco terminal server, clear line firstly")
            self.clearLine()
        super(Console, self).open(False)
        if autologin:
            try:
                self.login(presend_user=True)
            except Exception as e:
                log.warn("Error login to %s: %s" % (self.name, e))
                self.close()


# Local connection, still use pexpect for simplicity
class Local(PexpectConnection):
    """local bash connection"""
    conn_name = "local"
    uniq = False
    # do not set TERM to dumb because some program will crash on this
    _env = None

    def __init__(
            self,
            cname,
            command='/bin/bash',
            prompt=r'\S+\@\S+\:.+# ',
            timeout=10,
            force_clear_echo=False,
            **kwargs):
        """reduce all unnecessary parameters for local connection"""
        super(Local, self).__init__(cname, command,
                                    "", prompt, timeout, force_clear_echo)
        if len(kwargs) > 0:
            log.debug("Extra arguments for local connection: %s" % kwargs)

    def open(self, autologin=True):
        """Consume first prompt"""
        if self._opened:
            # log.debug("Connection already opened: %s %s", self.prog, self.params)
            return
        # set terminal
        os.environ['COLUMNS'] = "256"
        super(Local, self).open()
        self._exp.expect([self.prompt])
        self.last_prompt = self._exp.after
