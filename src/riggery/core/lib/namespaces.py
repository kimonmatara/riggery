"""Tools to manage Maya namespaces."""

from fnmatch import fnmatch
from typing import Generator, Optional, Union
import re

import maya.cmds as m

from ..elem import Elem
from riggery.general.functions import resolve_flags, short
from riggery.general.iterables import expand_tuples_lists, \
    without_duplicates

INTERNAL = [':UI', ':shared']

#---------------------------------------------|
#---------------------------------------------|    ERRORS
#---------------------------------------------|

class NamespaceError(RuntimeError):
    pass

class InternalNamespaceError(NamespaceError):
    """
    The specified namespace can't be deleted or created because it's one
    of the Maya 'internal' namespaces, namely ':UI' or ':shared'.
    """

class NamespaceExistsError(RuntimeError):
    """
    A namespace being created already exists.
    """

#---------------------------------------------|
#---------------------------------------------|    HELPERS
#---------------------------------------------|

def isInternal(namespace) -> bool:
    """
    :param namespace: the namespace to inspect; this will be conformed to
        absolute form based on the current context
    :return: True *namespace* is an internal Maya namespace, e.g. ':UI' or
        ':shared'.
    """
    return abs(namespace) in INTERNAL

def conformNodes(*nodes): # -> list[Elem]
    """
    Unpacks \*nodes, conforms to ``Elem`` and removes duplicates.

    :param \*nodes: the nodes to conform
    :return: The list of conformed nodes.
    """
    nodes = expand_tuples_lists(*nodes)
    nodes = list(map(Elem, nodes))
    return list(without_duplicates(nodes))

def clean(namespace:str) -> str:
    """
    Strips trailing colons for the namespace.
    """
    if namespace in (None, '', ':'):
        return ':'
    return re.match(r"^(.*?)(?:\:+)?$", namespace).groups()[0]

def abs(namespace:str) -> str:
    """
    Doesn't perform any checks. If the namespace doesn't start with ':',
    it will have the current namespace prepended to it.
    """
    if namespace.startswith(':'):
        return namespace

    current = m.namespaceInfo(currentNamespace=True, absoluteName=True)

    if current == ':':
        current = ''

    return f"{current}:{namespace}"

#---------------------------------------------|
#---------------------------------------------|    CONTEXT MANAGERS
#---------------------------------------------|

class RelativeNames:
    """
    Context manager; turns on 'relative names' for the block and restores
    the previous setting on exit.

    Note that :class:`Namespace` also does this by default, so no need to
    combine them.
    """
    def __enter__(self):
        self._prevRn = m.namespace(relativeNames=True, q=True)
        m.namespace(relativeNames=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        m.namespace(relativeNames=self._prevRn)
        del(self._prevRn)
        return False

class Namespace(str):
    """
    String-like namespace manager.

    Notes
    =====

    -   Namespaces are conformed to 'absolute' form on instantiation

    -   The context manager will always activate relative names on enter,
        and restore the setting on exit.

        If an attempt is made to enter a non-existent namespace, the
        namespace will be automatically created ('actualized'). If you need
        more control over its creation, enter the output of :meth:`create`
        instead.
    """

    #---------------------------------|    Inst

    def __new__(cls, namespace):
        namespace = abs(clean(namespace))
        return str.__new__(cls, namespace)

    #---------------------------------|    Constructor(s)

    @classmethod
    @short(makeUnique='mu', reuse='re', reuseOnlyIfEmpty='roe')
    def create(cls,
               namespace:str,
               makeUnique:bool=False,
               reuse:bool=False,
               reuseOnlyIfEmpty:bool=False):
        """
        :param namespace: the namespace to create
        :param makeUnique/mu: if the namespace already exists, append a number
            to it to make it unique; this will only be used
        :param reuse/re: if the namespace already exists, return the existing
            namespace; defaults to False
        :param reuseOnlyIfEmpty/roe: ignored if *reuse* if False; if the
            namespace already exists, use it only if it doesn't contain any
            nodes (or other namespaces with nodes); otherwise, if *makeUnique*
            is True, create a unique name; otherwise, error; defaults to False
        :raises NamespaceExistsError: The namespace already exists.
        """
        namespace = abs(clean(namespace))
        count = 0

        while True:
            _candidate = namespace
            if count > 0:
                _candidate += str(count)
            candidate = cls(_candidate)
            if candidate.exists():
                if reuse:
                    if reuseOnlyIfEmpty:
                        if not candidate.getNodes(recurse=True):
                            return candidate
                    else:
                        return candidate

                if makeUnique:
                    count += 1
                    continue

                raise NamespaceExistsError(
                    f"namespace exists: {_candidate}"
                )
            return candidate.actualize()

    def actualize(self): # -> Self
        """
        If this namespace doesn't exist, creates it.
        :return: self
        """
        if not self.exists():
            m.namespace(addNamespace=str(self))
        return self

    @classmethod
    @short(includeInternal='ii')
    def getAll(cls, includeInternal:bool=False): # -> list['Namespace']
        """
        :param includeInternal: include the internal, non-user-editable ':UI'
            and ':shared' namespaces; defaults to False
        :return: Namespaces excluding the root (':') namespace.
        """
        result = m.namespaceInfo(':', listOnlyNamespaces=True, recurse=True)

        if result is None:
            return []

        result = list(map(Namespace, result))

        if not includeInternal:
            result = list(filter(lambda x: not x.isInternal(), result))
        return result

    #---------------------------------|    Renaming / replacement

    def rename(self, newNamespace:str) -> str:
        """
        Creates a new namespace, moves all of this namespace's members to that,
        deletes this namespace, and returns the new namespace.
        """
        wasCurrent = self.isCurrent()

        if self.isRoot():
            raise RuntimeError("root namespace can't be renamed")

        newNamespace = Namespace(newNamespace).actualize()
        if self == newNamespace:
            return self

        m.namespace(moveNamespace=(self, newNamespace), force=True)

        if self.isEmpty():
            self.destroy()

        if wasCurrent:
            m.namespace(set=newNamespace)

        return newNamespace

    #---------------------------------|    Destructors

    @classmethod
    def pruneNamespaces(cls):
        """
        Removes any namespaces which don't contain nodes or other non-empty
        namespaces.
        """
        # Start with the most deeply nested namespaces
        for namespace in reversed(
            sorted(
                cls.getAll(),
                key=lambda x: len(x.getParents()) -1 # exclude root
            )
        ):
            if namespace.getMembers():
                continue
            namespace.destroy()

    def destroy(self, members:bool=False):
        """
        Removes this namespace; content will be moved to the root namespace;
        some nodes may be renamed in case of clashes. If this is the current
        namespace, the current namespace will be switched to the root.

        :param members: delete the namespace members too; defaults to False
        :raises NamespaceError: The root namespace can't be deleted.
        """
        if self.isRoot():
            raise NamespaceError("The root namespace can't be deleted.")

        if self.isCurrent():
            self.setCurrent(':')

        kwargs = {'removeNamespace': self, 'force': True}

        if members:
            kwargs['deleteNamespaceContent'] = True
        else:
            kwargs['mergeNamespaceWithRoot'] = True

        m.namespace(**kwargs)

    #---------------------------------|    Context

    def isCurrent(self) -> bool:
        """
        :return: True if this is the current namespace.
        """
        return self.getCurrent() == self

    @classmethod
    def getCurrent(cls) -> 'Namespace':
        """
        Class method. Returns the current namespace.
        """
        return Namespace(m.namespaceInfo(currentNamespace=True,
                                         absoluteName=True))

    @classmethod
    def setCurrent(cls, namespace:str) -> 'Namespace':
        """
        Class method. Sets the current namespace.
        :param namespace: the namespace to make current
        :return: An instance for the namespace.
        """
        m.namespace(set=namespace)
        return cls(namespace)

    def __enter__(self):
        self.actualize()
        self._prevNs = self.getCurrent()
        self._prevRn = m.namespace(relativeNames=True, q=True)

        self.setCurrent(self)
        m.namespace(relativeNames=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.setCurrent(self._prevNs)
        m.namespace(relativeNames=self._prevRn)
        del(self._prevNs)
        del(self._prevRn)
        return False

    #---------------------------------|    Basic inspections

    def isInternal(self) -> bool:
        """
        :return: True if this is one of Maya's reserved 'internal' namespaces,
            namely ':UI' or ':shared'.
        """
        return self in INTERNAL

    def exists(self) -> bool:
        """
        :return: True if this namespace exists.
        """
        return m.namespace(exists=self)

    def isRoot(self) -> bool:
        """
        :return: True if this is the root namespace.
        """
        return self == ':'

    #---------------------------------|    Hierarchy

    def getParent(self) -> 'Namespace':
        """
        :return: This namespace's immediate parent. If this is the root
            namespace, None.
        """
        # I think the namespaceInfo implementation is a little buggy,
        # when absoluteName is requested, so here's a calculated one
        elems = self.split(':')
        if len(elems) > 1:
            return Namespace(':'.join(elems[:-1]))

    def iterParents(self) -> Generator['Namespace', None, None]:
        """
        Iterates over this namespace's parents, up to and including the root
        namespace. If this is the root namespace, nothing will be yielded.
        """
        if not self.isRoot():
            current = self

            while True:
                parent = current.getParent()
                yield(parent)
                if parent.isRoot():
                    break
                current = parent

    def getParents(self): # -> list['Namespace']:
        """
        List version of :meth:`iterParents`.
        """
        return list(self.iterParents())

    def hasParent(self, parentNamespace:Union[str, 'Namespace']) -> bool:
        """
        :return: True if *parentNamespace* is a parent to this namespace,
            regardless of rank.
        """
        parentNamespace = Namespace(parentNamespace)
        for parent in self.iterParents():
            if parent == parentNamespace:
                return True

    #---------------------------------|    Listings

    def isEmpty(self) -> bool:
        """
        :return: True if this namespace is empty of nodes or child namespaces.
        """
        if self.exists():
            return not bool(m.namespaceInfo(self, listNamespace=True))
        raise RuntimeError(f"Namespace doesn't exist: {self}")

    @short(recurse='r')
    def getMembers(self,
                   nodes:Optional[bool]=None,
                   namespaces:Optional[bool]=None,
                   recurse:bool=False):
        """
        Internal Maya nodes (e.g. item filters) are not included.

        The *nodes* and *namespaces* flags are evaluated Maya-style, i.e. if
        only one is passed in as True, the other is set to False.

        :param nodes: include nodes
        :param recurse / r: look inside nested namespaces too
        :param namespaces: include nested namespaces
        """
        nodes, namespaces = resolve_flags(nodes, namespaces)
        out = []

        if nodes:
            out += self.getNodes()

        if namespaces:
            childNamespaces = self.getChildNamespaces()
            for childNamespace in childNamespaces:
                out.append(childNamespace)
                if recurse:
                    out += childNamespace.getMembers(nodes=nodes,
                                                     namespace=namespace,
                                                     recurse=True)
        elif recurse and nodes:
            for childNamespace in self.getChildNamespaces():
                out += childNamespace.getNodes(recurse=True)

        return out


    @short(recurse='r', includeInternal='ii')
    def getChildNamespaces(self,
                           recurse:bool=False,
                           includeInternal:bool=False): # -> list['Namespace']:
        """
        :param recurse / r: list children of children as well; defaults to
            False
        :param includeInternal / ii: include reserved Maya namespaces such as
            ':UI' and ':shared'; defaults to False
        :return: Any namespaces under this one.
        """
        out = m.namespaceInfo(self,
                              listOnlyNamespaces=True,
                              recurse=recurse)
        if out:
            out = [Namespace(item) for item in out]
            if not includeInternal:
                out = list(filter(lambda x: not x.isInternal(), out))
            return out
        return []

    @short(recurse='r')
    def getNodes(self, recurse:bool=False): # -> list[Elem]
        """
        :param recurse / r: look inside child namespaces too; defaults to
            False
        :return: A list of nodes under this namespace.
        """
        nodes = m.namespaceInfo(self,
                                listOnlyDependencyNodes=True,
                                dagPath=True,
                                recurse=recurse)
        if nodes:
            return list(map(Elem, nodes))
        return []

    @short(recurse='r')
    def findNodes(self,
                  pattern:str,
                  recurse:bool=False) -> Generator[Elem, None, None]:
        """
        Yields ``Elem`` instances for any nodes in this namespace that match
            the specified pattern.
        :param recurse / r: look inside child namespaces too; defaults to
            False
        :param pattern: a glob-style, local pattern
        """
        nodes = m.namespaceInfo(self,
                                listOnlyDependencyNodes=True,
                                absoluteName=True)
        if nodes:
            if self == ':':
                _pattern = ':'+pattern
            else:
                _pattern = self +':'+pattern
            for node in nodes:
                if fnmatch(node, _pattern):
                    yield Elem(node)

        if recurse:
            for namespace in self.getChildNamespaces():
                for item in namespace.findNodes(pattern, recurse=True):
                    yield(item)

    @short(recurse='r')
    def findNode(self, pattern:str, recurse:bool=False) -> Optional[Elem]:
        """
        :param pattern: a glob-style, local pattern
        :param recurse / r: look inside child namespaces too; defaults to
            False
        :return: The first node under this namespace that matches *pattern*.
        """
        for item in self.findNodes(pattern, recurse=recurse):
            return item

    #---------------------------------|    Add / remove nodes

    def addNodes(self, *nodes):
        """
        :param \*nodes: the nodes to add to this namespace, packed or unpacked
        :rtype \*nodes: Elem or str
        """
        for node in conformNodes(*nodes):
            newName = "{}:{}".format(
                self,
                node.shortName(stripNamespace=True)
            )
            node.name = newName

    def setNodes(self, *nodes):
        """
        :param \*nodes: the nodes to replace this namespace membership with
        """
        requestedNodes = conformNodes(*nodes)
        currentNodes = self.getNodes()
        toAdd = [node for node in requestedNodes if node not in currentNodes]
        toRem = [node for node in currentNodes if node not in requestedNodes]
        if toAdd:
            self.removeNodes(toRem)
        if toRem:
            self.addNodes(toAdd)

    def removeNodes(self, *nodes):
        """
        :param \*nodes: the nodes to add to the root namespace, packed or
            unpacked
        """
        if not self.isRoot():
            Namespace(':').addNodes(*nodes)

    #---------------------------------|    Repr

    def __repr__(self):
        return f"{type(self).__name__}({str.__repr__(self)})"