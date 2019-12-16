# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
The config management classes.
Config files are written in json format.
The file 'config' under source code folder is the Base config contains
all options and set to default value. User can edit his own config file
under '/etc/hban/' or '~/.hban/' to override the options.
"""

import os
import site
import sys
import yaml
import importlib
import inspect


##############################################
# utilities
class Singleton(type):
    """Singleton meta class which initialize the class on definition
        Limitations are:
        1. the classes use this meta cannot have extra arguments for their __init__ method
        2. the class cannot call super on init
        3. cannot use class variables on init
    """

    def __init__(self, name, bases, mmbs):
        super(Singleton, self).__init__(name, bases, mmbs)
        self._instance = super(Singleton, self).__call__()

    def __call__(self, *args, **kw):
        return self._instance


def loadClass(clsname):
    """Load a class by its' name
        Dose not work for embedded class
    """
    # split the module name and class name
    pos = clsname.rfind('.')
    module = importlib.import_module(clsname[:pos])
    return getattr(module, clsname[pos + 1:])


# extension decorator
EXT_MAP = {}


def extend(devicetag):
    """All extension should extend this class
    Collect class extensions
    Extensions can only be applied to device tags
    """

    def dec(cls):
        if devicetag in EXT_MAP:
            EXT_MAP[devicetag].append(cls)
        else:
            EXT_MAP[devicetag] = [cls]
        return cls

    return dec


############################
# Exception
class ConfigException(Exception):
    """Exception class for config"""

    def __init__(self, value):
        super(ConfigException, self).__init__()
        self.value = "Failed to load config: " + value

    def __str__(self):
        return repr(self.value)


if __file__.startswith(site.USER_SITE):
    SYSPATH = site.USER_BASE
else:
    SYSPATH = sys.prefix
    if SYSPATH == '/usr' and not os.path.isfile(
            os.path.join("/usr", "etc", "chorus", 'chorus.config')):
        SYSPATH = '/usr/local'

CHORUS_BASE_PATH = os.path.join("etc", "chorus")

LIBCONFPATH = os.path.join(SYSPATH, CHORUS_BASE_PATH)
# user can define their own config files under ~/.chorus.
USERCONFPATH = os.path.join(os.path.expanduser('~'), ".chorus")
# config files, may exist under system config path or user config path.
# The latter will override the former.
CONFIGFILE = "chorus.config"
PLUGINFILE = "plugin.config"
EXTENSIONFILE = "extension.config"
# config subpathes, may exist only under system config path
CONFIG_FOLDER = "config"
PLUGIN_FOLDER = "plugin"
EXTENSION_FOLDER = "extension"
# system config folder full path
CHORUS_CONFIG_PATH = os.path.join("etc", "chorus", CONFIG_FOLDER)
CHORUS_PLUGIN_PATH = os.path.join("etc", "chorus", PLUGIN_FOLDER)
CHORUS_EXTENSION_PATH = os.path.join("etc", "chorus", EXTENSION_FOLDER)


##############################################
# Config class
class Config(metaclass=Singleton):
    """Global config class"""
    __metaclass__ = Singleton

    # chorus will search /etc/chorus and its sub folders to load config
    def __init__(self):
        self._config = {}
        # base plugins
        self._plugins = {}
        self._device_link = {}  # link lists of device plugin decendents
        self._uuid = None  # uuid for each run

    @property
    def uuid(self):
        if self._uuid is None:
            # use pid as temp uuid if not specified.
            return str(os.getpid())
        else:
            return self._uuid

    @uuid.setter
    def uuid(self, uuid):
        if self._uuid is None:
            self._uuid = uuid
        else:
            raise ConfigException("Cannot change UUID")

    def get_uuid(self):
        return self.uuid

    def get_config(self, module, key):
        """Get config item
            config should in a two level format
        """
        if not self._config:
            self.load_config()
        p = self._config.get(module)
        if not p:
            print("ERROR: No such part in config file: %s" % module)
            return None
        else:
            return p.get(key)

    def set_config(self, module, key, value):
        """Override a config item
            config should in a two level format
        """
        if not self._config:
            self.load_config()
        p = self._config.get(module)
        if not p:
            print("ERROR: No such part in config file: %s" % module)
            return None
        else:
            p[key] = value
            return value

    def get_plugin(self, ptype, tag):
        """Get plugin class by tag

        :param ptype: plugin type
        :param tag: tag of the plugin
        :return: the class of the plugin
        """
        # lazy load to avoid import loop
        if not self._plugins:
            self.load_plugin()
            self.load_extension()
        if ptype not in self._plugins:
            print("Invalid plugin type: %s" % ptype)
            return None
        self._update_plugin_cls(ptype, tag)
        return self._plugins[ptype].get(tag, None)

    def list_plugin_tags(self, ptype):
        """List the supported plugin types"""
        if not self._plugins:
            self.load_plugin()
            self.load_extension()
        if ptype not in self._plugins:
            print("Invalid plugin type: %s" % ptype)
            return None
        return list(self._plugins[ptype].keys())

    ################################
    # Initialzation
    def _load(self, filename):
        """common yaml config file loading logic"""
        if not os.path.isfile(filename):
            print("Cannot find config file: %s" % filename)
            return {}
        try:
            with open(filename) as f:
                conf = yaml.safe_load(f)
            if not conf:
                return {}
            else:
                return conf
        except Exception:
            print("Cannot load config file: %s" % filename)
            return {}

    def _load_config_file(self, confile):
        """Load a single config file"""
        uc = self._load(confile)
        for k in uc:
            if k not in self._config:
                # user addded keys
                self._config[k] = uc[k]
            else:
                # check subkeys
                if isinstance(uc[k], dict):
                    self._config[k].update(uc[k])
                else:
                    self._config[k] = uc[k]

    def load_config(self):
        """Load config from config files"""
        # Load base config first
        self._load_config_file(os.path.join(LIBCONFPATH, CONFIGFILE))
        if not self._config:
            raise ConfigException("Cannot load base config file.")

        # load module config
        module_config_folder = os.path.join(LIBCONFPATH, CONFIG_FOLDER)
        if os.path.isdir(module_config_folder):
            for f in [x for x in os.listdir(
                    module_config_folder) if x.endswith('.config')]:
                self._load_config_file(os.path.join(module_config_folder, f))
        # Load user config
        user_config = os.path.join(USERCONFPATH, CONFIGFILE)
        if os.path.isfile(user_config):
            self._load_config_file(user_config)

    def _load_single_plugin(self, plugin_file):
        """Add a single plugin file"""
        plugins = self._load(plugin_file)
        for k in plugins:
            if k not in self._plugins:
                # print("None standarded plugin type '%s' found in: %s" % (k, plugin_file))
                self._plugins[k] = {}
            self._plugins[k].update(plugins[k])

    def _update_plugin_cls(self, ptype, tag):
        """Update the plugin cls name to class"""
        if ptype not in self._plugins:
            print("Invalid plugin type: %s" % ptype)
            return None
        clsname = self._plugins[ptype].get(tag, None)
        if isinstance(clsname, str):
            try:
                cls = loadClass(clsname)
                self._plugins[ptype][tag] = cls
            except Exception:
                raise ConfigException(
                    "Cannot load plugin: %s/%s" % (ptype, tag))

    def load_plugin(self):
        """Load plugins from plugin files"""
        # Load base config first
        self._plugins = {
            "connection": {},
            "device": {},
            "topo": {},
            "log": {},
            "repo": {},
            "cli": {}
        }
        self._load_single_plugin(os.path.join(LIBCONFPATH, PLUGINFILE))

        module_plugin_folder = os.path.join(LIBCONFPATH, PLUGIN_FOLDER)
        if os.path.isdir(module_plugin_folder):
            for f in [x for x in os.listdir(
                    module_plugin_folder) if x.endswith('.config')]:
                self._load_single_plugin(os.path.join(module_plugin_folder, f))

        # Load user plugin
        user_plugin = os.path.join(USERCONFPATH, PLUGINFILE)
        if os.path.isfile(user_plugin):
            self._load_single_plugin(user_plugin)

        # plugin inheritance map
        for tag in self._plugins["device"]:
            self._update_plugin_cls("device", tag)
            pcls = self._plugins["device"][tag]
            ancs = inspect.getmro(pcls)
            # self._plugins may contain class name or class so a class name
            # list should also be tested
            anc_names = [".".join([c.__module__, c.__name__]) for c in ancs]
            for (itag, icls) in self._plugins["device"].items():
                if itag != tag and ((icls in ancs) or (icls in anc_names)):
                    if itag not in self._device_link:
                        self._device_link[itag] = [tag]
                    else:
                        self._device_link[itag].append(tag)

    def load_extension(self):
        """Load extensions"""
        extensions = self._load(os.path.join(LIBCONFPATH, EXTENSIONFILE))

        # load module extensions
        module_extension_folder = os.path.join(LIBCONFPATH, EXTENSION_FOLDER)
        if os.path.isdir(module_extension_folder):
            for f in [x for x in os.listdir(
                    module_extension_folder) if x.endswith('.config')]:
                extensions += self._load(os.path.join(module_extension_folder, f))

        # Load user extension
        user_extension = os.path.join(USERCONFPATH, EXTENSIONFILE)
        if os.path.isfile(user_extension):
            extensions += self._load(user_extension)

        # import modules
        # map(__import__, extensions)
        for extension in extensions:
            __import__(extension)
        # change plugin classes
        dplugins = self._plugins["device"]
        for k in EXT_MAP:
            if k not in dplugins:
                raise ConfigException(
                    """Unknown device tag '%s' is extended by class %s.
                       Please check if proper plugin is configured""" %
                    (k, EXT_MAP[k]))
            else:
                self._update_plugin_cls("device", k)
                exts = EXT_MAP[k]
                self._extend(exts, k)

    def _extend(self, exts, tag):
        """nested method to apply extension to a class and its descendants"""
        bases = exts + [self._plugins["device"][tag]]
        clsnames = list(c.__name__ for c in bases)
        class_name = "_".join(clsnames)
        enhcls = type(class_name, tuple(bases), {})
        self._plugins["device"][tag] = enhcls
        if tag in self._device_link:
            for stag in self._device_link[tag]:
                self._extend(exts, stag)
