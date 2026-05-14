import itertools as _itr
from functools import cached_property
from typing import Optional, Union, Any, Iterator

from .strings import nice_name
from .iterables import check_index
from .mappings import get_first_in_dicts
from .functions import roperty
from .types import iter_mro_dicts

class _Base:
    ...

class BaseMeta(type):

    def __new__(meta, clsname, bases, dct):
        rn = dct.get('__readable_name__', None)

        if rn is None:
            dct['__readable_name__'] = nice_name(clsname).lower()

        return super().__new__(meta, clsname, bases, dct)


class Base(_Base, metaclass=BaseMeta):

    __readable_name__ = None # e.g. 'cached samples'

    #-------------------------------------|    Init

    def __init__(self, owner:Any):
        self._owner = owner

    #-------------------------------------|    Navigation

    @roperty
    def owner(self):
        return self._owner

    o = owner

    @property
    def owners(self) -> Iterator['Base']:
        current = self

        while True:
            current = current.owner
            if current is None or not isinstance(current, Base):
                break
            yield current

    @roperty
    def root(self) -> Any:
        current = self

        while True:
            current = current.owner

            if current is None or not isinstance(current, Base):
                return current

    #-------------------------------------|    Repr

    def __repr__(self):
        return "<{}>".format(self.__readable_name__)


class CachedSample(Base):

    #-------------------------------------|    Init

    def __init__(self, owner:'CachedSamples', index:int):
        super().__init__(owner)
        self._index = index

    @roperty
    def index(self):
        return self._index

    i = index

    #-------------------------------------|    Navigation

    @roperty
    def is_first(self) -> bool:
        return self.index == 0

    @roperty
    def is_last(self) -> bool:
        return self.index == len(self.owner) - 1

    @roperty
    def is_inner(self) -> bool:
        return not (self.is_first or self.is_last)

    def next(self) -> 'CachedSample':
        try:
            return self.owner[self.index + 1]
        except IndexError:
            raise IndexError("already at end")

    def prev(self) -> 'CachedSample':
        try:
            index = check_index(self.index - 1,
                                len(self.owner),
                                reject_negative=True)
        except IndexError:
            raise IndexError("already at start")
        return self.owner[index]

    #-------------------------------------|    Repr

    def __repr__(self):
        return "<{} {}>".format(self.__readable_name__, self.i)

class CachedSamples(Base):

    #-------------------------------------|    Init

    def __init__(self,
                 owner:Any,
                 expected_length:int,
                 member_type:type['CachedSample']):
        super().__init__(owner)
        self._len = expected_length
        self._member_type = member_type
        self._content = {}

    #-------------------------------------|    Iter

    def __len__(self):
        return self._len

    def __iter__(self):
        for i in range(self._len):
            yield self[i]

    def __getitem__(self, i:Union[int, slice]):
        if isinstance(i, slice):
            return [self[ii] for ii in range(self._len)[i]]

        i = check_index(i, self._len)

        try:
            return self._content[i]
        except KeyError:
            self._content[i] = out = self._member_type(self, i)
            return out

    #-------------------------------------|    Repr

    def __repr__(self):
        return "<{} {}>".format(self.__readable_name__, self._len)