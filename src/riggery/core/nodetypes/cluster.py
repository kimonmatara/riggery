import re
from typing import Optional, Union

import maya.cmds as m
import maya.api.OpenMaya as om

from ..lib import names as _nm
from riggery.general.functions import short
from riggery.general.iterables import expand_tuples_lists
from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs


class Cluster(nodes['WeightGeometryFilter']):

    #--------------------------------------|    Constructor(s)

    @classmethod
    @short(name='n', handle='h')
    def create(cls, *items, name=None, handle=None):
        """
        :param \*items: components or geometries for the cluster to deform
        :param name\n: an optional name override for the cluster node; defaults
            to block naming
        :param handle/h: an existing transform to use as the cluster handle;
            this can also be a matrix output, in which case no DAG handle will
            be used at all; if omitted, a new handle is created
        """
        kwargs = {}
        if handle:
            if isinstance(Elem(handle), plugs['Matrix']):
                return cls._createFromMatrixOutput(handle, *items, name=name)
            handle = str(handle)
            kwargs['weightedNode'] = (handle, handle)
            kwargs['bindState'] = True

        items = map(str, expand_tuples_lists(*items))
        node, outHandle = map(nodes['DependNode'], m.cluster(*items, **kwargs))

        if name:
            node.name = name
            if not handle:
                outHandle.name = f"{name}Handle"
        else:
            name = _nm.Name.evaluate()
            if name:
                node.name = "{}_{}".format(name, _nm.TYPESUFFIXES['cluster'])
            if not handle:
                outHandle.name = "{}_{}".format(
                    name,
                    _nm.TYPESUFFIXES['clusterHandle']
                )
        return node

    @classmethod
    @short(name='n', handle='h')
    def _createFromMatrixOutput(cls, matrixOutput, *items, name=None):
        matrixOutput = plugs['Attribute'](matrixOutput)

        node, outHandle = map(nodes['DependNode'], m.cluster(*items))
        node.lock()
        m.delete(str(outHandle))
        node.unlock()

        matrixOutput >> node.attr('matrix')
        node.attr('bindPreMatrix').set(matrixOutput().inverse())

        if name:
            node.name = name
        else:
            name = _nm.Name.evaluate()
            if name:
                node.name = "{}_{}".format(name, _nm.TYPESUFFIXES['cluster'])
        return node