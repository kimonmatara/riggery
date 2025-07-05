import maya.api.OpenMaya as om
from riggery.general.functions import short
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes


class String(plugs['Attribute']):

   #-----------------------------------------|    Get

   def _getValue(self, **_):
      plug = self.__apimplug__()
      if plug.isArray:
         plug = plug.elementByLogicalIndex(0)
      return plug.asString()

   #-----------------------------------------|    Set

   def _setValue(self, value, **_):
      plug = self.__apimplug__()
      if plug.isArray:
         plug = plug.elementByLogicalIndex(0)
      plug.setString(value)

   #-----------------------------------------|    Default value

   def getDefaultValue(self) -> str:
      out = super().getDefaultValue()
      if out.isNull():
         return ''
      return om.MFnStringData(out).string()

   def setDefaultValue(self, value:str):
      fn = om.MFnStringData()
      mobj = fn.create()
      fn.set(value)
      return super().setDefaultValue(mobj)

   #-----------------------------------------|    Connections

   def __rshift__(self, other):
      plugs['Attribute'](other).set(self)

   def __rrshift__(self, other):
      self.setValue(other)

   def put(self, other, *_, **__):
      self.setValue(other)
      return self