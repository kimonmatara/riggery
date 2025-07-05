"""
Defines a utility plug-in command, and supporting functions, to implement
undo / redo for pure-API operations that aren't tracked by Maya's undo
mechanism.

To use, import this module, call :func:`install` to install the plug-in,
and then call :func:`run`, passing it a callable for the 'doing' and one for
the 'undoing'.

Simple example:

.. code-block:: python

    import riggery.internal.apirunner as _ar
    import maya.api.OpenMaya as om
    _ar.install()

    mod = om.MDGModifier()
    mod.createNode('skinCluster')

    result = _ar.run(mod.doIt, mod.undoIt)
"""
from typing import Callable
import riggery
import os
import maya.api.OpenMaya as om
import maya.cmds as m

riggery.__apireturn__ = None

def maya_useNewAPI():
    pass

class JournalledRunner(om.MPxCommand):
    """
    The plug-in command should not be run directly, it's only used as a
    wrapper. Use :func:`run` instead.
    """
    kPluginCmdName = 'journalledRunner'

    @staticmethod
    def cmdCreator():
        return JournalledRunner()

    def doIt(self, _):
        riggery.__apireturn__ = None
        doFunc, undoFunc = riggery.__apiundoinbox__
        riggery.__apiundoinbox__ = None

        self._funcs = doFunc, undoFunc
        riggery.__apireturn__ = doFunc()

    def undoIt(self):
        self._funcs[1]()

    def redoIt(self):
        self._funcs[0]()

    def isUndoable(self):
        return True

def initializePlugin(plugin):
    pluginFn = om.MFnPlugin(plugin)
    pluginFn.registerCommand('journalledRunner',
                             JournalledRunner.cmdCreator)

def uninitializePlugin(plugin):
    pluginFn = om.MFnPlugin(plugin)
    pluginFn.deregisterCommand('journalledRunner')

def install():
    m.loadPlugin(__file__.replace('.pyc', '.py'), quiet=True)

def uninstall():
    m.flushUndo()
    m.unloadPlugin(os.path.basename(__file__.replace('.pyc', '.py')))

def run(doFunc:Callable, undoFunc:Callable):
    """
    .. warning::

        Neither doFunc nor undoFunc should contain any undoable calls, i.e.
        they should *entirely* comprise undo-blind API calls.

    :param doFunc: the 'doing' function
    :param undoFunc: the 'undoing' function
    """
    riggery.__apiundoinbox__ = doFunc, undoFunc
    m.journalledRunner()

    return riggery.__apireturn__

# The following is here purely as a proof-of-concept, but should probably be
# avoided unless requested, since class instantiation is significantly slower
# than simple function calls.

# class PureApiActionMeta(type):
#
#     def __call__(cls, *args, **kwargs):
#         inst = cls.__new__(cls)
#         return run(partial(inst.doIt, *args, **kwargs), inst.undoIt)
#
#     def __new__(meta, clsname, bases, dct):
#         try:
#             doIt = dct['doIt']
#         except KeyError:
#             return super().__new__(meta, clsname, bases, dct)
#
#         doc = inspect.getdoc(doIt)
#         if doc:
#             dct['__doc__'] = doc
#
#         cls = super().__new__(meta, clsname, bases, dct)
#
#         signature = inspect.signature(doIt)
#         parameters = list(signature.parameters.values())[1:]
#         signature = signature.replace(parameters=parameters)
#
#         cls.__signature__ = signature
#         return cls
#
# class PureApiAction(metaclass=PureApiActionMeta):
#     """
#     How to use
#     ----------
#
#     -   Subclass, give the subclass a lowercase name that looks like a command
#     -   Implement ``doIt()``, give it a meaningful signature and return value
#     -   Implement ``undoIt()``
#
#     .. warning::
#
#         Neither ``doIt()`` nor ``undoIt()`` can contain any Maya commands,
#         i.e. everything in there must be pure, undo-blind API calls.
#
#     That's it. Just call the class object itself as if it were a function.
#     """
#
#     def doIt(self, *args, **kwargs):
#         raise NotImplementedError
#
#     def undoIt(self):
#         raise NotImplementedError