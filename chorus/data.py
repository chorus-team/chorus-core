# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

import csv
from .utils import load_yaml
from .log import log, getLog
import json


class DataParse(object):
    """Test data parse class"""

    def __init__(self, datafile):
        self.uri = datafile
        self.dict = {}
        self.filetype = self.getDataType()
        self.log = getLog("DATAPARSE")

    def getDataType(self):
        f = self.uri.split('.')
        if f[-1] in ["yaml", "yml"]:
            filetype = "yaml"
        elif f[-1] == "json":
            filetype = "json"
        else:
            log.info("Unknow data file type, will parse it as csv file")
            filetype = "csv"
        return filetype

    def parse(self):
        if self.filetype == "yaml":
            return self.yamlParse()
        elif self.filetype == "json":
            return self.jsonParse()
        else:
            return self.csvParse()

    def yamlParse(self):
        try:
            datadict = load_yaml(self.uri)
            if isinstance(datadict, dict):
                return [datadict]
            elif isinstance(datadict, list):
                return datadict
            else:
                raise DataException("Parse data file with yaml: %s" % self.uri)
        except Exception as e:
            raise DataException(
                "Error parsing yaml data file %s: %s" % (self.uri, e))

    def csvParse(self):
        arglist = []
        with open(self.uri, 'r') as f:
            reader = csv.reader(f)
            # header
            cols = reader.next()
            for row in reader:
                c = dict(zip(cols, row))
                # c.update(args)
                arglist.append(c)
        return arglist

    def jsonParse(self):
        try:
            with open(self.uri, 'r') as f:
                datadict = json.load(f)
                if isinstance(datadict, dict):
                    return [datadict]
                elif isinstance(datadict, list):
                    return datadict
                else:
                    raise DataException(
                        "Parse data file with json: %s" % self.uri)
        except Exception as e:
            raise DataException(
                "Error parsing json data file %s: %s" % (self.uri, e))


############################
# Exceptions
class DataException(Exception):
    """Exception handling class for data file"""

    def __init__(self, value):
        super(DataException, self).__init__()
        self.value = "Data parse Error due to: " + value
        log.error("Data file parse error happens!!")
        log.exception(value)

    def __str__(self):
        return repr(self.value)
