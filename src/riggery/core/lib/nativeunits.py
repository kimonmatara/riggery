"""Tools to enforce Maya native units."""

from functools import wraps

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.internal.typeutil import SingletonMeta


class NativeUnits(metaclass=SingletonMeta):

    __depth__ = 0
    __user_linear__ = None
    __user_angular__ = None
    __track_changes__ = True
    __callbacks__ = None

    #----------------------------------|    Init

    def __init__(self):
        self.installCallbacks()

    #----------------------------------|    Enter / exit

    def __enter__(self):
        self.__depth__ += 1
        if self.__depth__ == 1:
            self._enter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__depth__ -= 1
        if self.__depth__ == 0:
            self._exit()
        return False

    def _enter(self):
        self._gridKwargs = {flag:m.grid(query=True, **{flag:True}) \
                            for flag in ['divisions', 'size', 'spacing']}
        NativeUnits.__user_linear__ = om.MDistance.uiUnit()
        NativeUnits.__user_angular__ = om.MAngle.uiUnit()

        om.MDistance.setUIUnit(om.MDistance.kCentimeters)
        om.MAngle.setUIUnit(om.MAngle.kRadians)
        NativeUnits.__track_changes__ = True

    def _exit(self):
        NativeUnits.__track_changes__ = False
        om.MDistance.setUIUnit(self.__user_linear__)
        om.MAngle.setUIUnit(self.__user_angular__)

        # Restore grid display settings
        m.grid(**self._gridKwargs)

    #----------------------------------|    Callback install / uninstall

    @staticmethod
    def installCallbacks():
        NativeUnits.__callbacks__ = [
            om.MSceneMessage.addCallback(om.MSceneMessage.kAfterNew,
                                         NativeUnits.afterNewCb),
            om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen,
                                         NativeUnits.afterOpenCb),
            om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeSave,
                                         NativeUnits.beforeSaveCb),
            om.MSceneMessage.addCallback(om.MSceneMessage.kAfterSave,
                                         NativeUnits.afterSaveCb),
            om.MEventMessage.addEventCallback('linearUnitChanged',
                                              NativeUnits.linearUnitChangedCb),
            om.MEventMessage.addEventCallback('angularUnitChanged',
                                              NativeUnits.angularUnitChangedCb)
        ]

    @staticmethod
    def uninstallCallbacks():
        for callback in NativeUnits.__callbacks__:
            om.MMessage.removeCallback(callback)
        NativeUnits.__callbacks__ = []

    #----------------------------------|    Internal callbacks

    @staticmethod
    def afterOpenCb(*_):
        if NativeUnits.__depth__ > 0:
            NativeUnits.__user_linear__ = om.MDistance.uiUnit()
            NativeUnits.__user_angular__ = om.MAngle.uiUnit()

            NativeUnits.__track_changes__ = False
            om.MDistance.setUIUnit(om.MDistance.kCentimeters)
            om.MAngle.setUIUnit(om.MAngle.kRadians)
            NativeUnits.__track_changes__ = True

    @staticmethod
    def afterNewCb(*_):
        if NativeUnits.__depth__ > 0:
            NativeUnits.__user_linear__ = om.MDistance.uiUnit()
            NativeUnits.__user_angular__ = om.MAngle.uiUnit()

            NativeUnits.__track_changes__ = False
            om.MDistance.setUIUnit(om.MDistance.kCentimeters)
            om.MAngle.setUIUnit(om.MAngle.kRadians)
            NativeUnits.__track_changes__ = True

    @staticmethod
    def beforeSaveCb(*_):
        if NativeUnits.__depth__ > 0:
            NativeUnits.__track_changes__ = False
            om.MDistance.setUIUnit(NativeUnits.__user_linear__)
            om.MAngle.setUIUnit(NativeUnits.__user_angular__)
            NativeUnits.__track_changes__ = True

    @staticmethod
    def afterSaveCb(*_):
        if NativeUnits.__depth__ > 0:
            NativeUnits.__track_changes__ = False
            om.MDistance.setUIUnit(om.MDistance.kCentimeters)
            om.MAngle.setUIUnit(om.MAngle.kRadians)
            NativeUnits.__track_changes__ = True

    @staticmethod
    def linearUnitChangedCb(*_):
        if NativeUnits.__depth__ > 0:
            if NativeUnits.__track_changes__:
                NativeUnits.__user_linear__ = om.MDistance.uiUnit()

    @staticmethod
    def angularUnitChangedCb(*_):
        if NativeUnits.__depth__ > 0:
            if NativeUnits.__track_changes__:
                NativeUnits.__user_angular__ = om.MAngle.uiUnit()

def nativeunits(f):
    """
    Wrapper version of :class:`NativeUnits`.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        with NativeUnits():
            result = f(*args, **kwargs)
        return result
    return wrapper