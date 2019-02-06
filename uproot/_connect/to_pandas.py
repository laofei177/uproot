#!/usr/bin/env python

# Copyright (c) 2019, IRIS-HEP
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import itertools
import functools
import operator

import numpy

import awkward as awkwardbase

from uproot.interp.jagged import asjagged
from uproot.interp.numerical import asdtype
from uproot.interp.objects import asobj
from uproot.interp.objects import astable

class TTreeMethods_pandas(object):
    def __init__(self, tree):
        self._tree = tree

    def df(self, branches=None, namedecode="utf-8", entrystart=None, entrystop=None, flatten=True, flatname=None, cache=None, basketcache=None, keycache=None, executor=None, blocking=True):
        import pandas
        return self._tree.arrays(branches=branches, outputtype=pandas.DataFrame, namedecode=namedecode, entrystart=entrystart, entrystop=entrystop, flatten=flatten, flatname=flatname, cache=cache, basketcache=basketcache, keycache=keycache, executor=executor, blocking=blocking)

def default_flatname(branchname, fieldname, index):
    out = branchname
    if not isinstance(branchname, str):
        out = branchname.decode("utf-8")
    if fieldname is not None:
        out += "." + fieldname
    if index != ():
        out += "[" + "][".join(str(x) for x in index) + "]"
    return out

def futures2df(futures, outputtype, entrystart, entrystop, flatten, flatname, awkward):
    import pandas

    if flatname is None:
        flatname = default_flatname

    if not flatten or all(interpretation.__class__ is not asjagged for name, interpretation, future in futures):
        columns = []
        data = {}
        for name, interpretation, future in futures:
            array = future()

            if isinstance(interpretation, asobj) and isinstance(interpretation.content, astable):
                interpretation = interpretation.content
            if isinstance(interpretation, astable) and isinstance(interpretation.content, asdtype):
                interpretation = interpretation.content

            if isinstance(interpretation, asdtype):
                if interpretation.todims == ():
                    if interpretation.todtype.names is None:
                        fn = flatname(name, None, ())
                        columns.append(fn)
                        data[fn] = array
                    else:
                        for nn in interpretation.todtype.names:
                            if not nn.startswith(" "):
                                fn = flatname(name, nn, ())
                                columns.append(fn)
                                data[fn] = array[nn]
                else:
                    for tup in itertools.product(*[range(x) for x in interpretation.todims]):
                        if interpretation.todtype.names is None:
                            fn = flatname(name, None, tup)
                            columns.append(fn)
                            data[fn] = array[(slice(None),) + tup]
                        else:
                            for nn in interpretation.todtype.names:
                                if not nn.startswith(" "):
                                    fn = flatname(name, nn, tup)
                                    columns.append(fn)
                                    data[fn] = array[nn][(slice(None),) + tup]
            else:
                fn = flatname(name, None, ())
                columns.append(fn)
                data[fn] = list(array)     # must be serialized as a Python list for Pandas to accept it

        return outputtype(columns=columns, data=data)

    else:
        starts, stops = None, None

        needbroadcasts = []
        names = []
        interpretations = []
        arrays = []
        for name, interpretation, future in futures:
            if isinstance(interpretation, asobj) and isinstance(interpretation.content, astable):
                interpretation = interpretation.content
            if isinstance(interpretation, astable) and isinstance(interpretation.content, asdtype):
                interpretation = interpretation.content

            array = future()
            if isinstance(interpretation, asjagged):
                interpretation = interpretation.content
                if isinstance(interpretation, asobj) and isinstance(interpretation.content, astable):
                    interpretation = interpretation.content
                if isinstance(interpretation, astable) and isinstance(interpretation.content, asdtype):
                    interpretation = interpretation.content

                # justifies the assumption that array.content == array.flatten() and array.stops.max() == array.stops[-1]
                assert array._canuseoffset() and len(array.starts) > 0 and array.starts[0] == 0

                if starts is None:
                    starts = array.starts
                    stops = array.stops
                    index = array.index
                else:
                    if starts is not array.starts and not awkward.numpy.array_equal(starts, array.starts):
                        raise ValueError("cannot use flatten=True on branches with different jagged structure; explicitly select compatible branches (and pandas.merge if you want to combine different jagged structure)")

                array = array.content
                length = len(array)
                needbroadcasts.append(False)

            else:
                needbroadcasts.append(True)

            names.append(name)
            interpretations.append(interpretation)
            arrays.append(array)

        index = pandas.MultiIndex.from_arrays([index._broadcast(numpy.arange(entrystart, entrystop, dtype=numpy.int64)).content, index.content], names=["entry", "subentry"])

        df = outputtype(index=index)

        for name, interpretation, array, needbroadcast in zip(names, interpretations, arrays, needbroadcasts):
            if isinstance(interpretation, asdtype):
                if isinstance(array, awkwardbase.ObjectArray):
                    array = array.content

                if needbroadcast:
                    # Invoke jagged broadcasting to align arrays
                    originaldtype = array.dtype
                    originaldims = array.shape[1:]

                    if isinstance(array, awkwardbase.Table):
                        for nn in array.columns:
                            array[nn] = awkward.JaggedArray(starts, stops, awkward.numpy.empty(stops[-1], dtype=array[nn].dtype))._broadcast(array[nn]).content

                    else:
                        if len(originaldims) != 0:
                            array = array.view(awkward.numpy.dtype([(str(i), array.dtype) for i in range(functools.reduce(operator.mul, array.shape[1:]))])).reshape(array.shape[0])

                        array = awkward.JaggedArray(starts, stops, awkward.numpy.empty(stops[-1], dtype=array.dtype))._broadcast(array).content
                        if len(originaldims) != 0:
                            array = array.view(originaldtype).reshape((-1,) + originaldims)

                if interpretation.todims == ():
                    if interpretation.todtype.names is None:
                        fn = flatname(name, None, ())
                        df[fn] = array
                    else:
                        for nn in interpretation.todtype.names:
                            if not nn.startswith(" "):
                                fn = flatname(name, nn, ())
                                df[fn] = array[nn]
                else:
                    for tup in itertools.product(*[range(x) for x in interpretation.todims]):
                        if interpretation.todtype.names is None:
                            fn = flatname(name, None, tup)
                            df[fn] = array[(slice(None),) + tup]
                        else:
                            for nn in interpretation.todtype.names:
                                if not nn.startswith(" "):
                                    fn = flatname(name, nn, tup)
                                    df[fn] = array[nn][(slice(None),) + tup]

            else:
                fn = flatname(name, None, ())
                array = awkward.numpy.array(array, dtype=object)
                array = awkward.JaggedArray(starts, stops, awkward.numpy.empty(stops[-1], dtype=object))._broadcast(array).content
                df[fn] = array

        return df
