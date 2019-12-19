load("//tradefed_cluster:adapter.bzl", "py_appengine_library", "py_appengine_test", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

PY_APPENGINE_ENVS = [{"runtime": "python27"}]

PY_APPENGINE_TEST_ENVS = [{
    "libraries": {
        "PIL": "latest",
        "pycrypto": "2.6",
    },
    "runtime": "python27",
}]

py_appengine_library(
    name = "base_lib",
    srcs = [
        "base.py",
    ],
    envs = PY_APPENGINE_ENVS,
)

py_appengine_test(
    name = "base_test",
    srcs = [
        "base_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":base_lib",
    ],
)

py_library(
    name = "metric_client_lib",
    srcs = [
        "metric_client.py",
    ],
)

py_appengine_library(
    name = "noop_plugin_lib",
    srcs = [
        "noop_plugin.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":base_lib",
    ],
)

py_appengine_library(
    name = "registry_lib",
    srcs = [
        "registry.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":base_lib",
        ":noop_plugin_lib",
    ],
)

py_appengine_test(
    name = "registry_test",
    srcs = [
        "registry_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":registry_lib",
        third_party("mock"),
    ],
)
