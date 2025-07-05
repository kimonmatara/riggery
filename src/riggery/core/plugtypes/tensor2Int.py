import maya.api.OpenMaya as om
from ..plugtypes import __pool__


class Tensor2Int(__pool__['Tensor2']):

   #-----------------------------------------|    Set

   def _setValue(self, value, **_):
      plug = self.__apimplug__()
      if plug.isArray:
         plug = plug.elementByLogicalIndex(0)

      fn = om.MFnNumericData()
      mobj = fn.create(om.MFnNumericData.k2Int)
      fn.setData(value)

      plug.setMObject(mobj)