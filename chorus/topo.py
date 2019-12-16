# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Topology basic classes
"""
from .log import log, getLog
from .utils import load_yaml
from .config import Config, loadClass


############################
# topo readers
class TopoReader(object):
    """Reader of topology, may read from difference sources and parse them into dict"""

    def __init__(self, uri):
        super(TopoReader, self).__init__()
        self.uri = uri
        self.dict = {}

    def parse(self):
        """Parse the topo string to dict, implement in subclasses"""
        pass


class YamlTopoReader(TopoReader):
    """YamlTopoReader"""

    def __init__(self, uri):
        super(YamlTopoReader, self).__init__(uri)

    def parse(self):
        try:
            topodict = load_yaml(self.uri)
            if isinstance(topodict, dict):
                return topodict
            elif isinstance(topodict, list):
                # to be compatitable with older versions
                return topodict[0]
            else:
                raise TopoException("Unknown topo format: %s" % self.uri)
        except Exception as e:
            raise TopoException(
                "Error parsing yaml topology file %s: %s" % (self.uri, e))


############################
# Topology classes
class Topo(object):
    """Base Topo class"""
    # stores all topologies for latter use
    __topos__ = {}
    #
    __toporeader = loadClass(Config().get_config("topo", "reader"))

    # used to check topo keywords
    #   subclass should override this for their own purpose
    __reserved_keys = ["type", "name", "desc"]

    # The topology type, used for mapping between topo type and class
    topo_type = "base"

    def __init__(self, topodict):
        """init topology"""
        super(Topo, self).__init__()
        self.dict = topodict
        self.log = getLog("TOPOLOGY")
        # manditory member
        self.devices = {}
        self.x_args = {}
        if self._validate():
            self._register()
        else:
            raise TopoException("Topology %s is not valid" % topodict["name"])

    def _register(self):
        """Register the topology to __topos__"""
        Topo.__topos__[str(self.name)] = self

    def _validate(self):
        """Validate the topology itself,
            called when loading topologies. Do not do enviroment specific logic here
            return True or False
            return true by default, ixmplemented in subclasses"""
        if "name" not in self.dict:
            log.error("Topology has no name!")
            return False
        elif self.dict["name"] in Topo.__topos__:
            log.error("Duplicate topology %s defined" % self.dict["name"])
            return False
        else:
            self.name = self.dict["name"]
            if "desc" in self.dict:
                self.description = self.dict["desc"]
                del(self.dict["desc"])
            else:
                self.description = ""
        return True

    def init(self, disconnected=False):
        """Initialize topology,
            typically init all devices, and fill context
            raise TopoException when fail
            implemented in subclasses"""
        self.log.info("> Initializing topology %s", self.name)
        # set user arguments from here
        for k in list(self.dict):
            if k.startswith("x_"):
                self.x_args[k] = self.dict[k]
                del(self.dict[k])

    def clean(self):
        """Cleaning up topology,
            typically called after a batch of scripts with same topo finished
        """
        self.log.info("> Cleaning up topology %s", self.name)
        for d in self.devices.values():
            d.disconnect()

    @classmethod
    def getTopo(cls, name):
        """Manage all aviable topologies"""
        if name not in cls.__topos__:
            log.warn("Topology %s not found" % name)
            return None
        log.debug("Topology {} found.".format(name))
        return cls.__topos__[name]

    @classmethod
    def addTopo(cls, uri):
        """Manage all aviable topologies"""
        log.info("Adding topology file %s" % uri)
        reader = cls.__toporeader(uri)
        topodict = reader.parse()
        if "type" not in topodict:
            raise TopoException("Type in topology file is empty: %s" % uri)
        if topodict['type'] == "base":
            raise TopoException(
                "Base type of topology is uninitializable: %s" % uri)
        topocls = Config().get_plugin("topo", topodict['type'])
        if not topocls:
            raise TopoException(
                "Unsupported topology type %s in file %s" %
                (topodict['type'], uri))
        else:
            # init and register
            topocls(topodict)


############################
# Exceptions
class TopoException(Exception):
    """Exception handling class for topology"""

    def __init__(self, value):
        super(TopoException, self).__init__()
        self.value = "Topology Error due to: " + value
        log.error("Topo error happens!!")
        log.exception(value)

    def __str__(self):
        return repr(self.value)
