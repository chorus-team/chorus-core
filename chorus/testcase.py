# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
The main test logic
"""
import time
import datetime
import inspect
import re
import sys
import traceback
import pdb

from .log import log
from .utils import ChorusThread, roclassproperty


class Testcase(object):
    """The base class of chorus testcases. All user defined testcases should inherit from this one.
    Topology:

        A subclass of Testcase should have its :attr:`~topo` attribute set to let chorus finds the proper topology.

    Test steps:

        By default Testcase will take its direct methods whose name starts with *step[seq]* as test steps.
        *seq* means the test step order, usually its a integer, and if defined in *int_int*, Testcase will
        take is as a substep. All substeps of the same step will run in paralelle.

        User can also inherit :meth:`~init` and :meth:`~clean` method to define the initialization and cleanup of
        a test case procedure.

        Each user defined test step should return Testcase.PASS or Testcase.FAIL. If any uncaught exception
        happens in a step, Testcase will mark that step as Testcase.ABORT.

    Testcase inheritance:

        All user testcase must inherit from chorus.Testcase directly or indirectly. Inheritance will not happen with
        teststeps, which means chorus will only run steps defines in current testcase but not its parent. The only
        exception is Fixture_.

    .. _Fixture:

        chorus supports fixture by Testcase class inheritance. All *init* and *clean* methods in any testcase will
        be considered as fixture. Thus testcase inheritance will also form a fixture chain, and user need not to
        call *super* in these methods. chorus will handle the chain automatically. For example, you have 3 testcases
        all of which defines its own *init* and *clean* method,
        and their relationships are like:

        ::

            case1--->case2--->case3--->chorus.Testcase

        Then their *init* method will be called in the following order:

        ::

            case3.init, case2.init, case1.init

        And their *clean* method will be called in the following order:

        ::

            case1.clean, case2.clean, case3.clean

        chorus also tries to reduce fixture calls as much as possible. For example, if you run another testcase
        *case4* which also inherits case2 and has the same topology, right after case3, chorus will not call *clean*
        and *init* fixture of *case2* and *case3* between *case1* and *case4*.

    """
    name = ""
    desc = "This is the base class of testcases, no case included"
    topo = None
    '''Topology of the testcase'''

    # Global context to control the running behaviour, may overridden by
    # initialization parameters
    c_continue_on_fail = False  # Continue the next step if any even if current one fails
    '''Continue to run the remaining steps when a step fails.'''
    # unlike c_continue_on_fail, _pause_on_fail can only be defined for
    # Testcase class
    _pause_on_fail = False
    _p = None
    check_topo_devices = True
    '''Connect topology devices on init.'''

    _passvalue = 1 << 2
    _failvalue = 1 << 3
    _abortvalue = 1 << 4
    _tfvalue = 1 << 5
    _cfvalue = 1 << 6
    _unvalue = 1 << 7
    _skippedvalue = 1 << 7

    STATES = {
        _passvalue: "PASS",
        _failvalue: "FAIL",
        _abortvalue: "ABORT",
        _tfvalue: "TOPO_FAIL",
        _cfvalue: "CONN_FAIL",
        _unvalue: "UNKNOWN",
        _skippedvalue: "SKIPPED"
    }
    METHOD_PREFIX = "step"

    def __init__(self, **kwargs):
        super(Testcase, self).__init__()
        # self._mapTopo(resource)
        # primarily used for overriding the class parameters
        log.info(">>>Testcase initialized with args: %s", kwargs)
        self.__dict__.update(kwargs)
        if not self.name:
            self.name = self.__class__.__name__
        self.log = log
        self.result = Result(self.name, rcode=self._unvalue)

    ######
    # test state as properties for instrumentation
    # pylint: disable=no-self-argument
    @roclassproperty
    def PASS(cls):
        return cls._passvalue

    @roclassproperty
    def FAIL(cls):
        if cls._pause_on_fail:
            # pause on caller
            cls._p.set_trace(sys._getframe(2))
        return cls._failvalue

    @roclassproperty
    def ABORT(cls):
        if cls._pause_on_fail:
            cls._p.set_trace(sys._getframe(2))
        return cls._abortvalue

    @roclassproperty
    def TOPO_FAIL(cls):
        if cls._pause_on_fail:
            cls._p.set_trace(sys._getframe(2))
        return cls._tfvalue

    @roclassproperty
    def CONN_FAIL(cls):
        if cls._pause_on_fail:
            cls._p.set_trace(sys._getframe(2))
        return cls._cfvalue

    @roclassproperty
    def UNKNOWN(cls):
        if cls._pause_on_fail:
            cls._p.set_trace(sys._getframe(2))
        return cls._unvalue

    @roclassproperty
    def SKIPPED(cls):
        return cls._skippedvalue

    ######
    def setParsedTopo(self, parsed_topo):
        self.parsed_topo = parsed_topo
        # escalate device to testcase member to simplify device call
        # device are mandatory in topology
        for d in parsed_topo.devices:
            setattr(self, d, parsed_topo.devices[d])
        # set x_args
        for x in parsed_topo.x_args:
            setattr(self, x, parsed_topo.x_args[x])

    def init(self):
        """User initialization step. Override this in subclasses."""
        return Testcase.PASS

    def clean(self):
        """User cleanup step. Override this in subclasses."""
        return Testcase.PASS

    def _postClean(self):
        self.parsed_topo.clean()
        return Testcase.PASS

    # The calling template
    def run(self, pause_on_fail=False, fixture_chain=[], next_chain=[]):
        """

        :param bool pause_on_fail: Whether pause when a step fails
        :param list fixture_chain: current excuted init fixtures
        :param list next_chain: fixture chain of the next testcase
        :return: result summary
        """
        log.info("=" * 30)
        log.info("Testcase: %s", self.__class__.__name__)
        if self.__doc__:
            for l in self.__doc__.split("\n"):
                log.info("  %s", l)
        log.info("=" * 30)
        log.info("")

        try:
            log.debug("Start running testcase {}".format(
                self.__class__.__name__))
            self.result.stage = Result.STAGE_INIT
            self.result.rcode = Testcase._passvalue
            # prepare steps
            step_erro = {"step": "preparing steps",
                         "desc": "Failed preparing test steps"}
            steps = self.getSteps()
            self.result.step_count = len(steps.keys())
            # set pause_on_fail for user steps
            Testcase._pause_on_fail = pause_on_fail
            if pause_on_fail:
                Testcase._p = pdb.Pdb()
            step_erro = {"step": "init",
                         "desc": "Testcase initialization failed"}
            log.info("=" * 20)
            log.info(">>>Initializing User Environment...<<<")
            log.info("=" * 20)
            # init fixture chain
            local_chain = self.__class__.getFixtureChain()
            if len(fixture_chain) > len(local_chain):
                # clear next_chain to teardown all lagacy fixtures
                next_chain = []
                raise TestException(
                    "Former fixture chain not cleaned up properly.")
            for i in range(len(fixture_chain)):
                if local_chain[i]['name'] != fixture_chain[i]['name']:
                    # clear next_chain to teardown all legacy fixtures
                    next_chain = []
                    raise TestException(
                        "Former fixture chain not cleaned up properly.")
            # init the rest
            init_rslt = Testcase._passvalue
            for fx in local_chain[len(fixture_chain):]:
                if 'init' in fx:
                    self.log.info(">>> Calling init of %s" % fx['name'])
                    init_rslt = fx['init'](self)
                    if init_rslt == Testcase._failvalue or init_rslt == Testcase._skippedvalue:
                        break
                    else:
                        fx["case"] = self
                        fixture_chain.append(fx)
            # be careful not to use class properties directly in meta unless
            # you know what you are doing
            if init_rslt not in Testcase.STATES:
                # Do not check pass for init and clean
                init_rslt = Testcase._passvalue
            if init_rslt == Testcase._skippedvalue:
                self.result.rcode = init_rslt
                log.info("Skipped testcase %s` ", self.name)
            elif init_rslt != Testcase._passvalue:
                self.result.failed_on.append(step_erro)
                self.result.rcode = init_rslt
                log.error("Failed initializing testcase %s` ", self.name)
            else:
                log.info("=" * 25)
                log.info(">>>Running steps ...<<<")
                log.info("=" * 25)
                self.result.stage = Result.STAGE_STEP
                sids = sorted(steps.keys())
                state = Testcase._passvalue
                for i in sids:
                    step_erro = {
                        "step": "step" +
                        str(i),
                        "desc": "Failed on test step(s) %s" %
                        i}
                    state, desc, rlist = self._runStep(i, steps[i])
                    step_erro["desc"] = desc
                    self.result.step_run += 1
                    self.result.step_results.append(rlist)
                    if state != Testcase._passvalue:
                        if state not in Testcase.STATES:
                            log.warn(
                                "Unknown test result, make sure you return a Testcase state for the step.")
                            state = Testcase.UNKNOWN
                        self.result.rcode = state
                        self.result.failed_on.append(step_erro)
                        if not self.c_continue_on_fail:
                            break
        except (KeyboardInterrupt, SystemExit) as e:
            log.error("User interrupted.")
            raise e
        except BaseException as e:
            log.error("*** Exception happened:")
            log.error("    Stage: %s" % self.result.stage)
            log.error("    Step: %s" % step_erro["step"])
            log.exception("    Except: %s" % e)
            self.result.failed_on.append(step_erro)
            self.result.rcode = Testcase.ABORT
        finally:
            if self.result.rcode == Testcase._skippedvalue:
                self.result.end_sec = time.time()
                self.result.stage = Result.STAGE_FINISHED
                # return result
                return self.result
            Testcase._pause_on_fail = False
            try:
                log.info("=" * 25)
                log.info(">>>Cleaning up User Environment...<<<")
                log.info("=" * 25)
                self.result.stage = Result.STAGE_CLEAN
                step_erro = {"step": "cleanup",
                             "desc": "Testcase cleaning up failed"}
                # clean only longest common prefix with next_chain
                clean_rslt = Testcase._passvalue
                i = 0
                for i in range(len(next_chain)):
                    if i >= len(
                            fixture_chain) or next_chain[i]['name'] != fixture_chain[i]['name']:
                        break
                for j in range(len(fixture_chain) - 1, i - 1, -1):
                    fx = fixture_chain.pop()
                    if 'clean' in fx:
                        self.log.info(">>> Calling clean of %s" % fx['name'])
                        # try best to cleanup
                        try:
                            clean_rslt = fx['clean'](fx['case'])
                        except BaseException as e:
                            log.error("Error happens on cleaning up %s" %
                                      fx['name'])
                            log.exception("  Except: %s" % e)
                            clean_rslt = Testcase._abortvalue
                if clean_rslt not in Testcase.STATES:
                    # do not check unknown clean result
                    clean_rslt = Testcase._passvalue
                if clean_rslt != Testcase._passvalue:
                    self.result.failed_on.append(step_erro)
                    self.result.rcode = clean_rslt
                    log.error("Failed cleaning up testcase %s", self.name)
            except (KeyboardInterrupt, SystemExit) as e:
                log.error("User interrupted.")
                raise e
            except BaseException:
                log.exception(
                    "*** Exception happened when cleaning up testcase")
                self.result.failed_on.append(step_erro)
                # do not change test result
            self.result.end_sec = time.time()
            self.result.stage = Result.STAGE_FINISHED
            # print test summary
            self.report()
            # return result
            return self.result

    def report(self):
        """Summarize the running state and gives out a report.
        Called at the end of a testcase.
        """
        log.info("============================================================")
        log.info("== Testcase '%s' ", self.name)
        log.info("== Finished with result: %s", self.result.status)
        log.info("==    Start at: %s", self.result.start_time)
        log.info("==    End at: %s", self.result.end_time)
        log.info("==    Duration: %s", self.result.duration)
        log.info("==    Total steps: %d", self.result.step_count)
        log.info("==    Steps run: %d", self.result.step_run)
        if self.result.rcode != Testcase._passvalue:
            log.info("==    Failed on following steps:")
            for f in self.result.failed_on:
                log.info("    ==  %s: %s", f["step"], f["desc"])
        log.info("============================================================\n")

    def getResult(self):
        return self.result

    def _runStep(self, sid, steps):
        """Internal method to call a step

        :param sid: step id
        :param steps: a list of substeps
        :return: (result_code, description, [sub_step_results])
        """
        rcode = Testcase._passvalue
        rmsg = ""
        rlist = []
        log.info("=" * 20)
        log.info(">>>Step %s started<<<", sid)
        log.info("=" * 20)
        if len(steps) == 1:
            ss = getattr(self, steps[0])
            log.info(">>> %s", ss.__doc__)
            desc = ss.__doc__
            subr = StepResult(str(sid), desc)
            try:
                rcode = ss()
                if isinstance(rcode, tuple):
                    (subr.rcode, subr.error) = rcode
                    (rcode, rmsg) = rcode
                else:
                    subr.rcode = rcode
                    rmsg = desc
                # Silently Pass
                if rcode is None:
                    subr.rcode = rcode = Testcase._passvalue
            except AssertionError as e:
                _, _, tb = sys.exc_info()
                tb_info = traceback.extract_tb(tb)
                filename, line, func, text = tb_info[-1]
                rcode = subr.rcode = Testcase._failvalue
                rmsg = 'Assertion fail: {}'.format(text)
                if self._pause_on_fail:
                    pdb.pm()
            except Exception as e:
                _, _, tb = sys.exc_info()
                tb_info = traceback.extract_tb(tb)
                filename, line, func, text = tb_info[-1]
                log.exception("*** Exception happens with step %s", steps[0])
                traceback.print_tb(tb)
                rcode = subr.rcode = Testcase._abortvalue
                rmsg = subr.error = str(e)
                if self._pause_on_fail:
                    pdb.pm()
            finally:
                subr.end_sec = time.time()
                rlist.append(subr)
        else:
            threads = []
            desclist = []
            sub_results = {}
            for s in range(len(steps)):
                sub_num = "_".join(steps[s].split("_")[-2:])
                ss = getattr(self, steps[s])
                log.info(">>> >>>Sub step %s started<<< <<<", sub_num)
                log.info(">>> >>> %s", ss.__doc__)
                sub_results[steps[s]] = StepResult(sub_num, ss.__doc__)
                t = ChorusThread(target=ss, name=steps[s])
                threads.append(t)
                t.start()

            for t in threads:
                subr = t.join()
                result = sub_results[t.name]
                result.end_sec = time.time()
                log.info("Result for substep %s:", t.name)
                if subr["exception"] is not None:
                    etype, value, tb = subr["exception"]
                    if etype == AssertionError:
                        result.rcode = Testcase._failvalue
                        tb_info = traceback.extract_tb(tb)
                        filename, line, func, text = tb_info[-1]
                        log.error(
                            'Assertion fail for substep %s: %s', t.name, text)
                    else:
                        log.error(" *** Exception happens with step %s:",
                                  t.name, exc_info=subr["exception"])
                        result.rcode = Testcase.ABORT
                        result.error = str(subr["exception"])
                elif isinstance(subr["state"], tuple):
                    (result.rcode, result.error) = subr["state"]
                else:
                    if subr["state"] is None:
                        result.rcode = Testcase._passvalue
                    else:
                        result.rcode = subr["state"]

                if result.rcode not in Testcase.STATES:
                    log.warn(
                        "  Unknown test result, make sure you return a Testcase state for the step.")
                    result.rcode = Testcase.UNKNOWN
                    result.error = "Illegal return from substep, please check the code."
                log.info("  >>> >>>Sub step %s result: %s<<< <<<",
                         t.name, result.status)

                desclist.append("%s:%s" % (t.name, result.status))
                rlist.append(result)
                # return the larget(worst) result
                if result.rcode > rcode:
                    rcode = result.rcode
            rmsg = "; ".join(desclist)

        log.info(">>>Step %s result: %s<<<", sid, Testcase.STATES[rcode])
        return rcode, rmsg, rlist

    def getSteps(self):
        """Instance method of get steps, call `_getSteps` of class by default"""
        return self.__class__._getSteps()

    @classmethod
    def _getSteps(cls):
        """Collect all the test steps
        Test step should in format of 'step<id>[_subid]'
        This may be called several times, so it should be idempotent
        """
        log.debug("Getting test steps for {}...".format(cls.name))
        # inspect all methods
        all_method = inspect.getmembers(
            cls, predicate=lambda x: inspect.isfunction(x) or inspect.ismethod(x))
        hsteps = {}
        for m in all_method:
            # because all methods including inherited ones will be listed,
            # filter out the methods defined in this cls only
            if m[0] in cls.__dict__ and re.match(
                r'^%s\d+(_\d+)?$' %
                cls.METHOD_PREFIX,
                    m[0]):
                smark = m[0][len(cls.METHOD_PREFIX):].split("_")
                # master smark smark[0]
                log.debug("Adding step %s to testcase %s", m[0], cls)
                if len(smark) == 1:
                    sid = int(smark[0])
                    # all in list form to simplify the process
                    hsteps[sid] = [m[0]]
                elif len(smark) == 2:
                    sid = int(smark[0])
                    if sid in hsteps:
                        hsteps[sid].append(m[0])
                    else:
                        hsteps[sid] = [m[0]]
                else:
                    raise TestException(
                        "Step name not supported %s, %s" % (m[0], cls))
        if len(hsteps.keys()) == 0:
            raise TestException("No steps defined in testcase %s" % cls)
        log.debug("{} steps found(without sub steps)".format(len(hsteps)))
        log.debug("Get test steps for {} finished.".format(cls.name))
        return hsteps

    @classmethod
    def getUserSteps(cls):
        methods = []
        # init and clean
        if "init" in cls.__dict__:
            methods.append("init")
        if "clean" in cls.__dict__:
            methods.append("clean")
        # steps
        for sl in cls._getSteps().values():
            for s in sl:
                methods.append(s)
        return methods

    @classmethod
    def setBreak(cls, p):
        filename = inspect.getsourcefile(cls)
        # break on user steps
        for s in cls.getUserSteps():
            step = getattr(cls, s)
            _, lineno = inspect.getsourcelines(step)
            p.set_break(filename, lineno, funcname=s)

    @classmethod
    def getFixtureChain(cls):
        """Get the chain of fixtures from all ancestors"""
        mros = inspect.getmro(cls)
        chain = []
        if len(mros) > 2:
            for c in mros[:-2]:
                entry = {'name': c.__name__}
                if "init" in c.__dict__:
                    entry['init'] = getattr(c, 'init')
                if "clean" in c.__dict__:
                    entry['clean'] = getattr(c, 'clean')
                chain.insert(0, entry)
        return chain


class AbstractResult(object):
    """Abstract result class, provides basic time calculation and result conversion properties"""

    def __init__(
            self,
            rcode=Testcase._passvalue,
            start_sec=None,
            end_sec=None):
        self.rcode = rcode
        self.start_sec = start_sec or time.time()
        self.end_sec = end_sec or time.time()

    @property
    def status(self):
        """The descriptive status"""
        return Testcase.STATES[self.rcode]

    @property
    def start_time(self):
        """The descriptive start time"""
        return time.ctime(self.start_sec)

    @property
    def end_time(self):
        """The descriptive start time"""
        return time.ctime(self.end_sec)

    @property
    def duration(self):
        """The descriptive start time"""
        return datetime.timedelta(
            seconds=(int(self.end_sec) - int(self.start_sec)))

    @property
    def elapsed_sec(self):
        """The descriptive start time"""
        return int(self.end_sec) - int(self.start_sec)


class Result(AbstractResult):
    """Test result class"""
    STAGE_NOT_RUN = "Not started"
    STAGE_INIT = "Initialization"
    STAGE_STEP = "Running Steps"
    STAGE_CLEAN = "Cleaning up"
    STAGE_FINISHED = "Finished"

    def __init__(self, name,
                 step_count=0,
                 step_results=[],
                 rcode=Testcase._unvalue):
        """
        :type step_count: step count of testcase
        :param name: testcase name
        :param step_results: step result list [StepResult ...]
        :param rcode: result code
        """
        super(Result, self).__init__(rcode)
        self.name = name
        self.step_count = step_count
        self.step_results = step_results
        self.step_run = 0
        self.stage = Result.STAGE_NOT_RUN
        self.failed_on = []


class StepResult(AbstractResult):
    """Result of a step/substep"""

    def __init__(self, id, desc):
        super(StepResult, self).__init__()
        self.id = id
        self.desc = desc
        self.error = ""


class TestException(Exception):
    """Exception handling class for testcases"""

    def __init__(self, value):
        super(TestException, self).__init__()
        self.value = "Test Error due to: " + value
        log.exception("Test Error happens: %s!!", value)

    def __str__(self):
        return repr(self.value)
