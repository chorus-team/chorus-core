# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Connection class. pexpect based
"""
from .config import Config
from .log import log, getLogPrefix, sleep
import os
import sys
import time
import pexpect
import re
import traceback
import requests
import json
# pylint: disable=no-member
requests.packages.urllib3.disable_warnings()

PY3 = (sys.version_info[0] >= 3)

# used to filter out all color characters in output
COLOR_FILTER = re.compile(r"\x1B\[(\d{1,2}(;\d{1,2})*)?[mA-Z]")
# controls whether to use dummy connection for test run
dummy_conn = False


class Connection(object):
    """Base interface for connections
    """
    # conn name is the symbolic name of the connection, used for topo and
    # device init
    conn_name = "base"
    uniq = False

    def __init__(self):
        super(Connection, self).__init__()
        self._opened = False

    def open(self):
        self._opened = True

    def close(self):
        self._opened = False

    def reopen(self, delay=3):
        self.close()
        sleep(delay)
        self.open()

    def cmd(self, cmd):
        pass

    def isOpen(self):
        return self._opened


class DummyConnection(Connection):
    """The empty connection, works as a stub for test running of scripts
    """
    # conn name is the symbolic name of the connection, used for topo and
    # device init
    conn_name = "dummy"

    def __init__(self, cname, **kwargs):
        super(DummyConnection, self).__init__()
        self.name = cname
        self.last_prompt = "dummy"

    def open(self):
        log.debug("Dummy connection %s opened." % self.name)
        self._opened = True

    def close(self, force=False):
        log.debug("Dummy connection %s closed." % self.name)
        self._opened = False

    def reopen(self, delay=0):
        log.debug("Dummy connection %s reopened." % self.name)
        super(DummyConnection, self).reopen(delay)

    def cmd(self, cmd, *args, **kwargs):
        log.debug("Command for dummy connection %s received:" % self.name)
        log.debug("  %s" % cmd)
        log.debug("  %s" % ",".join(args))
        log.debug("  %s" % kwargs)
        # echo the command
        return cmd

    def isOpen(self):
        return self._opened


class PexpectConnection(Connection):
    """Pexpect based connet class, used to control devices over the network tools or other interactive processes
    """
    # conn name is the symbolic name of the connection, used for topo and
    # device init
    conn_name = "base"
    # reusable connection
    uniq = False
    # env params when spawning connection
    _env = {"TERM": "dumb"}
    # Need to specify **kwargs to prevent error happening

    def __init__(
            self,
            cname,
            prog,
            params,
            prompt,
            timeout=10,
            force_clear_echo=False):
        """
        :param cname: name of the connection
        :param prog: connection program, can be a program name or a file descriptor
        :param params: parameters of the program
        :param prompt: default prompt of the connection
        :param timeout: default timeout of the connection
        :param force_clear_echo: For some none-standard os, like stoneos, echo mode cannot be turned off. Set this to
            True to force clear echoed command.
        """
        super(PexpectConnection, self).__init__()
        self.name = cname
        self.prog = prog
        self.params = params
        self.prompt = prompt
        self.timeout = timeout
        self.force_clear_echo = force_clear_echo
        self._exp = None
        self._opened = False
        self.uniq = self.__class__.uniq
        # use for store the prompt left after the command output
        self.last_prompt = ""

    def open(self):
        """Open the connection"""
        if isinstance(self.prog, int):
            log.debug("Opening connection for %s: %s",
                      self.name, self.conn_name + str(self.prog))
            from pexpect.fdpexpect import fdspawn
            if PY3:
                self._exp = fdspawn(self.prog, encoding='utf-8')
            else:
                self._exp = fdspawn(self.prog)

            # to be consistent with `spawn`, implement `sendcontrol` by hand
            def sendcontrol(c):
                chars = r"abcdefghijklmnopqrstuvwxyz[\]^_"
                if len(c) == 1 and c in chars:
                    self._exp.send(chr(chars.index(c) + 1))
                else:
                    log.error("Not a control char %s, ignoring" % c)

            self._exp.sendcontrol = sendcontrol
        else:
            os.environ["TERM"] = "dumb"
            log.debug("Opening connection for %s: %s %s",
                      self.name, self.prog, self.params)
            if PY3:
                self._exp = pexpect.spawn(
                    self.prog + " " + self.params,
                    env=self._env,
                    echo=False,
                    use_poll=True,
                    encoding='utf-8')
            else:
                self._exp = pexpect.spawn(
                    self.prog + " " + self.params,
                    env=self._env,
                    echo=False,
                    use_poll=True)
        lp = getLogPrefix()
        if lp != "":
            fout = open(lp + self.name + '.exp', 'a+', encoding='utf-8')
            self._exp.logfile = fout
        self._opened = True

    def close(self, force=False):
        """Close the connection"""
        log.debug("Closing connection: %s %s", self.prog, self.params)
        if (self._exp is not None) and self._opened:
            try:
                self._exp.close(force)
            except BaseException:
                log.warning("Closing connection error with %s", self.name)
        self._opened = False

    def _clear_echo(self, cmd):
        """For some none-standard os, like stoneos, we cannot turn off echo mode. This will help clean the echo string."""
        # handle linewraps in case of long commands
        # take '020d' as a special mark for width overflow
        i = self._exp.expect([re.escape(cmd), " \r", "[\r\n]+"])
        out = str(self._exp.before)
        while i == 1 and \
                (cmd not in out) and \
                (out in cmd):
            i = self._exp.expect([" \r", "[\r\n]+"]) + 1
            out += str(self._exp.before)

    def _cmd(
            self,
            cmd,
            prompt=None,
            mid_prompts={},
            mid_ignore=False,
            timeout=None,
            control=False,
            nonewline=False,
            failcontinue=False):
        """
        Send a command and return the output
        mid_prompts is a dict which contains the prompts before return and the action need to takes
        i.e. conn.cmd("show session", mid_prompts={"--more--": " ", "Y/n": "Y"})
        mid_ignore indicates whether clear the mid prompt in the output

        :param str cmd: the command string
        :param str prompt: prompt regex, use the connection default if not specified
        :param dict mid_prompts: match middle prompts, like 'yes/no', and send response
        :param str mid_ignore: record mid prompt and response to log file, False by default
        :param int timeout: command line timeout
        :param bool control: send control character instead of command string, False by default
        :param bool nonewline: do not send line wrap, False by default
        :param bool failcontinue: ignore command line failures, i.e. timeout, False by default
        :return: the output of the command
        """
        if prompt is None:
            prompt = self.prompt
        if timeout is None:
            timeout = self.timeout
        # clear expect buffer to avoid confusion
        if len(self._exp.buffer) > 0:
            if self._exp.buffer.strip() != "":
                log.debug("Expect buffer not empty, clear it:")
                log.debug(self._exp.buffer)
            while True:
                i = self._exp.expect(
                    ['.', pexpect.EOF, pexpect.TIMEOUT], timeout=0.2)
                if i != 0:
                    break
        o = ""
        p = self.last_prompt
        l = 0
        # Total output characters, used to tell if there are any extra chars
        # before timeout or exception
        to = 0
        start = time.time()
        if control:
            l = self._exp.sendcontrol(cmd)
            log.info(cmd)
        else:
            cmd = cmd.strip()
            if nonewline:
                l = self._exp.send(cmd)
            else:
                l = self._exp.sendline(cmd)
            log.info(str(p) + cmd)
            if self.force_clear_echo:
                self._clear_echo(cmd)
        if l <= len(cmd):
            log.warning("Command is partially sent: %s", cmd)

        mid_size = len(mid_prompts.keys())
        # Do not match line wraps, in case mid_prompt may container multi-line
        # match
        if mid_size != 0:
            exp_prompts = list(mid_prompts.keys()) + \
                [prompt, pexpect.EOF, pexpect.TIMEOUT]
        else:
            exp_prompts = list(mid_prompts.keys()) + \
                [prompt, pexpect.EOF, pexpect.TIMEOUT, "[\r\n]+"]

        while True:
            i = self._exp.expect(exp_prompts, timeout=int(timeout))
            if i < mid_size:
                to = to + len(self._exp.before) + len(self._exp.after)
                k = list(mid_prompts.keys())[i]
                o = o + str(self._exp.before)
                if not mid_ignore:
                    o = o + str(self._exp.after)
                # check if place indicators specified
                allpos = re.findall(r'(?<=\$)\d+', mid_prompts[k])
                sendstr = mid_prompts[k]
                if len(allpos) > 0:
                    m = re.search(k, self._exp.after)
                    for pos in allpos:
                        # replace $ indicator with reg submatches
                        if int(pos) > m.groups():
                            log.error(
                                'Location indicator exceeds the sub matchs: %s: %s', mid_prompts[k], k)
                        else:
                            sendstr = sendstr.replace(
                                '$' + pos, m.group(int(pos)))
                log.debug(str(self._exp.before) + str(self._exp.after))
                self._exp.send(sendstr)
            elif i == mid_size:
                to = to + len(self._exp.before) + len(self._exp.after)
                o = o + str(self._exp.before)
                self.last_prompt = self._exp.after
                if self._exp.before:
                    log.debug(str(self._exp.before))
                break
            elif i == mid_size + 1:
                if len(self._exp.before) > to:
                    log.debug(str(self._exp.before)[to:])
                if failcontinue:
                    log.debug("failcontinue enabled, continue...")
                    break
                else:
                    raise ConnCloseException("connection closed unexpectly.")
            elif i == mid_size + 2:
                # one time timeout, output the extra chars
                if len(self._exp.before) > to:
                    o = o + str(self._exp.before)[to:]
                    log.debug(str(self._exp.before)[to:])
                    to = len(self._exp.before)
            elif i == mid_size + 3:
                to = to + len(self._exp.before) + len(self._exp.after)
                # output each line
                o = o + str(self._exp.before) + str(self._exp.after)
                if self._exp.before:
                    log.debug(str(self._exp.before))

            # overall timeout
            if time.time() - start >= timeout:
                if failcontinue:
                    log.debug("failcontinue enabled, continue...")
                    break
                else:
                    raise ConnTimeoutException("command timeout.")

        # filter the output
        #log.info(str(p) + o)
        out = COLOR_FILTER.sub("", o.strip("\r\n"))
        # filter all backspace and empty characters
        fout = ""
        for c in out:
            if c == "\x08":
                fout = fout[:-1]
            elif c == "\x00":
                continue
            else:
                fout = fout + c
        # reduce output
        if len(fout) > 100:
            log.info(fout[0:100] + "...")
        else:
            log.info(fout)
        if failcontinue:
            log.info("failcontinue enabled. The output is not to be trusted. ")
        return fout

    def cmd(
            self,
            cmd,
            prompt=None,
            mid_prompts={},
            mid_ignore=False,
            timeout=None,
            control=False,
            nonewline=False,
            failcontinue=False,
            clean_timeout=True):
        """A cmd method with retries"""
        out = ""
        # Do not try to reopen connection here, leave it to the upper layer,
        # because there may be initial command to be issued
        try:
            for c in cmd.strip().splitlines():
                out += self._cmd(c,
                                 prompt,
                                 mid_prompts,
                                 mid_ignore,
                                 timeout,
                                 control=control,
                                 nonewline=nonewline,
                                 failcontinue=failcontinue)
            return out
        except ConnTimeoutException:
            log.error("Send command error due to timeout: %s", cmd)
            if clean_timeout:
                log.debug("Clean current process on timeout")
                self._cmd('c', control=True)
        except ConnCloseException:
            log.debug("Send command error due to connection closed: %s", cmd)
        except (KeyboardInterrupt, SystemExit) as e:
            log.error("User interrupted.")
            log.debug("Cascading ^C to device")
            self._cmd('c', control=True)
            raise e
        except BaseException:
            log.error("Send command error due to error:\n %s",
                      traceback.format_exc())
        # leave it to the caller
        raise ConnException("Error sending command %s." % cmd)

    def isOpen(self):
        return self._opened


class RestConnection(Connection):
    """Rest base connect class, used to control/manage devices via restful API"""
    conn_name = "rest"
    uniq = False
    default_user_agent = "chorus"

    def __init__(
            self,
            cname,
            use_session=True,
            session=None,
            ssl_verify=False):
        """
        :param cname: specify the connection name
        :param use_session: use session to do the request
        :param session: a request session class
        :param ssl_verify: ssl verify for https connection
        """
        super(RestConnection, self).__init__()
        self.name = cname
        self.ssl_verify = ssl_verify
        self._opened = False
        self.uniq = self.__class__.uniq
        self.use_session = use_session
        self.token = ""
        self._session = session
        self.headers = {}
        self.cookies = {}
        self._set_user_agent()

    def auth(self):
        pass

    def connect(self):
        pass

    @property
    def session(self):
        if not self._session and self.use_session:
            self._session = self.get_session()
        return self._session

    @staticmethod
    def get_session():
        return requests.session()

    def set_auth_token(self):
        pass

    def set_headers(self, header, reset=False):
        if reset:
            self.headers = {}
        self.headers.update(header)
        if self.use_session:
            self.session.headers = self.headers

    def set_cookies(self, cookies, reset=False):
        if reset:
            self.cookies = {}
        self.cookies.update(cookies)

    def set_host(self, host=""):
        if host:
            self.set_headers({"Host": host})

    def _set_user_agent(self):
        self.set_headers({'User-Agent': self.default_user_agent})

    def set_content_type(self, content_type):
        self.set_headers({'Content-type': content_type})

    def request(self, method, url, timeout=5, **args):
        """
        :param method: request method
        :param url: request url
        :param timeout: timeout for send request
        :param args: other args like json, params, body, etc.
        :return: response for request or Fail
        """
        log.debug("Request parameters: {method: %s, url: %s, args: %s}" % (
            method, url, str(args)))
        if "json" in args:
            if args["json"]:
                self.set_content_type("application/json")
        if "params" in args:
            # do not change string value due to extra quotation marks
            for p in args["params"]:
                if not isinstance(args["params"][p], str):
                    args["params"][p] = json.dumps(args["params"][p], separators=(',', ':'))
        try:
            if self.use_session:
                self.session.verify = self.ssl_verify
                resp = getattr(self.session, method.lower())(
                    url, timeout=timeout, cookies=self.cookies, **args)
            else:
                resp = getattr(
                    requests,
                    method.lower())(
                    url,
                    headers=self.headers,
                    cookies=self.cookies,
                    verify=self.ssl_verify,
                    timeout=timeout,
                    **args)

            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError:
            log.exception(
                "Request Error due to response status code: " + str(resp.status_code))
            return False
        except requests.exceptions.Timeout:
            log.exception("Request Error due to timeout")
            return False
        except BaseException:
            log.error("Request Error due to:\n %s", traceback.format_exc())
            raise ConnException("Send Request error")

    def open(self):
        self.connect()
        self._opened = True

    def close(self, force=False):
        if self.use_session and self.session:
            self.session.close()
        self._opened = False

    def isOpen(self):
        return self._opened


############################
#
class ConnException(Exception):
    """Exception handling class for connection"""

    def __init__(self, value):
        super(ConnException, self).__init__()
        self.value = "Connection Error due to: " + value
        log.exception("Connection Error happens: %s!!", value)

    def __str__(self):
        return repr(self.value)


#
class ConnCloseException(ConnException):
    """Exception handling class for connection"""

    def __init__(self, value):
        super(ConnCloseException, self).__init__(value)

    def __str__(self):
        return repr(self.value)


#
class ConnTimeoutException(ConnException):
    """Exception handling class for connection"""

    def __init__(self, value):
        super(ConnTimeoutException, self).__init__(value)

    def __str__(self):
        return repr(self.value)


##############################################
# facilities to connect a specific connection
def newConn(cname, ctype, **kwargs):
    """Get a connection with the specific type"""
    if dummy_conn:
        log.info("Using dummy connection for %s" % cname)
        return DummyConnection(cname, **kwargs)
    try:
        conn = Config().get_plugin("connection", ctype)
    except Exception as e:
        raise ConnException("Connection init failed: %s" % e)
    log.debug("New connection is being establised: %s %s with args %s",
              cname, ctype, kwargs)
    return conn(cname, **kwargs)


def uniqConn(ctype):
    """Check if a connection uniq"""
    conn = Config().get_plugin("connection", ctype)
    return conn.uniq
