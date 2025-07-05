from riggery.general.numbers import floatrange, subdivide_floats
from ..lib import nurbsutil as _nut
from ..lib import names as _nm
from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes


class BezierCurve(plugs['NurbsCurve']):

    def numAnchors(self) -> int:
        """
        This is a soft-only inspection.

        :return: The number of Bezier anchors on this curve.
        """
        return _nut.numCVsToNumAnchors(self.numCVs())

    def paramAtAnchor(self, anchorIndex:int) -> float:
        """
        This is a soft-only inspection.

        :param anchorIndex: the index of the anchor at which to sample a U
            parameter
        :return: The U parameter at the center of the specified Bezier anchor.
        """
        return self.knots()[::3][anchorIndex]

    def subdivide(self, iterations:int=1):
        """
        Subdivides this Bezier curve, adding anchors between existing anchors.
        Insertions parameters are calculated once (i.e. non-dynamically); not
        suitable for outputs with changing curve topology.

        :param iterations: the number of subdivisions to apply; defaults to 1
        :return: The subdivided Bezier curve.
        """
        origParams = [self.paramAtAnchor(anchorIndex)
                      for anchorIndex in range(self.numAnchors())]
        newParams = subdivide_floats(origParams, iterations, inclusive=False)

        with _nm.Name('subdivide'):
            node = nodes['InsertKnotCurve'].createNode()
            self >> node.attr('inputCurve')
            node.setAttrs(insertBetween=False, addKnots=True)
            for i, param in enumerate(newParams):
                node.attr('parameter')[i].set(param)
                node.attr('numberOfKnots')[i].set(1)

        return node.attr('outputCurve')