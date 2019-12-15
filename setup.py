#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

try:
    import multiprocessing  # noqa
except ImportError:
    pass

setup(
    setup_requires=['pbr>=2.0.0'],
    pbr=True)
