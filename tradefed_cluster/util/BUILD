load("//tradefed_cluster:adapter.bzl", "py_library", "pytype_strict_library", "third_party")

package(
    default_applicable_licenses = ["//tradefed_cluster:license"],
    default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"],
)

licenses(["notice"])

pytype_strict_library(
    name = "auth_lib",
    srcs = [
        "auth.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        third_party("google/auth:compute_engine/__init__"),
        third_party("google/auth:transport/requests"),
    ],
)

pytype_strict_library(
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

py_test(
    name = "command_util_test",
    srcs = [
        "command_util_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_util",
        third_party("mock"),
    ],
)

pytype_strict_library(
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

py_test(
    name = "email_sender_test",
    srcs = [
        "email_sender_test.py",
    ],
    data = [
        ":testdata",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":email_sender_lib",
        third_party("mock"),
        "//tradefed_cluster:testbed_dependent_test_lib",
    ],
)

pytype_strict_library(
    name = "env_util_lib",
    srcs = [
        "env_util.py",
    ],
    deps = ["//third_party/py/google/appengine/api:full_app_id"],
)

pytype_strict_library(
    name = "metric_util_lib",
    srcs = [
        "metric_util.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster/plugins:metric_client_lib",
    ],
)

pytype_strict_library(
    name = "ndb_util_lib",
    srcs = [
        "ndb_util.py",
    ],
    deps = [
        ":ndb_shim_lib",
    ],
)

py_test(
    name = "ndb_util_test",
    srcs = [
        "ndb_util_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":ndb_shim_lib",
        ":ndb_util_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
    ],
)

pytype_strict_library(
    name = "pubsub_client_lib",
    srcs = [
        "pubsub_client.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//pyglib:retry",
        "//third_party/py/google/auth:__init__",
        third_party("googleapiclient"),
    ],
)

py_test(
    name = "pubsub_client_test",
    srcs = [
        "pubsub_client_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":pubsub_client_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

pytype_strict_library(
    name = "elasticsearch_client_lib",
    srcs = [
        "elasticsearch_client.py",
    ],
    srcs_version = "PY3",
    deps = [
        "//third_party/py/elasticsearch",
    ],
)

py_test(
    name = "elasticsearch_client_test",
    srcs = [
        "elasticsearch_client_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":elasticsearch_client_lib",
        "//third_party/py/elasticsearch",
    ],
)

filegroup(
    name = "testdata",
    srcs = glob([
        "testdata/**",
    ]),
)

pytype_strict_library(
    name = "ndb_shim_lib",
    srcs = [
        "ndb_shim.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        third_party("google/auth:__init__"),
        third_party("google/auth:compute_engine/__init__"),
        third_party("google/cloud/ndb"),
        third_party("six"),
    ],
)

pytype_strict_library(
    name = "ndb_test_lib",
    testonly = True,
    srcs = [
        "ndb_test_lib.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":datastore_emulator_lib",
        ":ndb_shim_lib",
        third_party("absl/testing:absltest"),
        third_party("google/auth:credentials"),
        third_party("google/cloud/datastore"),
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

py_test(
    name = "datastore_emulator_test",
    srcs = [
        "datastore_emulator_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_emulator_lib",
        third_party("mock"),
    ],
)
