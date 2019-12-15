# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
chorus IP functions
"""

import ipaddress


def ipVersion(ip_addr):
    """Get IP address's version"""
    try:
        return ipaddress.ip_address(ip_addr.decode('utf-8')).version
    except BaseException:
        return None


def networkVersion(subnet):
    """Get IP network's version"""
    try:
        return ipaddress.ip_network(subnet.decode('utf-8')).version
    except BaseException:
        return None


def isValidIP(ip_addr):
    """Check the ip_addr is a valid IP address"""
    try:
        return ipaddress.ip_address(ip_addr.decode('utf-8'))
    except BaseException:
        return False


def ip2int(ip_addr):
    """ip address to int"""
    try:
        return int(ipaddress.ip_address(ip_addr.decode('utf-8')))
    except BaseException:
        return None


def int2ip(int_num):
    """int to an ip address"""
    try:
        return ipaddress.ip_address(int_num)
    except BaseException:
        return None


def isInSameNetwork(ip_addr1, ip_addr2, prefix):
    """Check two ip address in same network or not"""
    ip1 = ip_addr1.decode('utf-8')
    ip2 = ip_addr2.decode('utf-8')
    try:
        return ipaddress.ip_interface(
            "%s/%s" %
            (ip1, prefix)).network == ipaddress.ip_interface(
            "%s/%s" %
            (ip2, prefix)).network
    except BaseException:
        return False


# ip utilities
def ipAdd(ipstr, add="0.0.0.1"):
    """Add a number to ip address
    return the new ip address string, in the same format as the input ip string
    """
    # check if the address ip masked
    ip = ipstr.decode('utf-8')
    if '.' in str(add) or ':' in str(add):
        add = ip2int(add)
    add = int(add)
    if '/' in ip:
        addr = ipaddress.ip_interface(ip)
        raddr = addr + add
        raddr.network = addr.network
        return str(raddr)
    else:
        addr = ipaddress.ip_address(ip)
        return str(addr + add)
