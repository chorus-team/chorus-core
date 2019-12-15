<div align="center">

![Chorus Core Logo](chorus_core_small.png)

# Chorus Core

</div>

## What is Chorus

**Chorus** is an felxible framework targets to network device test automation. It can be extended in many ways including testcase, device behaviour, control methods, topology representation etc.

**Chorus Core** is the core of the chorus framwork.

## Prerequisites

Chorus supports only Linux Platform. You need to install python, pip before install.

## Installation

### Source

```bash
$ git clone https://github.com/chorus-team/chorus-core.git
$ cd chorus-core
$ python setup.py install
```

### PYPI

```bash
$ pip install chorus-core
```

## Configuration Files

After installation, the configuration files will be placed under `sys.prefix+'/etc/chorus'`, i.e. '/usr/etc/chorus' or '/usr/local/etc/chorus' if not using virtualenv.

## Command Line

### chorus

The command line framework of chorus. Currently the following subcommands are supported:

- run
  Run a chorus script. Calls chorus_run directly.
- debug
  Debug a chorus script. Calls chorus_run with -D option.
- lastlog
  Show the latest chorus log file.

## Notes:

There are several kinds of files for Chorus testcase to run (check example folder in src):

1. testcase file, format python, define testcases which inherate from class Testcase.
2. topology file, format yaml, define the topologies, extension .topo.
3. suite file, define testcases and their parameters, used for batch regression. A suite file may have a topology file with the same prefix.
4. data file, format csv, define the testcase argument data in format of table.
