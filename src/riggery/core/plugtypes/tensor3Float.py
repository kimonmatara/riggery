import maya.api.OpenMaya as om
from ..plugtypes import __pool__


class Tensor3Float(__pool__['Tensor3']):

    #-----------------------------------------|    Set

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        fn = om.MFnNumericData()
        mobj = fn.create(om.MFnNumericData.k3Double)
        fn.setData(value)

        plug.setMObject(mobj)