"""Various tagging tools."""

from typing import Generator
import re
from ..elem import Elem
from ..nodetypes import __pool__ as nodes
from ..plugtypes import __pool__ as plugs
from ..lib.names import TYPESUFFIXES
from riggery.internal.typeutil import UNDEFINED
from riggery.general.iterables import without_duplicates

import maya.cmds as m



ATTRTOTAG = re.compile(r"^(.*?)_tag$")

class MissingTagError(RuntimeError):
    pass

class TagsInterface:

    #------------------------------------|    Inst

    def __init__(self, owner):
        self._owner = nodes['DependNode'](owner)

    @property
    def owner(self):
        return self._owner

    #------------------------------------|    Node management

    def _getNetwork(self, create=False):
        try:
            msgPlug = self.owner.attr('tagger')
        except AttributeError:
            if create:
                msgPlug = self.owner.addAttr('tagger', at='message')
            else:
                return
        inputs = msgPlug.inputs()
        if inputs:
            return inputs[0]

        if create:
            nodeName = "{}_tags_{}".format(
                self.owner.shortName(sts=True),
                TYPESUFFIXES['network']
            )
            if nodeName.startswith('_'):
                nodeName = nodeName[1:]
            network = nodes['Network'].createNode(name=nodeName)
            network.addAttr('isTagger', at='bool', dv=True, l=True)
            network.attr('isHistoricallyInteresting').set(0)
            network.attr('message') >> msgPlug
            return network

    #------------------------------------|    Attr management

    @staticmethod
    def _tagNameToAttrName(tagName:str):
        return tagName+'_tag'

    @staticmethod
    def _attrNameToTagName(attrName:str):
        return re.match(ATTRTOTAG, attrName).groups()[0]

    def _initTagAttr(self, tagName:str, multi:bool=False):
        network = self._getNetwork(True)
        attrName = self._tagNameToAttrName(tagName)
        kwargs = {}
        if multi:
            kwargs['multi'] = multi
        return network.addAttr(attrName, at='message', **kwargs)

    #------------------------------------|    Remove

    def __delitem__(self, tagName):
        try:
            self.removeTag(tagName)
        except MissingTagError:
            raise KeyError(tagName)

    def removeTag(self, tagName, quiet=False):
        nw = self._getNetwork()
        if nw is None:
            if quiet:
                return
            raise MissingTagError(tagName)
        try:
            attr = nw.attr(self._tagNameToAttrName(tagName))
        except AttributeError:
            if quiet:
                return
            raise MissingTagError(tagName)

        if attr.isMulti():
            attr.clearMulti()
        else:
            attr.disconnect(inputs=True)

        m.deleteAttr(str(attr))
        if not self:
            m.delete(str(self._getNetwork()))

    def clear(self):
        for key in self:
            self.removeTag(key)

    #------------------------------------|    Set

    def __setitem__(self, tagName:str, content):
        self.removeTag(tagName, True)
        multi = isinstance(content, (list, tuple))
        attr = self._initTagAttr(tagName, multi)

        if multi:
            content = without_duplicates(map(Elem, content))

            for i, item in enumerate(content):
                if isinstance(item, plugs['Attribute']):
                    item >> attr[i]
                else:
                    item.attr('message') >> attr[i]
        else:
            content = Elem(content)
            if isinstance(content, plugs['Attribute']):
                content >> attr
            else:
                content.attr('message') >> attr

    #------------------------------------|    Get

    def keys(self) -> Generator[str, None, None]:
        """
        Yields tag names.
        """
        nw = self._getNetwork()
        if nw is not None:
            for attr in nw.listAttr(ud=True, at='message'):
                mt = re.match(ATTRTOTAG, attr.attrName())
                if mt:
                    yield mt.groups()[0]

    def __iter__(self):
        return iter(dict(zip(self.keys(), self.values())))

    def values(self):
        """
        Yields tag members.
        """
        for key in self.keys():
            yield self._getTagContent(key)

    def items(self):
        """
        Yields tag, content pairs.
        """
        for key, value in zip(self.keys(), self.values()):
            yield key, value

    def __bool__(self):
        for key in self.keys():
            return True
        return False

    def __len__(self):
        return len(list(self.keys()))

    def __getitem__(self, tagName:str):
        try:
            return self._getTagContent(tagName)
        except MissingTagError:
            raise KeyError(tagName)

    def _getTagContent(self, tagName:str, default=UNDEFINED):
        nw = self._getNetwork()
        if nw is None:
            if default is UNDEFINED:
                raise MissingTagError(tagName)
            return default
        try:
            attr = nw.attr(self._tagNameToAttrName(tagName))
        except AttributeError:
            if default is UNDEFINED:
                raise MissingTagError(tagName)
            return default

        if attr.isMulti():
            out = []
            for index in attr.indices():
                slot = attr[index]
                inputs = slot.inputs(plugs=True)
                if inputs:
                    input = inputs[0]
                    if isinstance(input, plugs['Message']):
                        out.append(input.node())
                    else:
                        out.append(input)
            return out

        inputs = attr.inputs(plugs=True)
        if inputs:
            input = inputs[0]
            if isinstance(input, plugs['Message']):
                return input.node()
            return input

    def get(self, tagName, default=None, /):
        """
        :param tagName: the tag to retrieve
        :param default: the default to return if the tag doesn't exist;
            defaults to None
        :return: Either the tag content, or *default*.
        """
        return self._getTagContent(tagName, default)

    def __contains__(self, tagName:str) -> bool:
        network = self._getNetwork()
        if network is None:
            return False
        return network.hasAttr(self._tagNameToAttrName(tagName))

    #------------------------------------|    Repr

    def __repr__(self):
        return "{}.tags".format(repr(self.owner))


class TagsGetter:
    def __get__(self, inst, instype):
        if inst is None:
            return self
        interface = TagsInterface(inst)
        setattr(inst, 'tags', interface)
        return interface

def iterTaggers():
    networks = m.ls(type='network')
    T = nodes['DependNode']

    if networks:
        for network in networks:
            try:
                val = m.getAttr(f"{network}.isTagger")
            except:
                continue
            if val:
                yield T(network)

def getTaggers():
    return list(self.iterTaggers)

def iterTagsFromMember(member):
    member = str(member)
    outputs = m.connectionInfo(f"{member}.message", dfs=True)
    if outputs:
        for output in outputs:
            mt = re.match(r"^.*?\.([^.]+)_tag$", output)
            if mt:
                yield mt.groups()[0]

def getTagsFromMember(member):
    return list(iterTagsFromMember(member))
