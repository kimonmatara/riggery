import re
from typing import Optional, Union, Iterable

import maya.cmds as m
import maya.api.OpenMaya as om

from ..lib import names as _nm
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists, without_duplicates
from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..datatypes import __pool__ as data


class Cluster(nodes['WeightGeometryFilter']):

    #--------------------------------------|    Constructor

    @classmethod
    def create(
            cls,
            *geos,
            handle:Optional[Union[str, 'plugs.Matrix', 'nodes.Transform']]=None,
            createHandle:bool=True
    ):
        #-------------------|    Create node

        node = cls.createNode()

        #-------------------|    Connect geos

        connectionsMap = node._parseRequestedGeoConnections(*geos)

        if connectionsMap:
            for index, geo, components in connectionsMap:
                node.connectGeometry(index, geo)
                node.attr('geomMatrix')[index].set(
                    geo.toTransform().getMatrix(worldSpace=True)
                )
                if components:
                    tag = geo.createComponentTag(str(node),
                                                 components,
                                                 uniqueTagName=True)
                    node.setComponentTag(index, tag)

        #-------------------|    Resolve handle

        if handle is None:
            if createHandle:
                if connectionsMap:
                    points = []

                    for _, geo, components in connectionsMap:
                        if components:
                            for component in components:
                                compType = re.match(
                                    r"^.*?\.(vtx|e|f|cv|pt).*$",
                                    component
                                ).group(1)

                                if compType == 'e':
                                    flat = m.ls(m.polyListComponentConversion(
                                        component,
                                        fromEdge=True,
                                        toVertex=True
                                    ), flatten=True)

                                elif compType == 'f':
                                    flat = m.ls(m.polyListComponentConversion(
                                        component,
                                        fromFace=True,
                                        toVertex=True
                                    ), flatten=True)

                                else:
                                    flat = m.ls(component, flatten=True)
                                points += [
                                    data['Point'](m.pointPosition(x, w=True))
                                    for x in flat
                                ]
                        else:
                            points.append(geo.toTransform().attr('center')())

                    point = points[0].center(*points[1:])
                else:
                    point = data['Point']()

                matrix = point.asTranslateMatrix()
                handle = nodes['Transform'].create(
                    name=node._getDefaultHandleTransformName(),
                    matrix=matrix
                )
                handleShape = nodes['ClusterHandle'].createNode(parent=handle)

                handleShape.attr('clusterTransforms'
                                 )[0] >> node.attr('clusterXforms')

                handle.attr('wm') >> node.attr('matrix')
                node.updateOffset()
        else:
            handle = Elem(handle)

            if isinstance(handle, plugs['Matrix']):
                handle >> node.attr('matrix')

            elif isinstance(handle, nodes['Transform']):
                handle.attr('wm') >> node.attr('matrix')

            else:
                raise TypeError("expected transform or matrix")

            node.updateOffset()

        return node

    #--------------------------------------|    Partial builds

    def _getDefaultHandleTransformName(self) -> tuple[str, str]:
        _self = str(self)
        mt = re.match(r"^(.*?)_"+self.__typesuffix__+r"$", _self)

        if mt:
            basename = mt.group(1)
            return "{}_{}".format(basename,
                                  nodes['ClusterHandle'].__typesuffix__)

        return "{}Handle".format(_self)

    #--------------------------------------|    Offset management

    def updateOffset(self):
        self.attr('bindPreMatrix').set(self.attr('matrix')().inverse())
        return self