load("//tradefed_cluster:adapter.bzl", "py2and3_test", "py_appengine_library", "py_appengine_test", "pytype_strict_library", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

pytype_strict_library(
    name = "file_storage_lib",
    srcs = [
        "file_storage.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster/plugins:base_lib",
        third_party("protorpc:protorpc_all"),
    ],
)

py2and3_test(
    name = "file_storage_test",
    srcs = [
        "file_storage_test.py",
    ],
    deps = [
        ":file_storage_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
    ],
)

pytype_strict_library(
    name = "mailer_lib",
    srcs = [
        "mailer.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster:env_config_lib",
        third_party("protorpc:protorpc_all"),
    ],
)

py2and3_test(
    name = "mailer_test",
    srcs = [
        "mailer_test.py",
    ],
    deps = [
        ":mailer_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "task_scheduler_lib",
    srcs = [
        "task_scheduler.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_appengine_test(
    name = "task_scheduler_test",
    srcs = [
        "task_scheduler_test.py",
    ],
    deps = [
        ":task_scheduler_lib",
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("mock"),
    ],
)

