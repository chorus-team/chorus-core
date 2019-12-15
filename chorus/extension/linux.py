# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Extend Linux with some service capabilities
"""
import re
import os
from ..config import extend
from ..log import sleep
from ..device import Device


@extend("linux")
class LinuxClient(object):
    """Linux client capabilities"""
    #############################
    # ping

    def ping(self, to_host="", count=2, pass_count=2, size=56, timeout=30):
        """Ping the target"""
        ping_cmd = "ping " + "-c %s" % count + " " + "-s %s" % size + " " + to_host
        self.log.info("Executing " + ping_cmd)
        ping_result = self.cmd(ping_cmd, timeout=timeout)
        if re.search(r'unknown host', ping_result):
            self.log.error("Cannot lookup the host!")
            return False
        elif re.search(r'(\d+) packets transmitted, (\d+)[\s\S]+received, \+(\d+) errors, (\d+)% packet loss', ping_result):
            match = re.search(
                r'(\d+) packets transmitted, (\d+)[\s\S]+received, \+(\d+) errors, (\d+)% packet loss',
                ping_result)
            self.log.info("Match info is: \"" + match.group() + "\"")
            if int(match.group(2)) == 0:
                self.log.error("error: All ping packets are dropped!")
                return False
            elif int(match.group(2)) < count:
                self.log.info("Some ping packets are dropped during ping!")
                if int(match.group(2)) < pass_count:
                    self.log.error("Error: Dropped ping packets are too much!")
                    return False
                else:
                    return True
        elif re.search(r'(\d+) packets transmitted, (\d+)[\s\S]+received, (\d+)% packet loss', ping_result):
            match = re.search(
                r'(\d+) packets transmitted, (\d+)[\s\S]+received, (\d+)% packet loss',
                ping_result)
            if int(
                    match.group(1)) == count and int(
                    match.group(2)) == int(
                    match.group(1)):
                self.log.info("All ping packets are passed!")
                return True
            elif int(match.group(2)) < count:
                self.log.info("Some ping packets are dropped during ping!")
                if int(match.group(2)) < pass_count:
                    self.log.error("Error: Dropped ping packets are too much!")
                    return False
                else:
                    return True
            elif re.search(r'(\d+) packets transmitted, (\d+)[\s\S]+received, \+(\d+) duplicates, (\d+)% packet loss',
                           ping_result):
                match = re.search(
                    r'(\d+) packets transmitted, (\d+)[\s\S]+received, \+(\d+) duplicates, (\d+)% packet loss',
                    ping_result)
                if int(
                        match.group(1)) == count and int(
                        match.group(2)) == int(
                        match.group(1)):
                    self.log.info("All ping packets are passed!")
                    return True
                elif int(match.group(2)) < count:
                    self.log.info("Some ping packets are dropped during ping!")
                    if int(match.group(2)) < pass_count:
                        self.log.error(
                            "Error: Dropped ping packets are too much!")
                        return False
                    else:
                        return True
        else:
            self.log.info("Check ping result failed. pls check")
            return False

    #############################
    # ftp
    def ftp(
            self,
            to_host="",
            user=Device.DEFAULT_USER,
            password=Device.DEFAULT_PASSWORD,
            cmd="get",
            ftp_file="ftpfile",
            local_file="",
            cd="",
            lcd="",
            pasv="",
            timeout=600):
        """transfer file with ftp. The client side"""
        if cmd == "get":
            if ftp_file != "":
                if lcd != "" and cd != "" and local_file != "":
                    cmd = cmd + " " + cd + "/" + ftp_file + " " + lcd + "/" + local_file
                elif lcd == "" and cd != "" and local_file != "":
                    cmd = cmd + " " + cd + "/" + " " + local_file
                elif lcd != "" and cd == "" and local_file != "":
                    cmd = cmd + " " + ftp_file + " "
                elif lcd != "" and cd != "" and local_file == "":
                    cmd = cmd + " " + cd + "/" + ftp_file + " " + lcd + "/" + ftp_file
                elif lcd != "" and cd == "" and local_file == "":
                    cmd = cmd + " " + ftp_file + "./" + ftp_file
                elif lcd == "" and cd == "" and local_file != "":
                    cmd = cmd + " " + ftp_file + " " + local_file
                elif lcd == "" and cd != "" and local_file == "":
                    cmd = cmd + " " + cd + "/" + ftp_file
                elif lcd == "" and cd == "" and local_file == "":
                    cmd = cmd + " " + ftp_file
        elif cmd == "put":
            if local_file != "":
                if lcd != "" and cd != "" and ftp_file != "":
                    cmd = cmd + " " + lcd + "/" + local_file + " " + cd + "/" + ftp_file
                elif lcd == "" and cd != "" and ftp_file != "":
                    cmd = cmd + " " + local_file + " " + cd + "/" + ftp_file
                elif lcd != "" and cd == "" and ftp_file != "":
                    cmd = cmd + " " + lcd + "/" + local_file + " " + ftp_file
                elif lcd != "" and cd != "" and ftp_file == "":
                    cmd = cmd + " " + lcd + "/" + local_file + " " + cd + "/" + local_file
                elif lcd != "" and cd == "" and ftp_file == "":
                    cmd = cmd + " " + lcd + "/" + local_file
                elif lcd == "" and cd == "" and ftp_file != "":
                    cmd = cmd + " " + local_file + " " + ftp_file
                elif lcd == "" and cd != "" and ftp_file == "":
                    cmd = cmd + " " + local_file + " " + cd + "/" + local_file
                elif lcd == "" and cd == "" and ftp_file == "":
                    cmd = cmd + " " + local_file + " " + local_file
        if pasv is None:
            pasv = "1"
        if timeout is None:
            timeout = "2400"

        self.log.info("ftp from client to server")
        ftp_prompt = "ftp>"
        rate = 0
        ftp_login_prompt = r"Name \(" + to_host + ":" + self.user + r"\):"
        ftp_login = self.cmd(
            "/usr/bin/ftp " + to_host,
            prompt=ftp_prompt,
            mid_prompts={
                ftp_login_prompt: user + "\n",
                "Password": password + "\n"})
        if re.search(r'No route to host', ftp_login):
            self.log.error("Cannot to connect ftp server!")
            self.cmd("bye")
            return False
        elif re.search(r'Connection timed out', ftp_login):
            self.log.error("Connection timed out!")
            self.cmd("bye")
            return False
        else:
            self.cmd("binary", prompt=ftp_prompt)
            if pasv == "1":
                self.cmd("passive", prompt=ftp_prompt)
            self.log.info("Now, begin to transmit the ftp file")
            myftp = self.cmd(cmd, prompt=ftp_prompt, timeout=timeout)
            if re.search(r'Failed to open file', myftp):
                self.log.error("Error: no ftp file exists!")
                self.cmd("bye")
                return False
            elif re.search(r'No such file or directory', myftp):
                self.log.error("Error: no ftp folder exists!")
                self.cmd("bye")
                return False
            elif re.search(r'Transfer complete', myftp) and re.search(r'received', myftp):
                pattern = re.compile(r"\((.*B/s)")
                rate = re.search(pattern, myftp).group(1)
                self.log.info("Pass: FTP is passed.")
                self.cmd("bye")
                return (True, rate)
            elif re.search(r'Connection reset by peer', myftp) and re.search(r'Transfer complete', myftp):
                reason = "Connection reset by peer"
                self.log.info("Pass: FTP connection is reset by peer.")
                self.cmd("bye")
                return (False, reason)
            elif re.search(r'Failed to establish connection', myftp):
                self.log.error("Failed to establish connection!")
                self.cmd("bye")
                return False
            elif re.search(r'Not connected', myftp):
                self.log.error("Not conneted!")
                self.cmd("bye")
                return False
            elif not myftp:
                self.cmd("c", control=True)
                return False

    #############################
    # tftp
    def tftp(self, to_host="", cmd="", tftp_file="", timeout=600):
        """transfer file with tftp"""
        ping_cmd = "ping " + "-nc 3 " + to_host
        self.log.info("Connection check needed before tftp!")
        ping_result = self.cmd(ping_cmd, timeout=30)
        if re.search(
            r'(\d+) packets transmitted, (\d+) received, \+(\d+) errors, (\d+)% packet loss',
                ping_result):
            match = re.search(
                r'(\d+) packets transmitted, (\d+) received, \+(\d+) errors, (\d+)% packet loss',
                ping_result)
            if int(match.group(2)) == 0:
                self.log.error(
                    "error: All ping packets are dropped, cannot connect to " + to_host)
                return False
            else:
                self.log.warn(
                    "warn: Some ping packets are dropped, the connection is not good for tftp!")
        elif re.search(r'(\d+) packets transmitted, (\d+) received, (\d+)% packet loss', ping_result):
            self.log.info(
                "pass: All ping packets are transmitted, the connection is very good!")

        tftp_prompt = "tftp>"
        print("to_host\n\n")

        tftp_login_cmd = "tftp  " + to_host
        if cmd == "":
            cmd = "get"
        tftp_cmd = cmd + " " + tftp_file
        self.log.info("Executing tftp " + to_host)
        tftp_login_result = self.cmd(tftp_login_cmd, prompt=tftp_prompt)
        if re.search(r'unknown host', tftp_login_result):
            self.log.error("Fail to nslookup the device!")
            return False
        else:
            tftp_result = self.cmd(
                tftp_cmd, prompt=tftp_prompt, timeout=timeout)

            if re.search(r'Error code 1: File not found', tftp_result):
                self.log.error("tftp file not found!")
                self.cmd("quit")
                return False
            elif re.search(r'Invalid command', tftp_result):
                self.log.error("wrong tftp cmd!")
                self.cmd("quit")
                return False
            elif re.search(r'Permission denied', tftp_result):
                self.log.error("no permission to put or get!")
                self.cmd("quit")
                return False
            elif re.search(r'No such file or directory', tftp_result):
                self.log.info("No such file or directory")
                self.cmd("quit")
                return False
            elif re.search(r'Sent', tftp_result):
                p1 = re.compile("Sent (.*) bytes")
                filesize = re.search(p1, tftp_result).group(1)
                filesize = float(filesize)
                p2 = re.compile("in (.*) seconds")
                time = re.search(p2, tftp_result).group(1)
                time = float(time)
                rate = (filesize / 1024) / time
                rate = round(rate, 2)
                self.log.info("Good to sent tftp file!")
                self.cmd("quit")
                return (True, rate)
            elif re.search(r'Received', tftp_result):
                p1 = re.compile("Received (.*) bytes")
                filesize = re.search(p1, tftp_result).group(1)
                filesize = float(filesize)
                print(filesize)
                p2 = re.compile("in (.*) seconds")
                time = re.search(p2, tftp_result).group(1)
                time = float(time)
                rate = (filesize / 1024) / time
                rate = round(rate, 2)
                self.log.info("Good to receive tftp file!")
                self.cmd("quit")
                return (True, rate)
            else:
                self.log.info("Good to receive tftp file!")
                self.cmd("quit")
                return True

    #############################
    # http
    def sendhttp(self, to_host="", get_file="", limit_rate="", timeout=60):
        """wget http target"""
        self.log.info("Now, send http stream!")
        if limit_rate == "":
            http_cmd = "wget " + "http://" + to_host + "/" + get_file
        else:
            http_cmd = "wget " + "http://" + to_host + "/" + \
                get_file + " --limit-rate=%s" % limit_rate
        http_result = self.cmd(http_cmd, prompt=self.prompt, timeout=timeout)
        if re.search(r'failed: No route to host', http_result):
            self.log.error("Cannot to connect www server!")
            return False
        elif re.search(r'ERROR 404: Not Found', http_result):
            self.log.error("error: File is not found!")
            return False
        elif re.search(r'200 OK', http_result) and re.search(r'saved', http_result):
            self.log.info("Pass: http transmits ok!")
            return True

    #############################
    # telnet
    def telnet(
            self,
            to_host="",
            user=Device.DEFAULT_ROOT,
            password=Device.DEFAULT_PASSWORD,
            cmd="",
            timeout=120):
        """telnet to target"""
        self.log.info("Now, to telnet " + to_host)
        telnet_prompt = r'\S+\@\S+\:.+#'
        telnet_cmd = "telnet " + to_host
        telnet_result = self.cmd(
            telnet_cmd,
            prompt=telnet_prompt,
            mid_prompts={
                "ubuntu login": user +
                "\n",
                "Password": password +
                "\n"},
            timeout=600)
        # self.log.info(telnet_result)
        if re.search(r'Unable to connect to remote host', telnet_result):
            self.log.error("Cannot connect to remote host!")
            return False
        elif re.search(r'Login incorrect', telnet_result):
            self.log.error("Error user and password!")
            return False
        elif re.search(r'Connection closed by foreign host', telnet_result):
            self.log.error("Remote host drops the telnet!")
            return False
        for i in range(0, len(cmd)):
            print("%s" % cmd[i])
            self.cmd(cmd[i], prompt=telnet_prompt, timeout=60)
            sleep(2)

        self.log.info("To exit the remote host " + to_host)
        endinfo = self.cmd("exit", prompt=telnet_prompt, timeout=120)
        if re.search(r'logout', endinfo):
            self.log.info("Success to logout remote host " + to_host)
            return True

    #############################
    # ssh
    def remoteCmd(
            self,
            to_host,
            cmd,
            usr=Device.DEFAULT_ROOT,
            password=Device.DEFAULT_PASSWORD,
            timeout=600):
        """issue ssh command"""
        rslt = self.cmd(
            "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o HashKnownHosts=no -t %s@%s '%s'" %
            (usr, to_host, cmd), mid_prompts={
                "assword:": password + "\n"}, timeout=timeout)
        if re.search(r'Connection timed out', rslt):
            self.log.error('Connection timed out')
            return False
        elif re.search(r'Connection to %s closed' % to_host, rslt):
            self.log.info("Execute remote command successfully")
            return True


@extend("linux")
class LinuxServer(object):
    """The server methods of linux"""
    #############################
    # ftp

    def ftpLimitRate(self, rate=100, timeout=60):
        """Adjust the transfer rate of ftp server
        default rate = 100KB/S"""
        rslt = self.cmd("ls /etc")
        if re.search(r'vsftpd\.conf', rslt):
            ftp_config_file = "/etc/vsftpd.conf"
        elif re.search(r'vsftpd\.conf', self.cmd("ls /etc/vsftpd/")):
            ftp_config_file = "/etc/vsftpd/vsftpd.conf"
        else:
            self.log.error("Fail to find vsftpd config file")
            return False
        self.log.info("limite rate")
        rate1 = int(rate * 1024)

        del_cmd = "sed -i '/local_max_rate/d' %s" % ftp_config_file
        set_cmd = "echo 'local_max_rate=%d' >> %s" % (rate1, ftp_config_file)

        if self.issue([del_cmd, set_cmd], timeout=timeout):
            if self.testCmd(
                "grep -- 'local_max_rate=%d' %s" %
                    (rate1, ftp_config_file), r"local_max_rate"):
                self.cmd("service vsftpd restart", timeout=timeout)
                self.log.info("Success to limit rate to %d KB/s" % rate)
                return True
        self.log.error("Fail to change ftp config file")
        return False
