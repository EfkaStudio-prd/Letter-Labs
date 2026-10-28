"""lettergcode - a clean-room G-code generator for the ZCCAD / S528 3D letter printer.

Reconstructed from S528\\GcodePara.ini plus the IL of OutPutG.dll and verified
against S528\\temp.gcode.  Pure standard library, no third-party packages.
"""
from .params import Params          # noqa: F401
from .job import Job, generate      # noqa: F401

__all__ = ["Params", "Job", "generate"]
