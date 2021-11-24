load("//tradefed_cluster:adapter.bzl", "py_library", "pytype_strict_library", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

py_library(
    name = "appengine_lib",
    srcs = [
        "appengine.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":base_lib",
    ],
)

pytype_strict_library(
    name = "base_lib",
    srcs = [
        "base.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        third_party("six"),
    ],
)

py_test(
    name = "base_test",
    srcs = [
        "base_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":base_lib",
    ],
)

py_library(
    name = "google_cloud_lib",
    srcs = [
        "google_cloud.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":base_lib",
        third_party("google-cloud-tasks"),
        third_party("six"),
    ],
)

py_test(
    name = "google_cloud_test",
    srcs = [
        "google_cloud_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":google_cloud_lib",
        third_party("mock"),
    ],
)

py_library(
    name = "metric_client_lib",
    srcs = [
        "metric_client.py",
    ],
    srcs_version = "PY2AND3",
)

pytype_strict_library(
    name = "noop_plugin_lib",
    srcs = [
        "noop_plugin.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":base_lib",
    ],
)

pytype_strict_library(
    name = "registry_lib",
    srcs = [
        "registry.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":base_lib",
        ":noop_plugin_lib",
    ],
)

py_test(
    name = "registry_test",
    srcs = [
        "registry_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":registry_lib",
        third_party("mock"),
    ],
)

