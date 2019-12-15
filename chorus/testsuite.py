# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
Testsuite management
"""

import os
import time
# todo: replace imp with importlib
import imp
import inspect
import re

from chorus.topo import Topo
from .log import log, getLogPath, addLogFile, removeLogFile, closeLog, link, getLogFile
from . import connection
from .config import loadClass
from .data import DataParse
from .testcase import Testcase


class Testsuite(object):
    """Testsuite which groups and calls all cases

    Testsuite provides some callback points, one can use `Testsuite.register` method to register their
    own function on those points.

    :param str pathlist: a list of path or python file names, from which the testcase will be loaded.
    """
    _callback_points = {
        # Called after testcases loaded and sorted
        "on_cases_load": [lambda ts, cases: log.debug("Callback on %s testcases loading.", len(cases))],
        # Called after topology initiated
        "before_topo_init": [lambda ts, topo: log.debug("Callback before topology initialization.")],
        # Called after topology initiated
        "on_topo_init": [lambda ts, topo: log.debug("Callback on topology initialization.")],
        # Called before each testcase run
        "before_case_run": [lambda ts, tc: log.debug("Callback before testcase %s.", tc.name)],
        # Called after each testcase run
        "on_case_run": [lambda ts, tc, result: log.debug("Callback after testcase %s.", tc.name)],
        # Called after each testcase run
        "on_report": [lambda ts, results: log.debug("Callback for testsuite result collection.")],
    }

    def __init__(self, pathlist=['.'], base_path='.', recursive=False):
        super(Testsuite, self).__init__()
        self.cases = []
        self._curcase = None
        self._case_results = {}
        self._starttime = time.time()
        # module to path cache to avoid duplication import
        self.pathlist = pathlist
        self.base_path = base_path
        self.recursive = recursive
        self._module_path = {}
        self._case_class = {}
        self._loadTestCase()

    def loadSuiteFile(self, suite_file, args={}):
        """Get all cases in a `suite file`_,
        a suite file includes lines in following format:

            <case name> [arguments]

        :param str suite_file: the suite file
        :param dict args: keyword arguments used overwrite those in suite files
        :rtype: Booblean
        """
        cases = []
        try:
            suite_file = os.path.join(self.base_path, suite_file)
            f = open(suite_file, 'r')
            for line in f:
                c = {}
                line = line.strip()
                if not line.startswith("#") and len(line) > 0:
                    parts = line.split()
                    c["name"] = parts[0]
                    c["args"] = {}
                    for pair in parts[1:]:
                        p = pair.split('=')
                        c["args"].update({p[0]: p[1]})
                    cases.append(c)
        except BaseException:
            log.exception("Suite file '%s' error" % suite_file)
            return False

        for c in cases:
            # each case may has its own arguments
            #  while user defined arguments have higher priority
            c["args"].update(args)
            self.addcase(c["name"], **c["args"])
        return True

    def loadDataFile(self, datafile, cases=[], args={}):
        """Load testcases according to `data file`_.

        :param str datafile: path to data file
        :param list cases: The testcases to run
        :param dict args: arguments used overwrite those in suite files
        :rtype: Booblean
        """
        arglist = []
        datafile = os.path.join(self.base_path, datafile)
        if (not cases) and len(self._case_class) > 1:
            log.error("More than one testcase specified when using data file")
            return False
        elif not cases:
            log.debug("No testcase specified, use the one in script implicitly")
            case_name = list(self._case_class.keys())[0]
        elif len(cases) > 1:
            log.error("More than one testcase specified when using data file")
            return False
        elif cases[0] not in self._case_class:
            log.error("Testcase %s not found" % cases[0])
            return False
        else:
            case_name = cases[0]
        data = DataParse(datafile).parse()
        for c in data:
            c.update(args)
            self.addcase(case_name, **c)
        return True

    def loadTestcaseReg(self, cases=[], args={}, per_case_params=[]):
        """Load testcases by regular expression

        :param list cases: regular expressions by which test cases are filtered
        :param dict args: arguments used overwrite those in suite files
        :rtype: Booblean
        """
        if len(cases) == 0 and len(self._case_class) > 0:
            # run all cases by default
            cases = [""]
        if len(per_case_params) > 0:
            if len(per_case_params) != len(cases):
                raise SuiteException(
                    "Count of per case parameters is different from count of testcases.")

        for i in range(len(cases)):
            case_name = cases[i]
            cur_args = args
            if len(per_case_params) > 0:
                cur_args = per_case_params[i]
                cur_args.update(args)
            cur_case = None
            for tcname in self._case_class:
                if re.search(case_name, tcname.split(':')[-1]):
                    cur_case = tcname
                    self.addcase(tcname, **cur_args)
            # Fall back to full testcase name search from syspath if no case
            # found
            if cur_case is None:
                log.info("Looking for testcase in syspath")
                try:
                    tclass = loadClass(case_name)
                    self._case_class[case_name] = tclass
                    self.addcase(case_name, **cur_args)
                except Exception:
                    log.exception("Error loading testcase: %s" % case_name)

    def _loadTestCase(self):
        """Load testcase classes from pathlist"""
        # load modules
        for p in self.pathlist:
            p = os.path.join(self.base_path, p)
            modules = []
            # load module if necessary
            if p in self._module_path:
                modules = self._module_path[p]
            else:
                if os.path.isdir(p):
                    # p = os.path.abspath(p)
                    modules_list = []
                    if self.recursive:
                        log.debug("Recursive search testcases from %s ..." % p)
                        for fpath, dirs, fs in os.walk(p):
                            for f in [x for x in fs if x.endswith('.py')]:
                                modules_list.append(os.path.join(fpath, f))
                    else:
                        for f in [
                                x for x in os.listdir(p) if x.endswith('.py')]:
                            modules_list.append(os.path.join(p, f))

                    for m in modules_list:
                        try:
                            modules.append(imp.load_source(
                                os.path.relpath(m, start=p).split(".")[0], m))
                            log.debug("Testcase Module %s added", m)
                        except BaseException:
                            log.debug("Error loading script %s", m)

                    self._module_path[p] = modules
                elif os.path.isfile(p) and p.endswith('.py'):
                    modules.append(imp.load_source(
                        os.path.basename(p).split('.')[0], p))
                    log.debug("Testcase Module %s added", p)
                else:
                    log.error("No valid python file or path specified.")
                    raise SuiteException("No valid module")

            # map each testcase subclasses in the modules
            for m in modules:
                for name, c in inspect.getmembers(m, inspect.isclass):
                    # skip classes defined in other modules
                    if c.__module__ != m.__name__:
                        continue
                    try:
                        anc = inspect.getmro(c)
                    except BaseException:
                        continue
                    cname = ":".join([c.__module__, name])
                    log.debug("%s inspected" % cname)
                    # The second generation of ancestors is Testcase
                    if (len(anc) > 2) and (anc[-2].__name__ == "Testcase"):
                        if cname in self._case_class:
                            log.warn(
                                "Duplicate testcase found and ignored: %s" %
                                cname)
                        else:
                            log.info("Testcase %s found", cname)
                            self._case_class[cname] = c
        if len(self._case_class) == 0:
            log.debug("No testcase found from local folders!")
            return True
        else:
            log.info("%s cases found." % len(self._case_class))
            return True

    def addcase(self, t_case_name, **kwargs):
        """Add a single :class:`.testcase.Testcase` to testsuite

        :param str t_case_name: the name of the testcase
        :param kwargs: the testcase parameters
        """
        if t_case_name not in self._case_class:
            log.error("Test case not found: %s" % t_case_name)
            return False
        cls = self._case_class[t_case_name]
        if cls.topo is None:
            log.warn("--------------------------------------------------")
            log.warn(
                "=== Test case %s does not have topo bind ==",
                t_case_name)
            log.warn("===   take it as a lib case ==")
            log.warn("--------------------------------------------------")
            return False
        c = {"t_case_name": t_case_name,
             "t_case_class_name": t_case_name,
             "t_case_class": cls,
             "t_case_fx": cls.getFixtureChain(),
             "topo": cls.topo,
             "kwargs": kwargs,
             "t_case_result": None}
        self.cases.append(c)
        log.info("--------------------------------------------------")
        log.info("=== Test case %s added ==", t_case_name)
        log.info("--------------------------------------------------")
        return True

    def _sortcase(self):
        """sort cases according to keywords"""
        topo_dict = {}
        # sort according to topo
        for c in self.cases:
            t = c.get("topo")
            if t in topo_dict:
                topo_dict[t].append(c)
            else:
                topo_dict[t] = [c]
        # sort cases in each topo according to fixture_chain, i.e. their parent
        # class
        for t in topo_dict.values():
            # t.sort(lambda x,y: cmp(x['t_case_fx'], y['t_case_fx']))
            t.sort(key=lambda x: x['t_case_fx'])
        d = list(topo_dict.values())
        # sort according to case number of each topo, the more cases the higher priority
        # d.sort(lambda x,y: cmp(len(y), len(x)))
        d.sort(key=lambda x: len(x))
        self.cases = [c for sublist in d for c in sublist]

    def run(
            self,
            test=False,
            pause_on_fail=False,
            topo_only=False,
            continue_on_fail=None):
        """The main logic of running testcases
        Use dummy connection if test specified

        :param test: Dry run switch
        :param pause_on_fail: drop to pdb prompt on fail
        :param topo_only: just init topology. (do not run any cases, useful for device upgrade)
        :param continue_on_fail: global continue on fail config.
        :return:
        """
        connection.dummy_conn = False
        if test:
            # change connections to dummy
            connection.dummy_conn = True
            continue_on_fail = True
        # sort cases
        self._sortcase()
        # case load callback
        self.callback("on_cases_load", self, self.cases)

        log.info("#" * 60)
        log.info("### {:^52} ###".format(
            "Start running {} cases".format(len(self.cases))))
        log.info("#" * 60)
        log.info("")

        cur_topo = None
        fixture_chain = []
        next_chain = []
        for i in range(len(self.cases)):
            c = self.cases[i]
            self._curcase = c.get("t_case_class")
            tccls = c.get("t_case_class")
            clsname = c.get("t_case_class_name")
            topo_name = c.get("topo")
            log.debug("Start running {} with topo {}".format(
                clsname, topo_name))
            t = tccls(**c['kwargs'])
            cname = t.name
            addLogFile(cname)
            c["t_case_name"] = cname
            c["t_case_result"] = t.result
            if not cur_topo or topo_name != cur_topo.name:
                log.debug(
                    "Topology {} may not init, try initializing...".format(topo_name))
                cur_topo = Topo.getTopo(topo_name)
                if not cur_topo:
                    log.warn(
                        "Topology for test %s not found, skipping..." % cname)
                    state = Testcase.SKIPPED
                    t.result.rcode = state
                    self._add_case_result(c, state)
                    continue
                log.info("#" * 60)
                log.info("### {:^52} ###".format(
                    "Initializing Topology: %s" % topo_name))
                log.info("#" * 60)
                log.info("")
                fixture_chain = []
                try:
                    self.callback("before_topo_init", self, cur_topo)
                    cur_topo.init(
                        disconnected=not self._curcase.check_topo_devices)
                    self.callback("on_topo_init", self, cur_topo)
                    if topo_only:
                        log.info("Test finished due to 'topo_only' mark set.")
                        removeLogFile(cname)
                        break
                except BaseException as e:
                    log.exception("Topo init exception: %s" % e)
                    # reset on topo fail
                    cur_topo = None
                    fixture_chain = []
                    next_chain = []
                    state = Testcase.TOPO_FAIL
                    self._add_case_result(c, state)
                    removeLogFile(cname)
                    break
            # check next chain
            if i == len(self.cases) - \
                    1 or self.cases[i + 1]['topo'] != topo_name:
                next_chain = []
            else:
                next_chain = self.cases[i + 1]['t_case_fx']

            try:
                log.info("#" * 60)
                log.info("### {:^52} ###".format("Test Case Starts"))
                log.info("### Class: {:^45} ###".format(clsname))
                log.info("### Name: {:^46} ###".format(cname))
                log.info("#" * 60)
                log.info("")
                t.setParsedTopo(cur_topo)
            except TypeError:
                log.error(
                    "Testcase Parameter Error. Please check your case definition at:")
                filename = inspect.getsourcefile(tccls)
                _, lineno = inspect.getsourcelines(tccls.__init__)
                log.exception("  File: %s, Line: %s" % (filename, lineno))
                removeLogFile(cname)
                return False
            # override running state
            if continue_on_fail is not None:
                tccls.c_continue_on_fail = continue_on_fail
            # before run callback
            self.callback("before_case_run", self, t)
            # run case
            r = t.run(pause_on_fail=pause_on_fail,
                      fixture_chain=fixture_chain, next_chain=next_chain)
            c["t_case_result"] = r
            state = r.rcode
            # after run callback
            self.callback("on_case_run", self, t, r)
            # clean up topology if necessary
            if i == len(self.cases) - \
                    1 or self.cases[i + 1]['topo'] != topo_name:
                try:
                    cur_topo.clean()
                except BaseException as e:
                    log.exception("Topo cleanup exception: %s" % e)
                    state = Testcase._tfvalue

            self._add_case_result(c, state)
            removeLogFile(cname)

        # report callback
        self.callback("on_report", self, self._case_results)

        log.info("#" * 60)
        log.info("### {:^52} ###".format("ALL TESTCASES FINISHED"))
        log.info("### {:<52} ###".format(
            "Totally {} cases".format(len(self.cases))))
        for k in self._case_results:
            log.info(
                "### ++{:<50} ###".format("{}: {}".format(k, len(self._case_results[k]))))
            case_list = [c for c in self._case_results[k]]
            for case in case_list:
                case_name = case.get('t_case_name')
                case_log = getLogFile(case_name)
                log.info(
                    "###  |--{:<48} ###".format(link(case_name, case_log)))
        log.info("### Log: {:<47} ###".format(getLogPath()))
        log.info("#" * 60)

        # close the log
        closeLog()
        rslt_keys = list(self._case_results.keys())
        if len(rslt_keys) > 0:
            for k in rslt_keys:
                if k not in [Testcase.STATES[Testcase.PASS],
                             Testcase.STATES[Testcase.SKIPPED]]:
                    return False

        return True

    def _add_case_result(self, case, state_code):
        """Store the case result to _case_results"""
        state = Testcase.STATES[state_code]
        log.info("#" * 60)
        log.info("### {:<52} ###".format(
            "TestCase: {}".format(case.get("t_case_name"))))
        log.info("### {:<52} ###".format("Result: {}".format(state)))
        log.info("#" * 60)
        log.info("")
        if state in self._case_results:
            self._case_results[state].append(case)
        else:
            self._case_results[state] = [case]

    def callback(self, cb_point, *args):
        if cb_point not in Testsuite._callback_points:
            log.error(
                "Error calling callback: no such callback point %s", cb_point)
            return False
        # call each callback in registration order
        for cb in Testsuite._callback_points[cb_point]:
            cb(*args)

    @classmethod
    def register_callback(cls, cb_point, callback):
        """register different callbackpoints for testsuite

        Current supported callbacks are:
        * on_cases_load: Called after testcases loaded and sorted
        * before_topo_init: Called before topology initiated
        * on_topo_init: Called after topology initiated
        * before_case_run: Called before each testcase run
        * on_case_run: Called after each testcase run
        * on_report: Called after each testcase run

        :param cb_point: the callback point
        :param callback: the callback function
        :rtype: bool
        """
        if cb_point not in cls._callback_points:
            log.error(
                "Error registering callback: no such callback point %s",
                cb_point)
            return False
        cls._callback_points[cb_point].append(callback)
        return True


class SuiteException(Exception):
    """Exception handling class for testsuite"""

    def __init__(self, value):
        super(SuiteException, self).__init__()
        self.value = "Suite Error due to: " + value
        log.exception("Suite Error happens: %s!!", value)

    def __str__(self):
        return repr(self.value)
