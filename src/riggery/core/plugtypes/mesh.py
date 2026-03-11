from typing import Optional, Union
import maya.api.OpenMaya as om
import maya.cmds as m

from riggery.general.functions import resolve_flags, short

from ..plugtypes import __pool__ as plugs
from ..nodetypes import __pool__ as nodes
from ..elem import Elem


class Mesh(plugs['Geometry']):

    __data_mfn_type__ = om.MFnMesh

    #--------------------------------------|    Data queries

    def _getData(self) -> om.MObject:
        plug = self._getSamplingPlug()
        handle = plug.asMDataHandle()
        out = handle.asMeshTransformed()
        plug.destructHandle(handle)
        return out

    #--------------------------------------|    Edits

    def separate(self) -> list:
        """
        Separates this mesh and returns the outputs in a list.
        """
        shape = self.node()

        if shape.nodeType() == 'mesh':
            wasInterm = shape.attr('intermediateObject').get()
        else:
            self = self.newInput()
            shape = self.node()
            wasInterm = True

        if wasInterm:
            shape.attr('intermediateObject').set(False)

        origParent = shape.parent

        result = m.polySeparate(str(shape))
        _newPolyXforms, _node = result[:-1], result[-1]
        node = Elem(_node)
        newPolyXforms = list(map(Elem, _newPolyXforms))
        insertedXform = shape.parent

        outputs = [xform.shape.input.inputs(plugs=True)[0] \
                   for xform in newPolyXforms]

        for output in outputs:
            output.node().lock()

        reparentedShapes = list(insertedXform.iterShapes())

        if reparentedShapes:
            m.parent(list(map(str, reparentedShapes)),
                     str(origParent),
                     r=True, shape=True)

        m.delete(_newPolyXforms, str(insertedXform))

        if not wasInterm:
            shape.attr('intermediateObject').set(False)

        outputPlug = node.attr('output')
        outputPlug.evaluate()

        for output in outputs:
            output.node().unlock()

        return [outputPlug[index].outputs(type='groupParts'
                                          )[0].attr('outputGeometry')
                for index in outputPlug.indices()]

    #--------------------------------------|    Transfers

    @short(uvSets='uv',
           vertexColor='vc',
           vertices='v')
    def polyTransferFrom(self,
                         otherPlug:'plugs.Mesh',
                         verts:Optional[bool]=None,
                         uvSets:Optional[bool]=None,
                         vertexColor:Optional[bool]=None) -> 'Mesh':
        """
        Transfers attributes from *otherPlug* and returns the result. Uses the
        older ``polyTransfer`` node. Flags are evaluated by omission.
        """
        verts, uvSets, vertexColor = resolve_flags(verts, uvSets, vertexColor)
        node = nodes['PolyTransfer'].createNode()

        for k, v in zip(('vertices', 'uvSets', 'vertexColor'),
                        (verts, uvSets, vertexColor)):
            node.attr(k).set(v)

        self >> node.attr('inputPolymesh')
        otherPlug >> node.attr('otherPoly')

        return node.attr('output')