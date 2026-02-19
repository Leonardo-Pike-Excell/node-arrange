# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import ctypes
import platform

import bpy


class bNodeStack(ctypes.Structure):
    vec: ctypes.c_float * 4
    min: ctypes.c_float
    max: ctypes.c_float
    data: ctypes.c_void_p
    hasinput: ctypes.c_short
    hasoutput: ctypes.c_short
    datatype: ctypes.c_short
    sockettype: ctypes.c_short
    is_copy: ctypes.c_short
    external: ctypes.c_short
    _pad: ctypes.c_char * 4


class bNodeSocketRuntimeHandle(ctypes.Structure):
    if platform.system() == 'Windows':
        _pad0: ctypes.c_char * 8
    declaration: ctypes.c_void_p
    changed_flag: ctypes.c_uint32
    total_inputs: ctypes.c_short
    _pad1: ctypes.c_char * 2
    location: ctypes.c_float * 2


class bNodeSocket(ctypes.Structure):
    next: ctypes.c_void_p
    prev: ctypes.c_void_p
    prop: ctypes.c_void_p
    identifier: ctypes.c_char * 64
    name: ctypes.c_char * 64
    storage: ctypes.c_void_p
    in_out: ctypes.c_short
    typeinfo: ctypes.c_void_p
    idname: ctypes.c_char * 64
    default_value: ctypes.c_void_p
    _pad: ctypes.c_char * 4
    label: ctypes.c_char * 64
    description: ctypes.c_char * 64
    short_label: ctypes.c_char * 64
    default_attribute_name: ctypes.POINTER(ctypes.c_char)
    own_index: ctypes.c_int
    to_index: ctypes.c_int
    link: ctypes.c_void_p
    ns: bNodeStack
    runtime: ctypes.POINTER(bNodeSocketRuntimeHandle)


for cls in (bNodeStack, bNodeSocketRuntimeHandle, bNodeSocket):
    cls._fields_ = [(k, eval(v)) for k, v in cls.__annotations__.items()]
