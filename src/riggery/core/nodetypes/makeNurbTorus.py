from ..nodetypes import __pool__ as nodes
RevolvedPrimitive = nodes['RevolvedPrimitive']

import maya.cmds as m


class MakeNurbTorus(RevolvedPrimitive):
    
    def initSectionRadius(self):
        """
        Creates, or retrieves, a more intuitive 'sectionRadius' input
        attribute.
        """
        if not self.hasAttr('sectionRadius'):
            sectionRadius = self.addAttr('sectionRadius',
                                         at='doubleLinear',
                                         dv=1.0, k=True)
        else:
            sectionRadius = self.attr('sectionRadius')

        if not any(sectionRadius.iterOutputs()):
            heightRatio = self.attr('heightRatio')
            heightRatio.unlock()

            sectionRadius / self.attr('radius') >> heightRatio
            heightRatio.lock()

        return sectionRadius