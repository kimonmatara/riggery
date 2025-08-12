"""Tools for working with geometries."""

from ..nodetypes import __pool__ as _nodes
from ..plugtypes import __pool__ as _plugs
from ..datatypes import __pool__ as _data
from . import mixedmode as _mm

import maya.cmds as m

class CachedGeoSampler:

    def __new__(cls, network):
        if isinstance(network, CachedGeoSampler):
            return network

        network = _nodes['DependNode'](network)

        if cls is CachedGeoSampler:
            clsname = network.attr('geoSamplerType')()
            cls = eval(clsname)

        return object.__new__(cls)

    #-------------------------------------|    Init

    def _configNode(self):
        self._initSamplesArray()

    @classmethod
    def create(cls, geoOutput):
        geoOutput = _plugs['Attribute'](geoOutput)

        for output in geoOutput.outputs(type='network', plugs=True):
            if output.attrName() == 'geo':
                node = output.node()
                if node.hasAttr('geoSamplerType'):
                    inst = CachedGeoSampler(node)
                    if type(inst) is cls:
                        return inst

        node = _nodes['Network'].createNode()
        node.addAttr('geoSamplerType', dt='string').set(cls.__name__)
        geoOutput >> node.addAttr('geo', at='message')
        self = cls(node)
        self._configNode()

        return self

    def __init__(self, network):
        self._node = _nodes['DependNode'](network)

    #-------------------------------------|    Inspections

    def node(self):
        return self._node

    @property
    def geo(self):
        return self.node().attr('geo').inputs(plugs=True)[0]

    #-------------------------------------|    Partials

    def _initSamplesArray(self):
        raise NotImplementedError

    @classmethod
    def _getPositionTypes(cls):
        pass

    def _findSample(self, position):
        position, _, positionIsPlug = _mm.info(position,
                                               self._getPositionTypes())

        for slot in self.node().attr('samples'):
            inputs = slot.attr('samplePosition').inputs(plugs=True)

            if positionIsPlug:
                if position in inputs:
                    found = slot.attr('sampleResult')
                    return found
            else:
                if not inputs:
                    if position == slot.attr('samplePosition')():
                        found = slot.attr('sampleResult')
                        return found

    def _createSample(self, position):
        raise NotImplementedError

    def sample(self, position):
        out = self._findSample(position)
        if out is None:
            out = self._createSample(position)
        return out

    __getitem__ = sample

    #-------------------------------------|    Repr

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, repr(self._node))


class CurveSamplePointAtFraction(CachedGeoSampler):

    @classmethod
    def _getPositionTypes(cls):
        return float, _plugs['Float']

    def _initSamplesArray(self):
        _node = str(self.node())

        m.addAttr(_node,
                  ln='samples', multi=True, at='compound', nc=2)

        m.addAttr(_node,
                  ln='samplePosition',
                  at='double',
                  parent='samples',
                  min=0,
                  max=1)

        m.addAttr(_node,
                  ln='sampleResult',
                  at='double3',
                  nc=3,
                  parent='samples')

        for ax in 'XYZ':
            m.addAttr(_node,
                      ln='sampleResult'+ax,
                      at='doubleLinear',
                      parent='sampleResult')

    def _createSample(self, position):
        slot = self.node().attr('samples').nextElement()
        position >> slot.attr('samplePosition')

        mp = _nodes['MotionPath'].createNode()
        self.geo >> mp.attr('geometryPath')
        mp.attr("fractionMode").set(True)
        slot.attr('samplePosition') >> mp.attr('uValue')
        mp.attr('allCoordinates') >> slot.attr('sampleResult')
        return slot.attr('sampleResult').lock(r=True)

class CurveSampleClosestPoint(CachedGeoSampler):

    @classmethod
    def _getPositionTypes(cls):
        return _plugs['Point'], _data['Point']

    def _initSamplesArray(self):
        _node = str(self.node())

        m.addAttr(_node,
                  ln='samples',
                  multi=True,
                  nc=2,
                  at='compound')

        m.addAttr(_node,
                  ln='samplePosition',
                  at='double3',
                  nc=3,
                  parent='samples')

        for ax in 'XYZ':
            m.addAttr(_node,
                      ln='samplePosition'+ax,
                      at='doubleLinear',
                      parent='samplePosition')

        m.addAttr(_node,
                  ln='sampleResult',
                  at='compound',
                  nc=2,
                  parent='samples')

        m.addAttr(_node,
                  ln='position',
                  at='double3',
                  nc=3,
                  parent='sampleResult')

        for ax in 'XYZ':
            m.addAttr(_node,
                      ln='position'+ax,
                      at='doubleLinear',
                      parent='position')

        m.addAttr(_node,
                  ln='parameter',
                  at='double',
                  parent='sampleResult')

        self.node().attr('samples')

    def _createSample(self, position):
        slot = self.node().attr('samples').nextElement()
        position >> slot.attr('samplePosition')

        node = _nodes['NearestPointOnCurve'].createNode()
        self.geo >> node.attr('inputCurve')
        slot.attr('samplePosition') >> node.attr('inPosition')

        node.attr('result') >> slot.attr('sampleResult')
        return slot.attr('sampleResult').lock(r=True)


class CurveSampleInfoAtParam(CachedGeoSampler):

    @classmethod
    def _getPositionTypes(cls):
        return float, _plugs['Float']

    def _initSamplesArray(self):
        _node = str(self.node())


        m.addAttr(_node,
                  ln='samples',
                  multi=True,
                  at='compound',
                  nc=2)

        m.addAttr(_node,
                  ln='samplePosition',
                  at='double',
                  parent='samples')

        m.addAttr(_node,
                  ln='sampleResult',
                  at='compound',
                  nc=7,
                  parent='samples')

        def _createTriple(name, parent=None, point=False):
            kw = {}

            if parent is not None:
                kw['parent'] = parent

            m.addAttr(_node, ln=name, at='double3', nc=3, **kw)

            for ax in 'XYZ':
                m.addAttr(_node,
                          ln=name+ax,
                          at='doubleLinear' if point else 'double',
                          parent=name)

        _createTriple('position', parent='sampleResult', point=True)
        _createTriple('normal', parent='sampleResult')
        _createTriple('normalizedNormal', parent='sampleResult')
        _createTriple('tangent', parent='sampleResult')
        _createTriple('normalizedTangent', parent='sampleResult')
        _createTriple('curvatureCenter', parent='sampleResult', point=True)
        m.addAttr(_node, ln='curvatureRadius', at='double',
                  parent='sampleResult')

        return self.node().attr('samples')

    def _createSample(self, position):
        slot = self.node().attr('samples').nextElement()
        position >> slot.attr('samplePosition')

        node = _nodes['PointOnCurveInfo'].createNode()
        self.geo >> node.attr('inputCurve')
        slot.attr('samplePosition') >> node.attr('parameter')
        node.attr('result') >> slot.attr('sampleResult')
        return slot.attr('sampleResult').lock(r=True)


class CurveSampleFractionAtLength(CachedGeoSampler):

    def _configNode(self):
        super()._configNode()
        node = self.node()
        node.addAttr('length', at='double', i=self.geo.length(), l=True, min=0)

    @classmethod
    def _getPositionTypes(cls):
        return float, _plugs['Float']

    def _initSamplesArray(self):
        _node = str(self.node())
        m.addAttr(_node,
                  ln='samples',
                  at='compound',
                  multi=True,
                  nc=2)
        m.addAttr(_node, ln='samplePosition', at='double', parent='samples')
        m.addAttr(_node, ln='sampleResult', at='double', parent='samples')

    def _createSample(self, position):
        slot = self.node().attr('samples').nextElement()
        position >> slot.attr('samplePosition')
        (position / self.node().attr('length')) >> slot.attr('sampleResult')
        return slot.attr('sampleResult').lock()


class CurveSampleLengthAtParam(CachedGeoSampler):

    def _initSamplesArray(self):
        _node = str(self.node())
        m.addAttr(_node,
                  ln='samples',
                  at='compound',
                  multi=True,
                  nc=2)
        m.addAttr(_node, ln='samplePosition', at='double', parent='samples')
        m.addAttr(_node, ln='sampleResult', at='double', parent='samples')

    def _createSample(self, position):
        slot = self.node().attr('samples').nextElement()
        position >> slot.attr('samplePosition')
        node = _nodes['SubCurve'].createNode()
        curve = self.geo
        curve >> node.attr('inputCurve')
        position >> node.attr('maxValue')
        subCurve = node.attr('outputCurve')
        subCurve.length() >> slot.attr('sampleResult')
        return slot.attr('sampleResult').lock()
