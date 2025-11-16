from typing import Literal, Union, Iterator

from ..nodetypes import __pool__ as nodes
GeometryFilter = nodes['GeometryFilter']

import maya.cmds as m
import riggery.core as r


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

    #-------------------------------------|    Influence management

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