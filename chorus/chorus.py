# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""The main program"""
import os
from . import testsuite
from .topo import Topo
from .log import setLogPath


def run(testcases=[],
        pathes=["."],
        topo_files=[],
        data_file="",
        suite_files=[],
        extra_params=[],
        per_case_params=[],
        base_path='.',
        debug=False,
        dryrun=False,
        pause_on_fail=False,
        log_path='.',
        recursive=False):
    """Run a test
    :param testcases: the testcases to run, by default is to run all found testcases
    :param pathes: the path or script where to find testcases, by default is current path and syspath
    :param topo_files: the topology files used by testcases
    :param data_file: data file, with which user runs testcase in data driven mode
    :param suite_files: test suite file, which contains a set of testcases, one for each line
    :param extra_params: parameters used by testcases
    :param per_case_params: specify parameters for each testcase, the length should be 0 or the same as testcases. A list of dict.
    :param base_path: the relative base path where all files are searched, current path by default
    :param debug: whether to debug the testcase(breaks on user steps), default False
    :param dryrun: run testcase with dummy connection, default False
    :param pause_on_fail: enter pdb when testcase fails, default False
    :param log_path: Path for chorus log files, '.' by default
    :param recursive: recursive search the testcases from the pathes, default False

    :rtype: bool
    :return: the result of the case
    """
    # set log path
    setLogPath(log_path)
    # testcase definitions
    if not pathes:
        pathes = ["."]
    suite = testsuite.Testsuite(
        pathes, base_path=base_path, recursive=recursive)
    # extra arguments
    test_params = {}
    for pair in extra_params:
        p = pair.split('=')
        test_params[p[0]] = p[1]
    # find all topo files
    for t in set(topo_files):
        Topo.addTopo(os.path.join(base_path, t))
    # Load testcases
    if len(suite_files) > 0:
        # suite files
        if len(topo_files) == 0:
            for sfile in suite_files:
                tfile = os.path.splitext(sfile)[0] + '.topo'
                topo_files.append(tfile)
            for t in set(topo_files):
                Topo.addTopo(os.path.join(base_path, t))
        for s in set(suite_files):
            suite.loadSuiteFile(s, test_params)
    elif data_file:
        # data file
        suite.loadDataFile(data_file, testcases, test_params)
    else:
        # default testcase run
        suite.loadTestcaseReg(testcases, test_params, per_case_params)

    # 3. run the case
    if debug:
        import pdb
        p = pdb.Pdb(skip=['pdb.*', 'dbd.*'])
        for case in suite.cases:
            case["t_case_class"].setBreak(p)
        mark = "*" * 60
        print(mark)
        print("Entering chorus Debug Mode...")
        print("  You are now in pdb shell.")
        print("  Press 'c' to continue to your testcase steps.")
        print(mark)
        return p.run('suite.run(dryrun, pause_on_fail)', globals(), locals())
    else:
        return suite.run(dryrun, pause_on_fail)
