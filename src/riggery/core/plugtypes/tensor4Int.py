import maya.api.OpenMaya as om
from ..plugtypes import __pool__


class Tensor4Int(__pool__['Tensor4']):

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        fn = om.MFnNumericData()
        mobj = fn.create(om.MFnNumericData.k4Int)
        fn.setData(value)

        plug.setMObject(mobj)