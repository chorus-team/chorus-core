# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Topology basic classes
By default `FixedTopo` processes yaml based topology file in the following format:

"""
from ..device import getDevice, Interface
from ..topo import Topo, TopoException


class FixedTopo(Topo):
    """Fixed Topo class
    Basic type of topo with fixed connections
    """
    _reserved_keys = ["conn", "type", "name", "schema"]

    #
    def __init__(self, topodict):
        """Initialization"""
        super(FixedTopo, self).__init__(topodict)

    #
    def _validate(self):
        # connection must exist in fixed topo
        if super(FixedTopo, self)._validate():
            if 'conn' not in self.dict:
                self.log.warn("No connection found in topo %s", self.name)
                self.dict['conn'] = {}
            return True
        else:
            return False

    # fixed topo dict is the final front, this class now handles only this one
    def init(self, disconnected=False):
        """parse fixed topo dict and return modified device objects
        :disconnected: do not connect devices in the topology
        """
        super(FixedTopo, self).init()
        self.log.info("Start to initial the Fixed topology...")
        # init devices
        for k in self.dict:
            if k not in self._reserved_keys:
                attrs = self.dict[k]
                self.log.info(">>> Initializing device: %s", k)
                d = getDevice(name=k, **attrs)
                # Add interfaces to device
                for da in attrs:
                    if da in self.dict["conn"]:
                        if isinstance(attrs[da], list):
                            intf = []
                            for ifname in attrs[da]:
                                i = Interface(d, ifname)
                                i.intf = ifname
                                intf.append(i)
                        else:
                            intf = Interface(d, da)
                            intf.intf = attrs[da]
                        setattr(d, da, intf)

                self.devices[k] = d

        # Add ip schema
        if 'schema' in self.dict:
            ipschema = self.dict['schema']
            for c in self.dict["conn"]:
                if c in ipschema:
                    cds = self.dict["conn"][c]
                    for i in range(len(cds)):
                        intf = getattr(self.devices[cds[i]], c)
                        ip = ipschema[c]["ip"][i]
                        mask = ipschema[c].get("mask", 24)
                        intf.setIP(ipmask='%s/%s' % (ip, mask))
                        intf.zone = ipschema[c].get("zone", "trust")
                else:
                    raise TopoException("ipschema and connection not match")

        # Connect all the devices
        if not disconnected:
            self.log.debug("Connect the devices immediately")
            for d in self.devices:
                if 'conn_method' in self.dict[d]:
                    self.devices[d].setDefaultConnMethod(
                        self.dict[d]["conn_method"])
                self.devices[d].connect()

        self.log.info("End for Fixed topology initialization.")
