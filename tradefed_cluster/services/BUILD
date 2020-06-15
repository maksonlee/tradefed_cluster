load("//tradefed_cluster:adapter.bzl", "py_appengine_library", "py_appengine_test", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

py_appengine_library(
    name = "task_scheduler_lib",
    srcs = [
        "task_scheduler.py",
    ],
    srcs_version = "PY2AND3",
)

py_appengine_test(
    name = "task_scheduler_test",
    srcs = [
        "task_scheduler_test.py",
    ],
    deps = [
        ":task_scheduler_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

