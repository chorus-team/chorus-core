# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

import re

from chorus.device import Device


class Linux(Device):
    """The basic Linux device"""
    # bash as the default shell. English is the default language.
    # Simple prompt at beginning, force turn off echo mode, and set PS1 on
    # login
    prompt = r'\[?[^\r\n]+(#|\]) '
    init_cmds = {
        "cmds": [
            '/bin/bash',
            'stty -echo',
            'LANG=en_US.UTF-8',
            'LANGUAGE=en_US.UTF-8',
            'PS1="chorus_auto# "'],
        "prompt_after": "chorus_auto# "}
    supported_con = ["ssh", "telnet", "local"]

    def __init__(
            self,
            ip="",
            name="",
            model="",
            user=Device.DEFAULT_ROOT,
            password=Device.DEFAULT_PASSWORD,
            con_method="ssh",
            **usrkwargs):
        super(Linux, self).__init__(name=name, **usrkwargs)
        self.setDefaultConnMethod(con_method)
        self.ip = ip
        self.model = model
        self.user = user
        self.password = password

    def issue(self, cmdlist, timeout=60):
        """Issue multi command and do common error check

        :return: True is all command succeed, or False if common error happens
        """
        reg_commonerror = r"command not found|No such file|Permission denied"
        for cmd in cmdlist:
            if self.testCmd(cmd, reg_commonerror, timeout=timeout):
                self.log.error("Error happens on sending commands!")
                return False
        return True

    def setIfIP(self, ifname, ipmask):
        """Set the ip address of a interface"""
        self.cmd("ip addr add %s dev %s" % (ipmask, ifname))
        self.cmd("ip link set %s up" % ifname)

    def getIfName(self, macaddress):
        """get the name of a interface by mac address"""
        # first get the if name by idx
        output = self.cmd("ip link show")
        # find only ethN
        ifmacs = re.findall(
            r"\d+: (eth\d+): .+\n\s+link/\w+ ([\d\:a-z]+)", output)
        for (ifname, mac) in ifmacs:
            if mac == macaddress:
                return ifname
        self.log.error("No interface with mac address: %s" % macaddress)
        return None

    def getMac(self, intf=None, timeout=60):
        """Get MAC address"""
        if self._mac != {}:
            if intf:
                return self._mac.get(intf)
            else:
                return self._mac
        rslt = self.cmd(
            'ifconfig -a | grep HWaddr | awk -F " " \'{print $1,$NF}\'',
            timeout=timeout)
        if not rslt:
            self.log.error('Get MAC address of %s failed' % intf)
            return rslt
        rslt = rslt.split('\r\n')
        for s in rslt:
            l = s.split(' ')
            self._mac[l[0]] = l[1]
        if intf:
            return self._mac.get(intf)
        else:
            return self._mac

    def create_file(
            self,
            file_path="",
            file_name="",
            file_size="",
            timeout=120,
            strict=True):
        """Create a file
           strict:True indicates that the file size is accurate,Flase indicates fast generation, and there is an error in file size, such as configure 599M to generate 600M        """
        self.log.info("need create the file: " + file_path + "/" + file_name)
        if not file_size:
            cmd = "touch " + file_path + "/" + file_name
        elif isinstance(file_size, int):
            cmd = "dd if=/dev/zero bs=1M of=" + file_path + \
                "/" + file_name + " count=%d" % file_size
        else:
            pattern = r'(\d*)([kMG])'
            m = re.search(pattern, file_size)
            b = 1
            s = m.group(2)
            c = int(m.group(1))
            if strict:
                cmd = "dd if=/dev/zero bs=%d%s of=" % (
                    b, s) + file_path + "/" + file_name + " count=%d" % c
            else:
                if c >= 99:
                    c = round(float(c) / 10) * 10
                    if c % 1000 == 0:
                        c = c / 1000
                        b = 1000
                    elif c % 100 == 0:
                        c = c / 100
                        b = 100
                    else:
                        c = c / 10
                        b = 10
                cmd = "dd if=/dev/zero bs=%d%s of=" % (
                    b, s) + file_path + "/" + file_name + " count=%d" % c
        return self.issue([cmd], timeout=timeout)

    def createFile(self, filename="", size="", timeout=120):
        self.log.info("Creating the file %s with size %sM" % (filename, size))
        rslt = self.cmd("dd if=/dev/zero bs=1M of=%s count=%s" %
                        (filename, size))
        return rslt

    def getFileSize(self, filename):
        "Get the file size"
        rslt = self.cmd("ls -l %s" % filename)
        if "No such file or directory" in rslt:
            self.log.info("The file %s is NOT exist" % filename)
            return False
        else:
            size = rslt.split()[4]
            return size
