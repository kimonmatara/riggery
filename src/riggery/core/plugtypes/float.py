from typing import Optional

import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import short
from ..plugtypes import __pool__
from ..nodetypes import __pool__ as nodes


class Float(__pool__['Number']):

    #-----------------------------------------|    Get

    def _getValue(self, *, frame=None, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)

        kwargs = {}
        if frame is not None:
            kwargs['context'] = om.MDGContext(
                om.MTime(frame, unit=om.MTime.uiUnit())
            )
        return plug.asDouble(**kwargs)

    #-----------------------------------------|    Set

    def _setValue(self, value, **_):
        plug = self.__apimplug__()
        if plug.isArray:
            plug = plug.elementByLogicalIndex(0)
        plug.setDouble(value)

    #-----------------------------------------|    Channel limits

    def getMinLimit(self) -> Optional[float]:
        """
        Only valid on transform channels. Returns the min limit, or ``None``
        if the min limit is inactive.
        """
        _node = str(self.node())
        n = self.shortName()
        enabled = m.transformLimits(_node, q=True,
                                    **{'e{}'.format(n):True})[0]
        if enabled:
            return m.transformLimits(_node, q=True, **{n:True})[0]

    def setMinLimit(self, limit:Optional[float]):
        """
        Only valid on transform channels. Sets the min limit. Pass ``None``
        to deactivate the min limit.
        """
        _node = str(self.node())
        n = self.shortName()
        enableds = m.transformLimits(_node, q=True,
                                    **{'e{}'.format(n):True})
        values = m.transformLimits(_node, q=True,
                                    **{'{}'.format(n):True})

        if limit is None:
            enableds[0] = False
        else:
            enableds[0] = True
            values[0] = limit

        m.transformLimits(_node, **{'e{}'.format(n): enableds, n: values})

    def clearMinLimit(self):
        """
        Only valid on transform channels. Deactivates the min limit.
        """
        self.setMinLimit(None)

    minLimit = property(getMinLimit, setMinLimit, clearMinLimit)

    def getMaxLimit(self) -> Optional[float]:
        """
        Only valid on transform channels. Returns the max limit, or ``None``
        if the max limit is inactive.
        """
        _node = str(self.node())
        n = self.shortName()
        enabled = m.transformLimits(_node, q=True, **{'e{}'.format(n):True})[1]
        if enabled:
            return m.transformLimits(_node, q=True, **{n:True})[1]

    def setMaxLimit(self, limit:Optional[float]):
        """
        Only valid on transform channels. Sets the max limit. Pass ``None``
        to deactivate the max limit.
        """
        _node = str(self.node())
        n = self.shortName()
        enableds = m.transformLimits(_node, q=True, **{'e{}'.format(n):True})
        values = m.transformLimits(_node, q=True, **{'{}'.format(n):True})

        if limit is None:
            enableds[1] = False
        else:
            enableds[1] = True
            values[1] = limit

        m.transformLimits(_node, **{'e{}'.format(n): enableds, n: values})

    def clearMaxLimit(self):
        """
        Only valid on transform channels. Deactivates the max limit.
        """
        self.setMaxLimit(None)

    maxLimit = property(getMaxLimit, setMaxLimit, clearMaxLimit)