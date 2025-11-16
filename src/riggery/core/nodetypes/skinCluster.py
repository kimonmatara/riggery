from pathlib import Path
from typing import Literal, Union, Iterator, Optional

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m

import riggery.core as r
from riggery.general.iterables import expand_tuples_lists
from riggery.general.functions import short


class SkinCluster(GeometryFilter):

    #-------------------------------------|    Serialization

    @classmethod
    def createFromMacro(cls, macro:dict, **overrides) -> 'SkinCluster':
        macro = macro.copy()
        macro.update(overrides)

        shape = macro['geometry'][0]
        influences = macro['influence']

        buildArgs = influences + [shape]
        buildKwargs = {k: macro[k] for k in [
            'bindMethod', 'maximumInfluences', 'obeyMaxInfluences',
            'skinMethod', 'weightDistribution', 'name']}

        buildKwargs['toSelectedBones'] = True

        skin = r.skinCluster(*buildArgs, **buildKwargs)[0]

        config = {k: macro[k] for k in
            ['deformUserNormals', 'useComponents',
             'envelope', 'dqsSupportNonRigid']}

        for k, v in config.items():
            skin.attr(k).set(v)

        for attrName, attrInfo in macro['dqsScale'].items():
            input = attrInfo['input']
            value = attrInfo['value']
            plug = skin.attr(attrName)

            if input:
                try:
                    r.connectAttr(input, plug)

                except RuntimeError:
                    r.warning(
                        ("Couldn't connect {} into {}; "+
                         "setting the value instead.").format(input, plug)
                    )

                    plug.set(value)
            else:
                plug.set(value)

        return skin

    def macro(self) -> dict:
        macro = super().macro()
        _self = macro['name']
        influences = list(map(str, self.influences))

        if influences:
            macro['influence'] = influences

        for flag in ['bindMethod',
                     'maximumInfluences',
                     'obeyMaxInfluences',
                     'skinMethod',
                     'weightDistribution']:
            macro[flag] = m.skinCluster(_self, q=True, **{flag:True})

        macro['geometry'] = [str(next(self.shapes))]

        for attrName in ['deformUserNormals',
                         'useComponents',
                         'envelope',
                         'dqsSupportNonRigid']:
            macro[attrName] = self.attr(attrName).get()

        macro['dqsScale'] = dqs = {}

        wlist = [self.attr('dqsScale')]
        wlist += list(wlist[0].children)

        for plug in wlist:
            val = plug()
            inputs = plug.inputs(plugs=True)

            if inputs:
                input = str(inputs[0])
            else:
                input = None

            dqs[plug.attrName()] = {'value': val, 'input': input}

        return macro

    #-------------------------------------|    Influences

    def getInfluence(self) -> list:
        """
        :return: The list of influences driving this skin cluster.
        """
        return list(self.influences)

    @property
    def influences(self) -> Iterator['nodes.Joint']:
        out = m.skinCluster(str(self), q=True, influence=True)

        if out:
            for x in out:
                yield nodes['DependNode'](x)

    #-------------------------------------|    Weights

    def _padBlendWeights(self):
        # Set any missing array indices on ``.blendWeights`` to 0.0. This is a
        # workaround for the following bug:
        #
        # When the ``.blendWeights`` array is sparsely populated, dumping and
        # reloading the attribute via :func:`deformerWeights` results in wrong
        # index mapping.

        plug = self.attr('blendWeights')
        indices = plug.indices()
        shape = next(self.shapes)
        numVertices = shape.numVertices()

        missingIndices = list(sorted(set(range(numVertices))-set(indices)))

        _plug = str(plug)

        for index in missingIndices:
            m.setAttr('{}[{}]'.format(_plug, index), 0.0)

        return missingIndices

    @short(
        remap='r',
        vertexConnections='vc',
        weightTolerance='wt',
        weightPrecision='wp',
        shape='sh',
        attribute='at',
        defaultValue='dv'
    )
    def dumpWeights(
            self,
            filepath:Union[str, Path],
            shape:Optional[Union[
                str,
                list[str],
                'nodes.DeformableShape',
                list['nodes.DeformableShape']]]=None,
            remap:Optional[str]=None,
            vertexConnections:bool=False,
            weightPrecision:int=3,
            weightTolerance:float=0.001,
            attribute:Optional[Union[
                str,
                list[str],
                'plugs.Attribute',
                list['plugs.Attribute']
            ]]=None,
            defaultValue:Optional[Union[int, float]]=None,
            includeBlendWeights:bool=True):
        """
        Overrides
        :meth:`riggery.core.nodetypes.geometryFilter.GeometryFilter.dumpWeights`
        to include DQ blend weights by default, and to work around this bug:

        When the ``.blendWeights`` array on a skinCluster is sparsely populated
        (as is typically the case), dumping and reloading it via
        ``deformerWeights(at='blendWeights')`` results in a wrongindex mapping.
        """
        kwargs = {}

        if includeBlendWeights:
            if attribute is None:
                attribute = []
            else:
                attribute = list(expand_tuples_lists(attribute))

            attribute.append('blendWeights')
            indicesToRemove = self._padBlendWeights()

            kwargs['at'] = attribute

        nodes['GeometryFilter'].dumpWeights(self,
                                            filepath,
                                            sh=shape,
                                            r=remap,
                                            vc=vertexConnections,
                                            wp=weightPrecision,
                                            wt=weightTolerance,
                                            dv=defaultValue,
                                            **kwargs)

        if includeBlendWeights:
            _plug = '{}.blendWeights'.format(self)

            for index in indicesToRemove:
                m.removeMultiInstance('{}[{}]'.format(_plug, index))

        return self

