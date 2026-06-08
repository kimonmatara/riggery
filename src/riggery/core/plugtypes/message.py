from ..plugtypes import __pool__ as plugs
Attribute = plugs['Attribute']

import maya.cmds as m


class Message(Attribute):
    
    def isMessage(self) -> bool:
        return True