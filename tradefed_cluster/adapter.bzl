"""Bazel adapter for build rules.

This file maps build rules used in the project to Bazel build rules.
"""

load("@com_google_protobuf//:protobuf.bzl", _py_proto_library = "py_proto_library")
load("@rules_appengine//appengine:py_appengine.bzl", _py_appengine_binary = "py_appengine_binary", _py_appengine_test = "py_appengine_test")
load("@rules_proto//proto:defs.bzl", _proto_library = "proto_library")
load("@rules_python//python:defs.bzl", _py_binary = "py_binary", _py_library = "py_library", _py_test = "py_test")
load("@third_party//:requirements.bzl", _requirement = "requirement")
load("@third_party_py3//:requirements.bzl", _requirement_py3 = "requirement")

# A map to convert library aliases to PyPI package names.
# When adding a new dependency, one should make the following changes:
# 1) Add a mapping from a library alias (e.g. cloudstorage) to PyPI package name (e.g. google-cloud-storage).
# 2) Add a new PyPI package to requirements.txt (or requirements_py3.txt).
PACKAGE_MAP = {
    "absl": "absl-py",
    "absl/testing": "absl-py",
    "antlr3": "antlr3-python-runtime",
    "apiclient": "google-api-python-client",
    "cloudstorage": "google-cloud-storage",
    "concurrent": "futures",
    "dateutil": "python-dateutil",
    "docker": "docker",
    "endpoints": "google-endpoints",
    "google/auth": "google-auth",
    "google/cloud/storage": "google-cloud-storage",
    "google/oauth2": "google-auth",
    "googleapiclient": "google-api-python-client",
    "hamcrest": "PyHamcrest",
    "jinja2": "Jinja2",
    "lazy_object_proxy": "lazy-object-proxy",
    "oauth2client_1_4_12_plus": "oauth2client",
    "oauth2client_4_0": "oauth2client",
    "portpicker": "portpicker",
    "requests": "requests",
    "retry": "retry",
    "webtest": "WebTest",
    "yaml": "PyYAML",
}

def _dedup_deps(kwargs):
    if "deps" in kwargs:
        # Dedup deps
        deps = kwargs["deps"]
        kwargs["deps"] = {dep: True for dep in deps}.keys()

def _fileset_impl(ctx):
    remap = {}
    for a, b in ctx.attr.maps.items():
        remap[ctx.label.relative(a)] = b
    cmd = ""
    outs = []
    for f in ctx.files.srcs:
        # Use the label of file, which is more reliable than fiddling with paths.
        # If f is not a source file, then the rule that generates f may have
        # a different name.
        label = f.owner if f.is_source else f.owner.relative(f.basename)
        if label in remap:
            dest = remap[label] + "/" + f.basename
            fd = ctx.actions.declare_file(dest)
            cmd += "mkdir -p " + fd.dirname + "\n"
            cmd += "cp -f '" + f.path + "' '" + fd.path + "'\n"
            outs.append(fd)
    script = ctx.actions.declare_file(ctx.label.name + ".cmd.sh")
    ctx.actions.write(output = script, content = cmd)

    # Execute the command
    ctx.actions.run_shell(
        inputs = (
            ctx.files.srcs +
            [script]
        ),
        outputs = outs,
        mnemonic = "fileset",
        command = "set -e; sh " + script.path,
        use_default_shell_env = True,
    )
    return DefaultInfo(files = depset(outs))

_fileset = rule(
    attrs = {
        "srcs": attr.label_list(allow_files = True),
        "maps": attr.string_dict(mandatory = True),
    },
    executable = False,
    implementation = _fileset_impl,
)

def Fileset(name, out, entries, visibility = None, **kwargs):
    """Builds a directory structure with a user-defined layout.

    Args:
        name: a unique name for a target.
        out: a name of the directory this Fileset creates.
        entries: a list of FilesetEntry objects.
        visibility: visibility.
        **kwargs: unused args.
    """
    srcs = []
    maps = {}
    for entry in entries:
        srcs += entry.files
        for label in entry.files:
            maps[label] = entry.destdir
    _fileset(
        name = name,
        srcs = srcs,
        maps = maps,
        visibility = visibility,
    )

def FilesetEntry(files, destdir):
    return struct(files = files, destdir = destdir)

proto_library = _proto_library

def py_appengine_binary(**kwargs):
    kwargs.pop("envs", None)
    if "srcs" not in kwargs:
        kwargs["srcs"] = ["__init__.py"]
    _py_appengine_binary(**kwargs)

def py_appengine_library(**kwargs):
    kwargs.pop("envs", None)
    _py_library(**kwargs)

def py_appengine_test(**kwargs):
    kwargs.pop("envs", None)
    kwargs.pop("python_version", None)
    kwargs.pop("use_public_sdk", None)
    _py_appengine_test(**kwargs)

def py_binary(**kwargs):
    _dedup_deps(kwargs)
    _py_binary(**kwargs)

def py_library(**kwargs):
    _dedup_deps(kwargs)
    _py_library(**kwargs)

def py_proto_library(**kwargs):
    kwargs.pop("api_version", None)
    kwargs.pop("deps", None)
    _py_proto_library(**kwargs)

def py_test(**kwargs):
    _dedup_deps(kwargs)
    _py_test(**kwargs)

def py2and3_test(**kwargs):
    _dedup_deps(kwargs)
    _py_test(**kwargs)

def pytype_strict_binary(name, **kwargs):
    """An adapter for pytype_strict_binary rule.

    Args:
        name: a unique name for a target.
        **kwargs: unused args.
    """
    kwargs.pop("disable_py3_errors", None)
    test_lib = kwargs.pop("test_lib", None)
    if test_lib:
        _py_library(
            name = name + ".testonly_lib",
            testonly = 1,
            visibility = ["//visibility:private"],
            deps = [name],
        )
    _py_binary(name = name, **kwargs)

def third_party(package_name):
    """A function to map a library alias to a label."""
    package_name = PACKAGE_MAP.get(package_name.split(":")[0], package_name)
    return _requirement(package_name)

def third_party_py3(package_name):
    """A function to map a Python 3 library alias to a label."""
    package_name = PACKAGE_MAP.get(package_name.split(":")[0], package_name)
    return _requirement_py3(package_name)

def zip_dir(**kwargs):
    # TODO: Make this rule work with Bazel.
    pass
