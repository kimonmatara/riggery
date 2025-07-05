from typing import Optional, Union, Generator
import inspect
import re

def get_subclasses_recursive(cls:type) -> list[type]:
    """
    :param cls: the class to scan from
    :return: All the descendants of the class, recursively.
    """
    out = []
    for c in cls.__subclasses__():
        out.append(c)
        out += get_subclasses_recursive(c)
    return out

def collapse_ancestors(classes:Union[list[type], tuple[type]]) -> list[type]:
    """
    Returns a list where any class in *classes* which is a parent of
    another class in *classes* is omitted.
    :param classes: a list or tuple of classes to process
    :return: A filtered list.
    """
    out = []
    for i, cls in enumerate(classes):
        skip = False
        for ii, child in enumerate(classes):
            if i == ii:
                continue
            if issubclass(child, cls):
                skip = True
                break
        if not skip:
            out.append(cls)
    return out

class SingletonMeta(type):
    """
    Assign this metaclass to any class to turn the class into a singleton.
    """
    def __new__(meta, clsname, bases, dct):
        dct['__instance__'] = None
        return super().__new__(meta, clsname, bases, dct)

    def __call__(cls, *args, **kwargs):
        if cls.__instance__ is None:
            cls.__instance__ = super().__call__(*args, **kwargs)
        return cls.__instance__


class Undefined(metaclass=SingletonMeta):

    def __bool__(self):
        return False

    def __repr__(self):
        return '<undefined>'

UNDEFINED = Undefined()


class TTCycleError(RuntimeError):
    """
    An insertion into a :class:`TypeTree` caused a cycle error.
    """


class TypeTree:
    """
    Gives you a way to quickly declare type trees (using :meth:`fromText`)
    and then get key paths (using :meth:`get_path_to`).

    Internally, the data is a dict, where:
    ```
    child: parent or None,
    child: parent or None,
    ...
    ```
    """
    @classmethod
    def from_text(cls, text:str) -> 'TypeTree':
        """
        Note that multiple assignments are not allowed; if a child class
        is assigned a new parent, it will override the previous one.

        Provide the tree in this sort of format:

        ```
        Alpha
            Beta
            Gamma
                Delta
            Epsilon
        ```

        :param text: the indented text outline of the class tree
        """
        # text = inspect.cleandoc(text)
        #print("Cleaned:")
        # print(text)
        # raise RuntimeError
        lines = list(
            filter(
                bool,
                [re.sub(r"\s+(?=$)", '', line) \
                 for line in text.split('\n')]
            )
        )
        depthPairs = []

        for line in lines:
            indent, clsname = re.match(r"^(\s*)(.*?)\s*$", line).groups()
            depthPairs.append((len(indent), clsname))

        # Normalize depths
        rankedDepths = list(sorted(set([pair[0] for pair in depthPairs])))
        depthPairs = [(rankedDepths.index(pair[0]),
                       pair[1]) for pair in depthPairs]

        registry = {} # class: parent

        for i, (thisDepth, thisCls) in enumerate(depthPairs):
            if i == 0:
                registry[thisCls] = None
            else:
                prevDepth, prevCls = depthPairs[i-1]
                delta = thisDepth - prevDepth

                if delta > 0:
                    registry[thisCls] = prevCls
                else:
                    parent = prevCls
                    for i in range(abs(delta)+1):
                        parent = registry[parent]
                    registry[thisCls] = parent

        inst = cls()
        inst._data.update(registry)
        inst.cycle_check()
        return inst

    def __init__(self):
        self._data = {}

    def cycle_check(self):
        """
        :raises TTCycleError:
        """
        for cls in self._data:
            visited = []
            while True:
                if cls in visited:
                    raise TTCycleError(cls)
                visited.append(cls)
                cls = self._data[cls]
                if cls is None:
                    break

    def names(self) -> Generator[str, None, None]:
        """
        Yields names in the tree.
        """
        out = []

        for k, v in self._data.items():
            if k not in out:
                out.append(k)
                yield(k)
            if (v is not None) and (v not in out):
                out.append(v)
                yield(v)

    def get_parent(self, clsname:str) -> Optional[str]:
        """
        :param clsname: the class to query
        :return: The parent of class *clsname*, if any.
        """
        if clsname in self:
            return self._data.get(clsname)
        raise KeyError(f"Class does not exist: {clsname}")

    def get_children(self, clsname:str) -> list[str]:
        """
        :param clsname: the class to query
        :return: The children of class *clsname*, if any.
        """
        if clsname in self:
            return [name for name in self.names() \
                    if self.get_parent(name) == clsname]
        raise KeyError(f"Class does not exist: {clsname}")

    def get_path_to(
            self,
            clsname:str, *,
            insert_under:Union[Undefined, None, str]=UNDEFINED
    ) -> list[str]:
        """
        :param clsname: the class for which to construct a path
        :param insert_under: if this is provided, it must either be
            ``None`` or an existing key, and it will be used as the
            parent under which to insert *clsname* if it's not in the
            tree
        :return: The hierarchy path leading to class *clsname*, which
            will be last on the list.
        """
        if clsname not in self:
            if insert_under is not UNDEFINED:
                if insert_under is None or insert_under in self:
                    self._data[clsname] = insert_under
                else:
                    raise KeyError(insert_under)
            else:
                raise KeyError(clsname)

        current = clsname
        out = []
        while True:
            out.append(current)
            current = self.get_parent(current)
            if current is None:
                break
        return list(reversed(out))

    def get_parents(self, clsname:str) -> list[str]:
        """
        :param clsname: the class to query
        :return: The list of parents above *clsname* (inner to outer).
        """
        path = self.get_path_to(clsname)
        if len(path) == 1:
            return []
        return list(reversed(path[:-1]))

    def get_depth(self, clsname) -> int:
        """
        :param clsname: the class to query
        :return: The number of classes above class *clsname*.
        """
        return len(self.get_parents(clsname))

    def __contains__(self, key:str):
        return key in self.names()

    def __str__(self):
        """
        Returns the type of string accepted by :meth:`fromText`.
        """
        lines = []

        rootNames = [name for name \
                     in self.names() if self.get_depth(name) == 0]

        def append_name(name, indent=0):
            line = "{}{}".format('    '*indent, name)
            lines.append(line)
            children = self.get_children(name)
            indent += 1
            for child in children:
                append_name(child, indent)

        for rootName in rootNames:
            append_name(rootName)

        return '\n'.join(lines)