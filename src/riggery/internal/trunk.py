import os
import inspect

class TrunkMeta(type):
    def __new__(meta, clsname, bases, dct):
        dct['__homedir__'] = os.path.dirname(
            inspect.currentframe().f_back.f_code.co_filename
        )
        return super().__new__(meta, clsname, bases, dct)


class Trunk(metaclass=TrunkMeta):

    __homedir__:str