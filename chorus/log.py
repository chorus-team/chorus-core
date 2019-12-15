# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
chorus logging facilities.
"""
import glob
import os.path
import logging
import re
import time
import datetime
import csv
from sys import stdout
from pbr.version import VersionInfo
from math import ceil

from .config import Config, loadClass

LOG_PATH_PREFIX = '.log'


###########################################
# A basic logger
###########################################
class BasicLogger(object):
    """The basic logger returns simple logger objects"""
    BASE_TAG = "chorus"
    LOGGLEVELS = {
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
        "notset": logging.NOTSET,
    }
    #
    _instance = None
    EXTENSION = '.log'

    def __init__(self):
        logging.captureWarnings(True)
        self._loggers = {}
        self.logpath = ""
        self.log_prefix = ""
        self._log_files = {}
        self.formatter = logging.Formatter(
            '[%(asctime)s][%(threadName).8s][%(levelname).4s]<%(name)s>: %(message)s',
            '%b %d %H:%M:%S')
        self._initLogging()

    def _initLogging(self):
        # Standard output handler
        # set logging level only on stdout
        self.sth = logging.StreamHandler()
        loglevel = self.LOGGLEVELS.get(
            Config().get_config("log", "level"), "notset")
        self.sth.setLevel(loglevel)
        self.sth.setFormatter(self.formatter)
        # set root logger, used only for global configuration
        # level and handlers set only on root logger
        self._loggers["root"] = logging.getLogger()
        self._loggers["root"].setLevel(logging.DEBUG)
        self._loggers["root"].addHandler(self.sth)

    def getLogger(self, name):
        """Get logger by name"""
        if not name:
            # return logger["chorus"]
            name = self.BASE_TAG

        if name not in self._loggers:
            self._loggers[name] = logging.getLogger(name)
            # addLogHandlers(name)
        return self._loggers[name]

    def setLogPath(self, path):
        # Make logdir
        path = os.path.join(path, LOG_PATH_PREFIX)
        if not os.path.isdir(path):
            os.mkdir(path)
        self.log_prefix = os.path.join(path, 'chorus_' + Config().get_uuid())
        self.logpath = self.log_prefix + self.EXTENSION
        # file log output handler
        fh = logging.FileHandler(self.logpath)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(self.formatter)
        self._loggers["root"].addHandler(fh)
        self._loggers["root"].addHandler(self.sth)
        # print chorus version on logging init
        self._loggers["root"].debug("chorus version: %s" % VersionInfo(
            'chorus').semantic_version().release_string())

    def addLogFile(self, tag):
        """Add a new log handler"""
        self._loggers["root"].debug("Add log file for {}".format(tag))
        if tag in self._log_files:
            self._loggers["root"].debug(
                "Log file for tag '%s' already exists" % tag)
            return
        logpath = self.getLogFile(tag)
        # file log output handler
        fh = logging.FileHandler(logpath)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(self.formatter)
        self._loggers["root"].addHandler(fh)
        self._log_files[tag] = {
            "file": logpath,
            "handler": fh
        }

    def getLogFile(self, tag):
        """Get a file name by tag"""
        if not os.path.isdir(self.log_prefix):
            os.mkdir(self.log_prefix)
        return os.path.join(self.log_prefix, tag + self.EXTENSION)

    def removeLogFile(self, tag):
        """Remove a log handler"""
        if tag in self._log_files:
            self._loggers["root"].removeHandler(
                self._log_files[tag]['handler'])
        else:
            self._loggers["root"].debug(
                "Log file for tag '%s' dose not exist" % tag)

    def gen_table_log(self, tag, cols, data_list):
        """Generate table log file. A csv file will be generated.

        :param tag: tag of the log, used for specific cases
        :param cols: columns to store in the data file
        :param data_list: a list of dict
        :return: table log file name
        """
        if len(data_list) == 0:
            self._loggers["root"].debug(
                "Empty data, not generating data file.")
            return None
        if not os.path.isdir(self.log_prefix):
            os.mkdir(self.log_prefix)
        filename = os.path.join(self.log_prefix, tag + ".csv")
        try:
            with open(filename, 'w+') as fd:
                writer = csv.DictWriter(fd, fieldnames=cols)
                writer.writeheader()
                writer.writerows(data_list)
            self._loggers["root"].info("Data file %s generated:" % filename)
            return filename
        except Exception:
            self._loggers["root"].exception(
                "Error generating data log: %s" % filename)
            return None

    def getLogPath(self):
        # return the log path
        return self.logpath

    def getLogPrefix(self):
        return self.log_prefix

    def close(self):
        """close the log"""
        pass

    def link(self, text, link):
        """Output link in the log"""
        return text

    def anchor(self, text, anchor):
        """Output anchor in the log"""
        return text

    @classmethod
    def get(cls):
        """get a singleton of logger"""
        if not BasicLogger._instance:
            BasicLogger._instance = cls()
        return BasicLogger._instance


def getLog(name=None):
    """Get logger of a specific tag, chorus by default"""
    logger = logcls.get()
    return logger.getLogger(name)


def setLog():
    global logcls, log
    clsname = Config().get_config("log", "logger")
    logcls = loadClass(clsname)
    log = getLog()


def setLogPath(path):
    """Set log path, chorus will only log to stdout if not set"""
    logcls.get().setLogPath(path)


def getLogPrefix():
    """Get log path and prefix"""
    return logcls.get().getLogPrefix() + "_"


def getLogPath():
    """Get log path and prefix"""
    return logcls.get().getLogPath()


def addLogFile(tag):
    """add a log file"""
    try:
        logcls.get().addLogFile(tag)
    except BaseException:
        logcls.get().exception("Error adding log")


def removeLogFile(tag):
    """remove a log file"""
    try:
        logcls.get().removeLogFile(tag)
    except BaseException:
        logcls.get().exception("Error removing log")


def gen_table_log(tag, cols, data_list):
    return logcls.get().gen_table_log(tag, cols, data_list)


def link(text, link):
    """Output link in the log"""
    return logcls.get().link(text, link)


def anchor(text, anchor):
    """Output anchor in the log"""
    return logcls.get().anchor(text, anchor)


def closeLog():
    """Close log files"""
    logcls.get().close()


def getLogFile(tag):
    """Get a file name by tag"""
    return logcls.get().getLogFile(tag)


def sleep(sec):
    length = 50
    if sec < length:
        length = int(ceil(sec))
    step = float(sec) / length

    fmt = "Please wait: |{:<%d}|" % length
    for i in range(length):
        msg = fmt.format("=" * i)
        stdout.write('{0}\r'.format(msg))
        stdout.flush()
        time.sleep(step)

    msg = fmt.format("=" * length)
    print(msg)


def get_log_files(path='.', extensions=['.log'], n=0):
    """Get the last n'th log file

    :param path: the job path
    :param extensions: log extensions to filter
    :param n: the last n'th log, 0 means all logs
    :return: a list of file names
    """
    logs = glob.glob(os.path.join(path, LOG_PATH_PREFIX, '*'))
    logs.sort(key=os.path.getctime, reverse=True)
    files = []
    if n == 0:
        files = logs
    else:
        curjob = 1
        lastjid = None
        for l in logs:
            # get logs with same id
            m = re.search(r'chorus_(\d+)', l)
            if m:
                jid = m.group(1)
                if lastjid is None:
                    lastjid = jid
                elif lastjid != jid:
                    lastjid = jid
                    curjob += 1
                if curjob == n:
                    files.append(l)
                elif curjob > n:
                    break

    # filter file extension
    files = filter(lambda f: f.endswith(tuple(extensions)), files)
    return list(files)


# The default logging object
log = logcls = None
setLog()
