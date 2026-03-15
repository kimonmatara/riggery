import inspect
import typing as _th
import types as _t
from collections import abc as _abc

def isinstance_quiet(instance:object, possible_type: _th.Type) -> bool:
    """
    Runs :func:`isinstance` but supresses :class:`TypeError` to return
   ``False``.
    """
    try:
        return isinstance(instance, possible_type)

    except TypeError:
        return False

def issubclass_quiet(classA:_th.Type, classB:_th.Type) -> bool:
    """
    Runs :func:`issubclass` but supresses :class:`TypeError` to return
    ``False``.
    """
    try:
        return issubclass(classA, classB)

    except TypeError:
        return False

def isnone(instance:_th.Any) -> bool:
    return instance is None or isinstance_quiet(instance, _t.NoneType)

def isiterable(instance:_th.Any) -> bool:
    return isinstance_quiet(instance, _abc.Iterable)

def isiterator(instance:_th.Any) -> bool:
    return isinstance_quiet(instance, _abc.Iterator)

def isgenerator(instance:_th.Any) -> bool:
    return isinstance_quiet(instance, _abc.Generator)

def ismapping(instance:_th.Any) -> bool:
    return isinstance_quiet(instance, _abc.Mapping)

def hint_matches(hint:_th.Type,
                 possible_hints:_th.Iterable[_th.Type]
                 ) -> bool:
    return any((
        issubclass_quiet(hint, x) or hint == x for x in possible_hints
    ))

def conform_instance(instance:_th.Any,
                     hint:_th.Type,
                     exact:bool=False,
                     quiet:bool=False,
                     handler:_th.Optional[_th.Callable]=None) -> _th.Any:
    """
    Attempts to conform a value (typically passed-in through an argument) into
    a hinted type.

    :warning:
        This *will* break mutability where various custom flavours of mappings,
        lists etc. have to be re-instantiated.

    :param handler: if provided, should be a callable that will receive the
        instance, the hint, and the *exact* flag as positional arguments, and
        should return a tuple of two members: the first one should be the value
        (processed or unprocessed) and the second one should be a boolean, that
        should be True if the value has been handled, and False if it should
        be processed furthers; defaults to None
    """
    if hint is _th.Any:
        return instance

    if handler is not None:
        instance, handled = handler(instance, hint, exact)

        if handled:
            return instance

    origin = _th.get_origin(hint)
    base_hint = hint if origin is None else origin

    # Try basic, non-parameterizable types first

    if hint_matches(base_hint, (str, float, int)):
        if exact:
            if type(instance) is base_hint:
                return instance
        else:
            if isinstance(instance, base_hint):
                return instance
        try:
            return base_hint(instance)

        except (TypeError, ValueError):
            pass

    elif isnone(base_hint) and instance is None:
        return None

    else:
        hint_params = _th.get_args(hint)

        if base_hint is _th.Union:
            if hint_params:
                if exact:
                    if any((type(instance) is x for x in hint_params)):
                        return instance
                else:
                    if any((isinstance_quiet(instance, x)
                            for x in hint_params)):
                        return instance

                for t in hint_params:
                    try:
                        return conform_instance(instance,
                                                t,
                                                exact,
                                                quiet,
                                                handler)
                    except (TypeError, ValueError):
                        pass
            else:
                return instance

        elif base_hint is _th.Annotated:
            try:
                return conform_instance(instance,
                                        hint_params[0],
                                        exact,
                                        quiet,
                                        handler)
            except:
                pass

        elif (hint_matches(base_hint, (_th.Mapping, _abc.Mapping))
              and ismapping(instance)):

            if hint_params:
                k_type, v_type = hint_params

                try:
                    conformed = {
                        conform_instance(k, k_type, exact, quiet, handler):
                            conform_instance(v, v_type, exact, quiet, handler)
                        for k, v in instance.items()
                    }
                    proceed = True
                except (TypeError, ValueError):
                    proceed = False

                if proceed:
                    if base_hint in (_th.Mapping, _abc.Mapping):
                        return conformed

                    if exact:
                        if base_hint is dict:
                            return conformed
                    else:
                        if isinstance(base_hint, dict):
                            return conformed

                    try:
                        return base_hint(conformed)
                    except (TypeError, ValueError):
                        pass
            else:
                if base_hint in (_th.Mapping, _abc.Mapping):
                    return instance

                if exact:
                    if type(instance) is base_hint:
                        return instance
                else:
                    if isinstance_quiet(instance, base_hint):
                        return instance

                try:
                    return base_hint(instance)
                except (TypeError, ValueError):
                    pass

        elif (hint_matches(base_hint, (_th.Iterable, _abc.Iterable,
                                      _th.Iterator, _abc.Iterator))
              and isiterable(instance)):

            if hint_matches(base_hint, (tuple,)):
                if hint_params:
                    expected_types = list(hint_params)

                    if ... in expected_types:
                        varlen = True
                        expected_types.remove(...)
                    else:
                        varlen = False

                    proceed = True

                    if isinstance(instance, (tuple, list)):
                        received_members = instance
                    else:
                        try:
                            received_members = list(instance)
                        except (TypeError, ValueError):
                            proceed = False

                    if proceed:
                        if varlen:
                            t = _th.Union[tuple(expected_types)]
                            try:
                                conformed = [
                                    conform_instance(member, t, exact, quiet,
                                                     handler)
                                    for member in received_members
                                ]
                                proceed = True
                            except (TypeError, ValueError):
                                proceed = False

                            if proceed:
                                if exact:
                                    try:
                                        return base_hint(conformed)
                                    except (TypeError, ValueError):
                                        pass
                                else:
                                    try:
                                        return tuple(conformed)
                                    except (TypeError, ValueError):
                                        pass
                        else:
                            num_expected = len(expected_types)
                            num_received = len(received_members)

                            if num_expected == num_received:
                                try:
                                    conformed = [
                                        conform_instance(member,
                                                         t,
                                                         exact,
                                                         quiet,
                                                         handler)
                                        for member, t in zip(received_members,
                                                             expected_types)
                                    ]
                                    proceed = True
                                except (TypeError, ValueError):
                                    proceed = False

                                if proceed:
                                    if exact:
                                        try:
                                            return base_hint(conformed)
                                        except (TypeError, ValueError):
                                            pass
                                    else:
                                        try:
                                            return tuple(conformed)
                                        except (TypeError, ValueError):
                                            pass
                else:
                    if exact:
                        if type(instance) is base_hint:
                            return instance
                    else:
                        if isinstance_quiet(instance, base_hint):
                            return instance

                    try:
                        return base_hint(instance)
                    except (TypeError, ValueError):
                        pass

            elif hint_matches(base_hint, (list,)):
                if hint_params:
                    try:
                        conformed = [
                            conform_instance(member,
                                             hint_params[0],
                                             exact,
                                             quiet,
                                             handler)
                            for member in instance
                        ]
                        proceed = True
                    except (TypeError, ValueError):
                        proceed = False

                    if proceed:
                        if exact:
                            if base_hint is list:
                                return conformed
                        else:
                            if isinstance(conformed, base_hint):
                                return conformed

                        try:
                            return base_hint(conformed)
                        except (TypeError, ValueError):
                            pass
                else:
                    if exact:
                        if type(instance) is base_hint:
                            return instance
                    else:
                        if isinstance_quiet(instance, base_hint):
                            return instance

                    try:
                        return base_hint(instance)
                    except (TypeError, ValueError):
                        pass
            else:
                if hint_params:
                    conform_gen = (
                        conform_instance(member, hint_params[0], exact, quiet,
                                         handler)
                        for member in instance
                    )

                    if base_hint in (_th.Iterable, _abc.Iterable,
                                     _th.Iterator, _abc.Iterator):
                        return conform_gen

                    if exact:
                        if base_hint is type(conform_gen):
                            return conform_gen
                    else:
                        if isinstance_quiet(conform_gen, base_hint):
                            return conform_gen
                    try:
                        return base_hint(conform_gen)
                    except (TypeError, ValueError):
                        pass
                else:
                    if exact:
                        if base_hint is type(instance):
                            return instance
                    else:
                        if isinstance_quiet(instance, base_hint):
                            return instance
                    try:
                        return base_hint(instance)
                    except (TypeError, ValueError):
                        pass
        elif isnone(base_hint) and instance is None:
            return instance

    if quiet:
        return instance

    raise TypeError("could not conform")