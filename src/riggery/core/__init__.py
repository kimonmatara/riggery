from importlib import reload
from .elem import Elem
from .lib.names import Name
from .lib.namespaces import Namespace
from .lib.controls import createControl, createControlStack, ShapeScale
from .lib.mixedmode import createOrthoMatrix, createScaleMatrix
from .lib.skel import Chain

from .nodetypes import __pool__ as nodes
from .plugtypes import __pool__ as plugs
from .datatypes import __pool__ as data

from . import cmds as _cmds

import riggery

if getattr(riggery, '__core_loaded__', False):
    nodes.rehash()
    plugs.rehash()
    data.rehash()
    reload(_cmds)

    print("Rehashed pools and commands.")
else:
    riggery.__core_loaded__ = True

Node = nodes['DependNode']
DagNode = nodes['DagNode']
Attribute = Plug = plugs['Attribute']

def __getattr__(item:str):
    obj = getattr(_cmds, item)
    globals()[item] = obj
    return obj