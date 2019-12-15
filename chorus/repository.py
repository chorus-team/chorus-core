# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
The repository base module, used to find scripts automatically
"""

import os
from .config import Config
from .log import log

config = Config()


class Repository(object):
    """Base repository class"""

    def __init__(self):
        super(Repository, self).__init__()

    def getPath(self, uri):
        """Map the repo path to local."""
        pass

    @classmethod
    def listTypes(cls):
        return config.list_plugin_tags('repo')

    @classmethod
    def syncPath(cls, type="local", uri="."):
        """Sync the repo path and return the local path"""
        repo = config.get_plugin("repo", type)
        if not repo:
            raise RepoException("Repo type '%s' not supported" % type)
        path = repo().getPath(uri)
        if os.path.isdir(path):
            return path
        else:
            raise RepoException("The repo path does not exist: %s" % path)


class Local(Repository):
    """Local repositoy"""

    def getPath(self, uri):
        """The uri is the local path"""
        if os.path.isdir(uri):
            return uri
        else:
            raise RepoException("The repo path does not exist: %s" % uri)


class RepoException(Exception):
    """repository exceptions"""

    def __init__(self, value):
        super(RepoException, self).__init__()
        self.value = "Repository Error: " + value
        log.exception(self.value)

    def __str__(self):
        return repr(self.value)
