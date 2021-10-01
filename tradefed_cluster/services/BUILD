load("//tradefed_cluster:adapter.bzl", "pytype_strict_library", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

pytype_strict_library(
    name = "app_manager_lib",
    srcs = [
        "app_manager.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster:env_config_lib",
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "app_manager_test",
    srcs = [
        "app_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":app_manager_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

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

py_test(
    name = "file_storage_test",
    srcs = [
        "file_storage_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":file_storage_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster/plugins:base_lib",
    ],
)

pytype_strict_library(
    name = "acl_service_lib",
    srcs = [
        "acl_service.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//third_party/py/endpoints:api_request",
        "//third_party/py/endpoints:endpoints_dispatcher",
        "//third_party/py/endpoints:endpoints_library",
        "//third_party/py/enum",
        "//tradefed_cluster:datastore_entities_lib",
        "//tradefed_cluster:env_config_lib",
    ],
)

py_test(
    name = "acl_service_test",
    srcs = [
        "acl_service_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY2AND3",
    deps = [
        ":acl_service_lib",
        third_party("absl/testing:absltest"),
        "//third_party/py/endpoints:endpoints_library",
        "//third_party/py/protorpc:protorpc_all",
        "//tradefed_cluster:api_common_lib",
        "//tradefed_cluster:datastore_test_util_lib",
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
        "//third_party/py/webtest",
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

py_test(
    name = "mailer_test",
    srcs = [
        "mailer_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":mailer_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "task_scheduler_lib",
    srcs = [
        "task_scheduler.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        "//tradefed_cluster:common_lib",
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster/plugins:base_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "task_scheduler_test",
    srcs = [
        "task_scheduler_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":task_scheduler_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster:env_config_lib",
        "//tradefed_cluster:testbed_dependent_test_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("mock"),
    ],
)
