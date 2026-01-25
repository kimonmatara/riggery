import math
import maya.cmds as m
import riggery.core as r
r.nodes.rehash()

def _test():
    path = r"C:/Users/user/Desktop/test.ma"
    m.file(path, o=1, f=1)

    arcPoint1 = r.Elem('loc1').attr('worldPosition')
    arcPoint2 = r.Elem('loc3').attr('worldPosition')
    apexPoint = r.Elem('loc2').attr('worldPosition')

    tangent1 = arcPoint1 - apexPoint
    tangent2 = arcPoint2 - apexPoint

    arcAngle = tangent1.angleTo(tangent2)
    halfArcAngle = arcAngle * 0.5

    # Derive chord length
    hypotenuse = tangent1.length()
    halfChordLength = halfArcAngle.sin() * hypotenuse
    chordLength = halfChordLength * 2

    #---------------|    Derive circle radius

    centralAngle = math.radians(180)-arcAngle
    halfCentralAngle = centralAngle * 0.5

    opposite = halfChordLength
    hypotenuse = opposite / halfCentralAngle.sin()

    circleRadius = hypotenuse

    #---------------|    Test with arc node (works)

    node = r.nodes.MakeTwoPointCircularArc.createNode()
    arcPoint1 >> node.point1
    arcPoint2 >> node.point2
    circleRadius >> node.radius

    node.directionVector.set((0, 1, 0))
    node.outputCurve.createShape()

def test():
    path = r"C:/Users/user/Desktop/test2.maC:/Users/user/Desktop/test2.ma"
    r.file(path, o=1, f=1)
    locs = r.ls('loc_??_LOCT')
    bias1 = locs[0].addAttr('bias', k=True, dv=0.5)
    bias2 = locs[2].addAttr('bias', k=True, dv=0.5)
    points = [loc.attr("worldPosition") for loc in locs]
    r.nodes.BezierCurve.createTriFillet(*points, bias1=bias1, bias2=bias2)

