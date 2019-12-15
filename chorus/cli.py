# -*-coding: utf-8-*-
#
# Copyright (c) 2019 Chorus Team.
#

"""
chorus command line management module
"""

import os
import subprocess
import argparse
from .repository import Repository
from . import chorus
from .log import log, logcls, get_log_files
from .config import Config


def main():
    """entry point of chorus command"""
    usage = """chorus command line
    chorus <subcommand> [options]
    Available subcommands:
        run: run chorus script
        debug: debug a chorus script
        lastlog: show the last Nth chorus log in current folder
        <module>: module specific commands
    """

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help='SUB COMMAND HELP')
    config = Config()

    # global parameters
    parser.add_argument(
        "-u",
        "--uuid",
        dest="global_uuid",
        default=str(
            os.getpid()),
        help="UUID of the test run, used to track the log file or for regression purpose")
    parser.add_argument(
        "-p",
        "--profile",
        dest="global_profile",
        action="store_true",
        help="Profiling the chorus command")

    for sub_cli in config.list_plugin_tags("cli"):
        cli_cls = config.get_plugin("cli", sub_cli)
        sub_parser = subparsers.add_parser(sub_cli, help=cli_cls.help)
        cli_cls.register(sub_parser)

    args = parser.parse_args()
    config.uuid = args.global_uuid

    if args.global_profile:
        # use cProfile for estimate the chorus profiling
        import cProfile as profile
        import pstats
        pr = profile.Profile()
        pr.enable()

    try:
        rslt = args.func(args)
    except AttributeError as e:
        parser.print_help()
        rslt = CLI.ERR_RUN
    except BaseException:
        log.exception("Error running chorus command:")
        rslt = CLI.ERR_EXP

    if args.global_profile:
        pr.disable()
        ps = pstats.Stats(pr).sort_stats('cumulative')
        ps.dump_stats(logcls.get().getLogPrefix() + ".profile")
        log.info("*************************")
        log.info("Profiling info:")
        ps.print_stats(".py:", 20)
        log.info("Use `chorus log --profile` to load the detailed data")
        log.info("*************************")

    return rslt


# The cli plugins
class CLI(object):
    """Cli plugin base class
    class attributes

    :cvar PASS: command passes
    :cvar ERR_RUN: Command fails on testcases
    :cvar ERR_EXP: Command fails on testcases exceptions
    :cvar ERR_ARG: command fails on arguments
    """
    help = "This is an base cli plugin, should not appear in cli"
    (PASS, ERR_RUN, ERR_EXP, ERR_ARG) = range(4)

    @classmethod
    def extend(cls, parser):
        """cli extending logic

        :param parser: the command line parser instance, refer to [argparse](https://docs.python.org/2/library/argparse.html#action)
        """
        # todo: change py2 to py3
        pass

    @classmethod
    def run(cls, args):
        """Command running logic"""
        pass

    @classmethod
    def register(cls, sub_parser):
        """Template method, no need to override"""
        cls.extend(sub_parser)
        sub_parser.set_defaults(func=cls.run)


# Basic implementation of chorus run command
class Run(CLI):
    """Basic chorus command: `chorus run`"""
    help = "Run chorus script"

    @classmethod
    def extend(cls, parser):
        """cli extention logic

        :param parser: the command line parser instance, refer to [argparse](https://docs.python.org/2/library/argparse.html#action)
        """
        parser.add_argument(
            "-p",
            "--testpath",
            dest="pathes",
            action="append",
            default=[],
            help="The path of test scripts (current folder by default), can occur multi times")
        parser.add_argument(
            "-s",
            "--testscript",
            dest="pathes",
            action="append",
            default=[],
            help="The testscript to run, can occur multi times")
        parser.add_argument(
            "-S",
            "--testsuite",
            dest="suite_files",
            action="append",
            default=[],
            help="The testsuite to run, can occur multi times")
        parser.add_argument(
            "-c",
            "--testcase",
            dest="testcase",
            action="append",
            default=[],
            help="The testcase to run, all testcases by default")
        parser.add_argument(
            "-t",
            "--topo-file",
            dest="topo_files",
            action="append",
            default=[],
            help="The topology file (suite file name plus .topo by default), can occur multi times")
        parser.add_argument("-d", "--data", dest="data_file",
                            help="The data file ")
        parser.add_argument(
            "--repo-uri",
            dest="repo_uri",
            default='.',
            help="The repository location where scripts are discovered")
        parser.add_argument(
            "--repo-type",
            dest="repo_type",
            default='local',
            help="The repository type, local file system by default")
        parser.add_argument(
            "-x",
            "--extra",
            dest="extra_params",
            action="append",
            default=[],
            help="Parameters used by cases, in format of \"k1=v1\". May occur multi times.")
        parser.add_argument("-D", "--debug", dest="debug", action="store_true",
                            help="Debug mode. Breaks on each custom step.")
        parser.add_argument(
            "-T",
            "--dryrun",
            dest="dryrun",
            action="store_true",
            help="Run testcase without really connect to devices. Useful for test script logic.")
        parser.add_argument(
            "-P",
            "--pause",
            dest="pause_on_fail",
            action="store_true",
            help="Enter debug mode when a step fails.")
        parser.add_argument(
            "--log-path",
            dest="log_path",
            default=".",
            help="Path for chorus log files(under foler log), current folder by default.")
        parser.add_argument(
            "-R",
            "--recursive",
            dest="recursive",
            action="store_true",
            help="Recursively search the test cases")
        parser.add_argument("pos_pathes", nargs="*", help="testscripts")

    @classmethod
    def run(cls, args):
        """Command running logic"""
        if args.repo_type == '?':
            rptypes = Repository.listTypes()
            print("Supported repository types:")
            for rp in rptypes:
                print("- %s" % rp)
            return CLI.ERR_ARG
        else:
            base_path = Repository.syncPath(
                type=args.repo_type, uri=args.repo_uri)

        if not args.topo_files and len(args.suite_files) == 0:
            print("Please specify topology files")
            return CLI.ERR_ARG

        if len(args.suite_files) > 0 and args.data_file:
            print("Data file will not take effect when suite file specifed")
            return CLI.ERR_ARG

        try:
            args.pathes += args.pos_pathes
            rslt = chorus.run(testcases=args.testcase,
                              pathes=args.pathes,
                              topo_files=args.topo_files,
                              data_file=args.data_file,
                              suite_files=args.suite_files,
                              extra_params=args.extra_params,
                              debug=args.debug,
                              dryrun=args.dryrun,
                              pause_on_fail=args.pause_on_fail,
                              base_path=base_path,
                              log_path=args.log_path,
                              recursive=args.recursive)
            if rslt:
                return CLI.PASS
            else:
                return CLI.ERR_RUN
        except BaseException:
            log.exception("Error running chorus script:")
            return CLI.ERR_EXP


class Debug(Run):
    """Debug class, inherates run with -D argument set by default"""
    help = "Debug chorus script"

    @classmethod
    def run(cls, args):
        """Command running logic"""
        # always set debug to true
        args.debug = True
        super(Debug, cls).run(args)


class Log(CLI):
    """Log viewing cli"""
    help = "Viewing chorus logs"

    @classmethod
    def extend(cls, parser):
        """cli extending logic

        :param parser: the command line parser instance, refer to [argparse](https://docs.python.org/2/library/argparse.html#action)
        """
        parser.add_argument("-l", "--list", dest="list", action="store_true",
                            help="List all chorus logs")
        parser.add_argument(
            "-p",
            "--path",
            dest="path",
            default=".",
            help="path where chorus scripts run, current path by default")
        parser.add_argument(
            "-e",
            "--expect-log",
            dest="expect",
            action="store_true",
            help="view expect log instead of script log")
        parser.add_argument("-a", "--all-log", dest="all", action="store_true",
                            help="view expect log and script log")
        parser.add_argument(
            "-n",
            dest="n",
            type=int,
            default=0,
            help="The last Nth log to view. The latest log (1) by default.")
        parser.add_argument(
            "-P",
            "--profile",
            dest="profile",
            action="store_true",
            help="Show the profile result.")

    @classmethod
    def run(cls, args):
        """Command running logic"""
        if not args.list and args.n == 0:
            args.n = 1

        # file extension
        extensions = [logcls.EXTENSION]
        if args.expect:
            extensions = ['.exp']
        elif args.profile:
            extensions = ['.profile']
        elif args.all:
            extensions = [logcls.EXTENSION, '.exp']

        files = get_log_files(args.path, extensions, args.n)
        if len(files) == 0:
            print("No log found!")
            return CLI.ERR_RUN
        elif args.list:
            for f in files:
                print("  %s" % f)
        else:
            if args.profile:
                import pstats
                ps = pstats.Stats(*files)
                ps.print_stats()
                ecode = 0
            else:
                # Do not open testcase log
                fs = []
                log_found = False
                if logcls.EXTENSION in extensions:
                    for f in files:
                        if f.endswith(logcls.EXTENSION):
                            # use the first log
                            if not log_found:
                                fs.append(f)
                                log_found = True
                        else:
                            fs.append(f)
                # Use subprocess to avoid shell injection
                ecode = subprocess.call(['vim -O --'] + fs, shell=False)
            if ecode == 0:
                return CLI.PASS
            else:
                return CLI.ERR_EXP
