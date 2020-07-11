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
        # TODO: switch from oauth2client to google.auth
        third_party("googleapiclient:googleapiclient_with_oauth2client"),
        third_party("oauth2client:titanium"),
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

py_appengine_library(
    name = "ndb_shim_lib",
    srcs = [
        "ndb_shim.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":google_import_fixer",
        third_party("google/cloud/ndb"),
    ],
)

py_appengine_library(
    name = "google_import_fixer",
    srcs = ["google_import_fixer.py"],
    srcs_version = "PY2AND3",
    visibility = [
        "//third_party/py/multitest_transport:__subpackages__",
        "//tradefed_cluster:__subpackages__",
    ],
)
