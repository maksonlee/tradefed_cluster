load("//tradefed_cluster:adapter.bzl", "py2and3_test", "py_appengine_library", "py_appengine_test", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

PY_APPENGINE_TEST_ENVS = [{
    "libraries": {
        "endpoints": "latest",
    },
    "runtime": "python27",
}]

py_library(
    name = "command_util",
    srcs = [
        "command_util.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        third_party("munch"),
        third_party("six"),
    ],
)

py2and3_test(
    name = "command_util_test",
    srcs = [
        "command_util_test.py",
    ],
    deps = [
        ":command_util",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "email_sender_lib",
    srcs = [
        "email_sender.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster/services:mailer_lib",
        third_party("jinja2"),
    ],
)

py_appengine_test(
    name = "email_sender_test",
    srcs = [
        "email_sender_test.py",
    ],
    data = [
        ":testdata",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":email_sender_lib",
        third_party("mock"),
        "//tradefed_cluster:testbed_dependent_test_lib",
    ],
)

py_library(
    name = "env_util_lib",
    srcs = [
        "env_util.py",
    ],
)

py_library(
    name = "metric_util_lib",
    srcs = [
        "metric_util.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster/plugins:metric_client_lib",
    ],
)

py_appengine_library(
    name = "pubsub_client_lib",
    srcs = [
        "pubsub_client.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//third_party/py/google/auth:__init__",
        third_party("googleapiclient"),
    ],
)

py_appengine_test(
    name = "pubsub_client_test",
    srcs = [
        "pubsub_client_test.py",
    ],
    deps = [
        ":pubsub_client_lib",
        third_party("mock"),
        "//tradefed_cluster:testbed_dependent_test_lib",
    ],
)

filegroup(
    name = "testdata",
    srcs = glob([
        "testdata/**",
    ]),
)

py_library(
    name = "ndb_shim_lib",
    srcs = [
        "ndb_shim.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":google_import_fixer",
        third_party("google/cloud/ndb:google3_ndb"),
    ],
)

py_library(
    name = "ndb_test_lib",
    testonly = True,
    srcs = [
        "ndb_test_lib.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":datastore_emulator_lib",
        ":ndb_shim_lib",
        "//net/grpc/python:use_insecure_channel",  # buildcleaner:keep
        third_party("absl/testing:absltest"),
        third_party("google/auth:app_engine"),
        third_party("google/cloud/datastore:datastore_grpc_alternative"),
    ],
)

py_library(
    name = "datastore_emulator_lib",
    testonly = True,
    srcs = [
        "datastore_emulator.py",
    ],
    deps = [
        third_party("googledatastore/v1:datastore_emulator"),
    ],
)

py2and3_test(
    name = "datastore_emulator_test",
    srcs = [
        "datastore_emulator_test.py",
    ],
    deps = [
        ":datastore_emulator_lib",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "google_import_fixer",
    srcs = ["google_import_fixer.py"],
    srcs_version = "PY2AND3",
    visibility = ["//third_party/py/multitest_transport:__subpackages__"],
)

