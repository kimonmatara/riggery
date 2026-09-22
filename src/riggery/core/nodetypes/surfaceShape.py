from riggery.general.iterables import without_duplicates
from typing import Iterator, Literal
from ..nodetypes import __pool__ as nodes
import maya.cmds as m

def _iterSurfaceShapes(source):
    source = nodes['DependNode'](source)
    if isinstance(source, nodes['Transform']):
        for shape in source.shapes:
            if shape.isIntermediate():
                continue
            if isinstance(shape, nodes['SurfaceShape']):
                yield shape
    elif isinstance(source, nodes['SurfaceShape']):
        yield source

class SurfaceShape(nodes['ControlPoint']):

    def assignDefaultShader(self):
        m.sets(str(self), fe='initialShadingGroup')
        return self

    def iterShadingGroups(self) -> Iterator['nodes.ShadingEngine']:
        visited = set()

        for instObjGroup in self.attr('instObjGroups'):
            for sg in instObjGroup.iterOutputs(type='shadingEngine'):
                if sg not in visited:
                    visited.add(sg)
                    yield sg

            for objectGroup in instObjGroup.attr('objectGroups'):
                for sg in objectGroup.iterOutputs(type='shadingEngine'):
                    if sg not in visited:
                        visited.add(sg)
                        yield sg

        for compInstObjGroup in self.attr('compInstObjGroups'):
            for compObjectGroup in compInstObjGroup.attr('compObjectGroups'):
                for sg in compObjectGroup.iterOutputs(type='shadingEngine'):
                    if sg not in visited:
                        visited.add(sg)
                        yield sg

    def iterShaders(self) -> Iterator['nodes.ShadingDependNode']:
        visited = set()

        for sg in self.iterShadingGroups():
            shader = next(sg.attr('surfaceShader'
                                  ).iterInputs(type='shadingDependNode'), None)
            if shader is not None:
                if shader not in visited:
                    visited.add(shader)
                    yield shader

    def copyShadersTo(self,
                      *destinations,
                      worldSpace:bool=False,
                      alongNormal:bool=False,
                      first:bool=False):
        """
        If this is a mesh, and there are per-component assignments, will use
        ``transferShadingSets``, but only if the destination is also a mesh
        and *first* is False.

        :param destinations: the geometries to copy shaders to
        :param worldSpace: used for ``transferShadingSets``; defaults to False
        :param alongNormal: used for ``transferShadingSets``; defaults to
            False
        :param first: don't use ``transferShadingSets``; defaults to False
        """
        surfaceShapes = []

        for destination in destinations:
            surfaceShapes += list(_iterSurfaceShapes(destination))

        surfaceShapes = list(without_duplicates(surfaceShapes))

        if surfaceShapes:
            shaders = list(self.iterShaders())

            num = len(shaders)

            if num > 0:
                if num > 1 and not first:
                    multi = isinstance(self, nodes['Mesh'])
                    _self = str(self)
                else:
                    multi = False

                for surfaceShape in surfaceShapes:
                    if multi and isinstance(surfaceShape, nodes['Mesh']):
                        kwargs = {'searchMethod': 0 if alongNormal else 3,
                                  'sampleSpace': 0 if worldSpace else 1}
                        m.transferShadingSets(_self, str(surfaceShape), **kwargs)
                    else:
                        surfaceShape.assignShader(shaders[0])

    def assignShader(self, shader):
        print('the shader is ', shader)
        print('the geometries is ', str(self))

        m.hyperShade(assign=str(shader), geometries=str(self))

