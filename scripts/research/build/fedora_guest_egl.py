#!/usr/bin/env python3
"""Small software-only EGL/GLES runtime check for the emulated Fedora rootfs.

Creates a 4x4 pbuffer, clears it, and reads back one pixel. This is not a GPU
benchmark, shader/conformance test, or evidence that Adreno hardware works.
Run it through the ARM64 interpreter in the assembled rootfs. No external
commands, device writes, persistent graphics overrides or tuning are used.
"""

import ctypes as C
import json
import os
import platform
import sys


def run():
    os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
    os.environ["GALLIUM_DRIVER"] = "llvmpipe"
    os.environ["LP_NUM_THREADS"] = "1"
    os.environ["EGL_PLATFORM"] = "surfaceless"
    egl = C.CDLL("libEGL.so.1")
    gl = C.CDLL("libGLESv2.so.2")
    handle, integer, boolean = C.c_void_p, C.c_int32, C.c_uint32

    def function(library, name, result, *arguments):
        value = getattr(library, name)
        value.restype = result
        value.argtypes = list(arguments)
        return value

    error = function(egl, "eglGetError", integer)
    get_display = function(egl, "eglGetPlatformDisplay", handle,
                           C.c_uint32, handle, C.POINTER(C.c_ssize_t))
    initialize = function(egl, "eglInitialize", boolean,
                          handle, C.POINTER(integer), C.POINTER(integer))
    choose = function(egl, "eglChooseConfig", boolean,
                      handle, C.POINTER(integer), C.POINTER(handle), integer,
                      C.POINTER(integer))
    bind = function(egl, "eglBindAPI", boolean, C.c_uint32)
    create_context = function(egl, "eglCreateContext", handle,
                              handle, handle, handle, C.POINTER(integer))
    create_surface = function(egl, "eglCreatePbufferSurface", handle,
                              handle, handle, C.POINTER(integer))
    make_current = function(egl, "eglMakeCurrent", boolean,
                            handle, handle, handle, handle)
    destroy_surface = function(egl, "eglDestroySurface", boolean, handle, handle)
    destroy_context = function(egl, "eglDestroyContext", boolean, handle, handle)
    terminate = function(egl, "eglTerminate", boolean, handle)
    gl_string = function(gl, "glGetString", C.c_char_p, C.c_uint32)
    clear_color = function(gl, "glClearColor", None,
                           C.c_float, C.c_float, C.c_float, C.c_float)
    clear = function(gl, "glClear", None, C.c_uint32)
    finish = function(gl, "glFinish", None)
    read_pixels = function(gl, "glReadPixels", None, integer, integer,
                           integer, integer, C.c_uint32, C.c_uint32, handle)
    gl_error = function(gl, "glGetError", C.c_uint32)

    def require(value, operation):
        if not value:
            raise RuntimeError(f"{operation} failed; EGL error 0x{error():04x}")
        return value

    # EGL_PLATFORM_SURFACELESS_MESA, an EGL 1.5 platform entry point.
    display = require(get_display(0x31DD, None, None), "eglGetPlatformDisplay")
    context = surface = None
    initialized = False
    try:
        major, minor = integer(), integer()
        require(initialize(display, C.byref(major), C.byref(minor)), "eglInitialize")
        initialized = True
        # RGBA8, pbuffer support, OpenGL ES 2 renderable configuration.
        attributes = (integer * 13)(
            0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8,
            0x3033, 0x0001, 0x3040, 0x0004, 0x3038)
        configurations, count = (handle * 1)(), integer()
        require(choose(display, attributes, configurations, 1, C.byref(count)),
                "eglChooseConfig")
        require(count.value == 1, "RGBA8 pbuffer configuration")
        require(bind(0x30A0), "eglBindAPI(OpenGL ES)")
        context_attributes = (integer * 3)(0x3098, 2, 0x3038)
        context = require(create_context(display, configurations[0], None,
                                         context_attributes), "eglCreateContext")
        surface_attributes = (integer * 5)(0x3057, 4, 0x3056, 4, 0x3038)
        surface = require(create_surface(display, configurations[0],
                                         surface_attributes), "eglCreatePbufferSurface")
        require(make_current(display, surface, surface, context), "eglMakeCurrent")
        strings = {
            key: (gl_string(token) or b"").decode("utf-8", "replace")
            for key, token in (("vendor", 0x1F00), ("renderer", 0x1F01),
                               ("version", 0x1F02))
        }
        clear_color(0.25, 0.5, 0.75, 1.0)
        clear(0x00004000)  # GL_COLOR_BUFFER_BIT
        finish()
        pixel = (C.c_ubyte * 4)()
        read_pixels(0, 0, 1, 1, 0x1908, 0x1401, pixel)  # RGBA / UNSIGNED_BYTE
        failure = gl_error()
        expected, actual = [64, 128, 191, 255], list(pixel)
        software = "llvmpipe" in strings["renderer"].lower()
        matched = all(abs(a - b) <= 1 for a, b in zip(actual, expected))
        return {
            "schema_version": 1,
            "test": "software EGL pbuffer clear and pixel readback",
            "machine": platform.machine(),
            "egl_version": f"{major.value}.{minor.value}",
            **strings,
            "expected_rgba8": expected,
            "readback_rgba8": actual,
            "component_tolerance": 1,
            "gl_error": failure,
            "software_renderer_confirmed": software,
            "passed": bool(software and matched and failure == 0),
            "hardware_acceleration_tested": False,
            "native_display_tested": False,
        }
    finally:
        if initialized:
            make_current(display, None, None, None)
            if surface:
                destroy_surface(display, surface)
            if context:
                destroy_context(display, context)
            terminate(display)


if __name__ == "__main__":
    try:
        report = run()
    except Exception as exc:
        report = {"schema_version": 1, "passed": False, "error": str(exc),
                  "hardware_acceleration_tested": False}
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)
