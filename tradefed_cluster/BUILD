load("//tools/build_defs/testing:bzl_library.bzl", "bzl_library")

# A test infra software for Android testing labs.
load("//tradefed_cluster:adapter.bzl", "py_library", "pytype_strict_library", "third_party")

package(default_visibility = [":tradefed_cluster_clients"])

licenses(["notice"])

exports_files(["LICENSE"])

package_group(
    name = "tradefed_cluster",
    packages = [
        "//tradefed_cluster/...",
    ],
)

package_group(
    name = "tradefed_cluster_clients",
    includes = [
        ":tradefed_cluster",
    ],
    packages = [
        "//third_party/py/multitest_transport/...",
    ],
)

pytype_strict_library(
    name = "acl_check_api_lib",
    srcs = [
        "acl_check_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/services:acl_service_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "acl_check_api_test",
    srcs = [
        "acl_check_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/services:acl_service_lib",
        third_party("protorpc:protorpc_all"),
    ],
)

pytype_strict_library(
    name = "affinity_manager_lib",
    srcs = [
        "affinity_manager.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

py_test(
    name = "affinity_manager_test",
    srcs = [
        "affinity_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":affinity_manager_lib",
        ":testbed_dependent_test_lib",
    ],
)

pytype_strict_library(
    name = "api_common_lib",
    srcs = [
        "api_common.py",
    ],
    deps = [
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("google/auth:__init__"),
        third_party("google/auth:compute_engine/__init__"),
        third_party("google/cloud/ndb:google3_ndb"),
    ],
)

pytype_strict_library(
    name = "api_lib",
    srcs = [
        "api.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":acl_check_api_lib",
        ":cluster_api_lib",
        ":cluster_device_api_lib",
        ":cluster_host_api_lib",
        ":command_attempt_api_lib",
        ":command_event_api_lib",
        ":command_task_api_lib",
        ":coordinator_api_lib",
        ":device_blocklist_api_lib",
        ":device_snapshot_api_lib",
        ":env_config_lib",
        ":filter_hint_api_lib",
        ":host_event_api_lib",
        ":lab_management_api_lib",
        ":predefined_message_api_lib",
        ":report_api_lib",
        ":request_api_lib",
        ":run_target_api_lib",
        ":test_harness_image_api_lib",
        third_party("endpoints:endpoints_library"),
    ],
)

pytype_strict_library(
    name = "api_messages_lib",
    srcs = [
        "api_messages.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        ":common_lib",
        third_party("protorpc:protorpc_all"),
        third_party("six"),
    ],
)

py_test(
    name = "api_messages_test",
    srcs = [
        "api_messages_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":api_test_lib",
        ":datastore_entities_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "api_test_lib",
    testonly = 1,
    srcs = [
        "api_test.py",
    ],
    deps = [
        ":acl_check_api_lib",
        ":api_lib",
        ":cluster_api_lib",
        ":cluster_device_api_lib",
        ":cluster_host_api_lib",
        ":command_attempt_api_lib",
        ":command_event_api_lib",
        ":command_task_api_lib",
        ":coordinator_api_lib",
        ":device_blocklist_api_lib",
        ":device_snapshot_api_lib",
        ":filter_hint_api_lib",
        ":host_event_api_lib",
        ":lab_management_api_lib",
        ":predefined_message_api_lib",
        ":report_api_lib",
        ":request_api_lib",
        ":run_target_api_lib",
        ":test_harness_image_api_lib",
        ":testbed_dependent_test_lib",
        third_party("endpoints:endpoints_library"),
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

pytype_strict_library(
    name = "app_lib",
    visibility = ["//visibility:public"],
    deps = [
        ":env_config_lib",
        ":server_lib",
        third_party("pytz"),
        "//tradefed_cluster/plugins:registry_lib",
        "//tradefed_cluster/util:env_util_lib",
    ],
)

pytype_strict_library(
    name = "cluster_api_lib",
    srcs = [
        "cluster_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_manager_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "cluster_api_test",
    srcs = [
        "cluster_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "cluster_device_api_lib",
    srcs = [
        "cluster_device_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        ":note_manager_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "cluster_device_api_test",
    srcs = [
        "cluster_device_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "cluster_host_api_lib",
    srcs = [
        "cluster_host_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        ":harness_image_metadata_syncer_lib",
        ":host_event_lib",
        ":note_manager_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "cluster_host_api_test",
    srcs = [
        "cluster_host_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "lab_management_api_lib",
    srcs = [
        "lab_management_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "lab_management_api_test",
    srcs = [
        "lab_management_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "command_attempt_api_lib",
    srcs = [
        "command_attempt_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "command_attempt_api_test",
    srcs = [
        "command_attempt_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "command_attempt_monitor_lib",
    srcs = [
        "command_attempt_monitor.py",
    ],
    deps = [
        ":command_event_lib",
        ":command_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "command_attempt_monitor_test",
    srcs = [
        "command_attempt_monitor_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_attempt_monitor_lib",
        ":command_event_test_util",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "command_error_type_config_lib",
    srcs = [
        "command_error_type_config.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_test(
    name = "command_error_type_config_test",
    srcs = [
        "command_error_type_config_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_error_type_config_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//third_party/py/absl/testing:parameterized",
    ],
)

pytype_strict_library(
    name = "command_event_api_lib",
    srcs = [
        "command_event_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":command_event_handler_lib",
        ":common_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "command_event_api_test",
    srcs = [
        "command_event_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "command_event_handler_lib",
    srcs = [
        "command_event_handler.py",
    ],
    deps = [
        ":command_event_lib",
        ":command_lib",
        ":commander_lib",
        ":common_lib",
        ":metric_lib",
        ":request_sync_monitor_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        third_party("flask"),
        third_party("six"),
    ],
)

py_test(
    name = "command_event_handler_test",
    timeout = "long",
    srcs = [
        "command_event_handler_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_event_handler_lib",
        ":command_event_test_util",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

pytype_strict_library(
    name = "command_event_lib",
    srcs = [
        "command_event.py",
    ],
    deps = [
        ":command_error_type_config_lib",
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_test(
    name = "command_event_test",
    srcs = [
        "command_event_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_event_lib",
        ":command_event_test_util",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "command_event_test_util",
    srcs = [
        "command_event_test_util.py",
    ],
    deps = [
        ":command_event_lib",
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "command_lib",
    srcs = [
        "command_file.py",
        "command_manager.py",
        "command_monitor.py",
    ],
    deps = [
        ":api_messages_lib",
        ":command_event_lib",
        ":command_task_store_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_manager_lib",
        "//tradefed_cluster/plugins:base_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
        third_party("protorpc:protorpc_all"),
        third_party("six"),
        third_party("typing"),
    ],
)

py_test(
    name = "command_manager_test",
    srcs = [
        "command_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":command_event_test_util",
        ":command_lib",
        ":command_task_store_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_manager_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("hamcrest"),
        third_party("mock"),
    ],
)

py_test(
    name = "command_monitor_test",
    srcs = [
        "command_monitor_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

pytype_strict_library(
    name = "command_task_api_lib",
    srcs = [
        "command_task_api.py",
    ],
    deps = [
        ":affinity_manager_lib",
        ":api_common_lib",
        ":api_messages_lib",
        ":command_lib",
        ":command_task_matcher_lib",
        ":command_task_store_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_manager_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_manager_lib",
        "//tradefed_cluster/util:command_util",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("grpc"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "command_task_api_test",
    srcs = [
        "command_task_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":affinity_manager_lib",
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "command_task_matcher_lib",
    srcs = [
        "command_task_matcher.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        third_party("six"),
    ],
)

py_test(
    name = "command_task_matcher_test",
    srcs = [
        "command_task_matcher_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":command_task_matcher_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "test_harness_image_api_lib",
    srcs = [
        "test_harness_image_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "test_harness_image_api_test",
    srcs = [
        "test_harness_image_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "command_task_store_lib",
    srcs = [
        "command_task_store.py",
    ],
    deps = [
        ":affinity_manager_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

py_test(
    name = "command_task_store_test",
    srcs = [
        "command_task_store_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_task_store_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "commander_lib",
    srcs = [
        "commander.py",
    ],
    deps = [
        ":command_lib",
        ":command_task_store_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_manager_lib",
        "//tradefed_cluster/util:command_util",
        third_party("flask"),
        third_party("six"),
    ],
)

py_test(
    name = "commander_test",
    srcs = [
        "commander_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":command_event_test_util",
        ":commander_lib",
        ":datastore_test_util_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "common_lib",
    srcs = [
        "common.py",
    ],
    data = [
        ":email_templates",
    ],
    visibility = ["//visibility:public"],
    deps = [
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
        third_party("retry"),
        third_party("six"),
    ],
)

py_test(
    name = "common_test",
    srcs = [
        "common_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":common_lib",
        third_party("six"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "config_syncer_gcs_to_ndb_lib",
    srcs = [
        "config_syncer_gcs_to_ndb.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":env_config_lib",
        "//tradefed_cluster/configs:lab_config_lib",
        "//tradefed_cluster/configs:unified_lab_config_lib",
        "//tradefed_cluster/plugins:base_lib",
        "//tradefed_cluster/services:acl_service_lib",
        "//tradefed_cluster/services:file_storage_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
        third_party("ansible"),
    ],
)

pytype_strict_library(
    name = "harness_image_metadata_syncer_lib",
    srcs = [
        "harness_image_metadata_syncer.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":env_config_lib",
        "//tradefed_cluster/util:auth_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
        third_party("google/auth:__init__"),
        third_party("google/auth:compute_engine/__init__"),
        third_party("requests"),
    ],
)

pytype_strict_library(
    name = "harness_update_scheduler_lib",
    srcs = [
        "harness_update_scheduler.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "config_syncer_gcs_to_ndb_test",
    srcs = [
        "config_syncer_gcs_to_ndb_test.py",
    ],
    data = [
        "test_yaml/dhcp.yaml",
        "test_yaml/dockerized-tf.yaml",
        "test_yaml/hosts",
        "test_yaml/lab-config-with-duplicated-cluster.yaml",
        "test_yaml/presubmit-dockerized-tf.yaml",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":config_syncer_gcs_to_ndb_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":testbed_dependent_test_lib",
        third_party("cloudstorage"),
        third_party("six"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "coordinator_api_lib",
    srcs = [
        "coordinator_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":command_attempt_monitor_lib",
        ":command_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":request_sync_monitor_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "coordinator_api_test",
    srcs = [
        "coordinator_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        ":request_sync_monitor_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "datastore_entities_lib",
    srcs = [
        "datastore_entities.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        "//tradefed_cluster/util:ndb_util_lib",
        third_party("dateutil"),
        third_party("six"),
    ],
)

py_test(
    name = "datastore_entities_test",
    srcs = [
        "datastore_entities_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "datastore_util_lib",
    srcs = [
        "datastore_util.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("six"),
    ],
)

py_test(
    name = "datastore_util_test",
    srcs = [
        "datastore_util_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":datastore_util_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("six"),
    ],
)

pytype_strict_library(
    name = "datastore_test_util_lib",
    testonly = 1,
    srcs = [
        "datastore_test_util.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("six"),
    ],
)

pytype_strict_library(
    name = "device_history_cleaner_lib",
    srcs = [
        "device_history_cleaner.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "device_history_cleaner_test",
    srcs = [
        "device_history_cleaner_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":device_history_cleaner_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webtest"),
        third_party("six"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "device_info_reporter_lib",
    srcs = [
        "device_info_reporter.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/services:file_storage_lib",
        "//tradefed_cluster/util:email_sender_lib",
        third_party("cloudstorage"),
        third_party("dateutil"),
        third_party("flask"),
        third_party("six"),
    ],
)

py_test(
    name = "device_info_reporter_test",
    srcs = [
        "device_info_reporter_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":device_info_reporter_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("six"),
        third_party("webtest"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "device_manager_lib",
    srcs = [
        "device_manager.py",
    ],
    deps = [
        ":affinity_manager_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        ":harness_image_metadata_syncer_lib",
        ":host_event_lib",
        ":metric_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("six"),
    ],
)

py_test(
    name = "device_manager_test",
    srcs = [
        "device_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":device_manager_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("hamcrest"),
    ],
)

pytype_strict_library(
    name = "device_monitor_lib",
    srcs = [
        "device_monitor.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        ":env_config_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:metric_util_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        "//tradefed_cluster/util:pubsub_client_lib",
        third_party("flask"),
        third_party("lazy_object_proxy"),
        third_party("protorpc:protorpc_all"),
        third_party("six"),
    ],
)

py_test(
    name = "device_monitor_test",
    srcs = [
        "device_monitor_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":device_monitor_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("mock"),
        third_party("webtest"),
    ],
)

pytype_strict_library(
    name = "device_snapshot_api_lib",
    srcs = [
        "device_snapshot_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_info_reporter_lib",
        third_party("dateutil"),
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "device_snapshot_api_test",
    srcs = [
        "device_snapshot_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "filter_hint_api_lib",
    srcs = [
        "filter_hint_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_manager_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "filter_hint_api_test",
    srcs = [
        "filter_hint_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "device_blocklist_api_lib",
    srcs = [
        "device_blocklist_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "device_blocklist_api_test",
    srcs = [
        "device_blocklist_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        ":device_blocklist_api_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "device_blocker_lib",
    srcs = [
        "device_blocker.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":datastore_entities_lib",
    ],
)

py_test(
    name = "device_blocker_test",
    srcs = [
        "device_blocker_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":device_blocker_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

filegroup(
    name = "email_templates",
    srcs = glob([
        "email_templates/**",
    ]),
)

pytype_strict_library(
    name = "env_config_lib",
    srcs = [
        "env_config.py",
    ],
    srcs_version = "PY2AND3",
    deps = [
        ":common_lib",
        "//tradefed_cluster/plugins:metric_client_lib",
        "//tradefed_cluster/plugins:registry_lib",
        "//tradefed_cluster/util:env_util_lib",
    ],
)

pytype_strict_library(
    name = "host_event_api_lib",
    srcs = [
        "host_event_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_manager_lib",
        ":host_event_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
        third_party("six"),
    ],
)

py_test(
    name = "harness_image_metadata_syncer_test",
    srcs = [
        "harness_image_metadata_syncer_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":harness_image_metadata_syncer_lib",
        ":testbed_dependent_test_lib",
        "//third_party/py/absl/testing:parameterized",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("mock"),
    ],
)

py_test(
    name = "harness_update_scheduler_test",
    srcs = [
        "harness_update_scheduler_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":harness_update_scheduler_lib",
        ":testbed_dependent_test_lib",
        "//third_party/py/absl/testing:parameterized",
        third_party("mock"),
    ],
)

py_test(
    name = "host_event_api_test",
    srcs = [
        "host_event_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":common_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

py_library(
    name = "host_event_lib",
    srcs = [
        "host_event.py",
    ],
    srcs_version = "PY2AND3",
)

py_test(
    name = "host_event_test",
    srcs = [
        "host_event_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_messages_lib",
        ":host_event_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "lab_resource_monitor_lib",
    srcs = [
        "lab_resource_monitor.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/util:pubsub_client_lib",
        third_party("flask"),
        third_party("six"),
    ],
)

py_test(
    name = "lab_resource_monitor_test",
    srcs = [
        "lab_resource_monitor_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":lab_resource_monitor_lib",
        ":testbed_dependent_test_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("mock"),
    ],
)

pytype_strict_library(
    name = "metric_lib",
    srcs = [
        "metric.py",
    ],
    deps = [
        ":env_config_lib",
        "//tradefed_cluster/util:metric_util_lib",
        third_party("pytz"),
    ],
)

py_test(
    name = "metric_test",
    size = "large",
    srcs = [
        "metric_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":metric_lib",
        third_party("mock"),
        third_party("webtest"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "note_manager_lib",
    srcs = [
        "note_manager.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        "//tradefed_cluster/util:pubsub_client_lib",
        third_party("lazy_object_proxy"),
        third_party("protorpc:protorpc_all"),
    ],
)

py_test(
    name = "note_manager_test",
    srcs = [
        "note_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":note_manager_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "notification_handler_lib",
    srcs = [
        "notification_handler.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":notifier_lib",
        ":request_manager_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "notification_handler_test",
    srcs = [
        "notification_handler_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":notification_handler_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "notifier_lib",
    srcs = [
        "notifier.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":env_config_lib",
        ":request_manager_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:pubsub_client_lib",
        third_party("flask"),
        third_party("lazy_object_proxy"),
    ],
)

py_test(
    name = "notifier_test",
    srcs = [
        "notifier_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":datastore_test_util_lib",
        ":env_config_lib",
        ":notifier_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("six"),
        third_party("webtest"),
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "predefined_message_api_lib",
    srcs = [
        "predefined_message_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        ":note_manager_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "predefined_message_api_test",
    srcs = [
        "predefined_message_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "report_api_lib",
    srcs = [
        "report_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_info_reporter_lib",
        third_party("dateutil"),
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("six"),
    ],
)

py_test(
    name = "report_api_test",
    srcs = [
        "report_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "request_api_lib",
    srcs = [
        "request_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":command_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":request_manager_lib",
        ":request_sync_monitor_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "request_api_test",
    srcs = [
        "request_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
    ],
)

pytype_strict_library(
    name = "request_manager_lib",
    srcs = [
        "request_manager.py",
    ],
    deps = [
        ":api_messages_lib",
        ":command_error_type_config_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:command_util",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("protorpc:protorpc_all"),
        third_party("six"),
    ],
)

py_test(
    name = "request_manager_test",
    srcs = [
        "request_manager_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    tags = ["requires-net:external"],
    deps = [
        ":datastore_test_util_lib",
        ":env_config_lib",
        ":request_manager_lib",
        ":testbed_dependent_test_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("hamcrest"),
        third_party("mock"),
    ],
)

pytype_strict_library(
    name = "request_sync_monitor_lib",
    srcs = [
        "request_sync_monitor.py",
    ],
    deps = [
        ":command_event_lib",
        ":command_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":request_manager_lib",
        "//third_party/py/six",
        "//tradefed_cluster/services:task_scheduler_lib",
        "//tradefed_cluster/util:ndb_shim_lib",
        third_party("flask"),
    ],
)

py_test(
    name = "request_sync_monitor_test",
    srcs = [
        "request_sync_monitor_test.py",
    ],
    python_version = "PY3",
    deps = [
        ":command_event_test_util",
        ":datastore_test_util_lib",
        ":request_sync_monitor_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

pytype_strict_library(
    name = "run_target_api_lib",
    srcs = [
        "run_target_api.py",
    ],
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_manager_lib",
        third_party("endpoints:endpoints_library"),
        third_party("protorpc:protorpc_all"),
        third_party("pytz"),
    ],
)

py_test(
    name = "run_target_api_test",
    srcs = [
        "run_target_api_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)

pytype_strict_library(
    name = "server_lib",
    srcs = [
        "server.py",
    ],
    deps = [
        ":api_lib",
        ":command_attempt_monitor_lib",
        ":command_event_handler_lib",
        ":command_lib",
        ":commander_lib",
        ":config_syncer_gcs_to_ndb_lib",
        ":device_history_cleaner_lib",
        ":device_info_reporter_lib",
        ":device_monitor_lib",
        ":harness_image_metadata_syncer_lib",
        ":harness_update_scheduler_lib",
        ":lab_resource_monitor_lib",
        ":notification_handler_lib",
        ":notifier_lib",
        ":request_sync_monitor_lib",
        "//tradefed_cluster/services:task_scheduler_lib",
    ],
)

py_test(
    name = "server_test",
    srcs = [
        "server_test.py",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":server_lib",
        third_party("absl/testing:absltest"),
        third_party("mock"),
        third_party("werkzeug"),
    ],
)

pytype_strict_library(
    name = "testbed_dependent_test_lib",
    testonly = 1,
    srcs = [
        "testbed_dependent_test.py",
    ],
    data = [
        "test_yaml/queue.yaml",
    ],
    deps = [
        ":env_config_lib",
        "//tradefed_cluster/plugins:base_lib",
        "//tradefed_cluster/util:ndb_test_lib",
        third_party("mock"),
    ],
)


bzl_library(
    name = "adapter_bzl",
    srcs = ["adapter.bzl"],
    parse_tests = False,
    visibility = ["//visibility:private"],
)

bzl_library(
    name = "adapter.bazel_bzl",
    srcs = ["adapter.bazel.bzl"],
    parse_tests = False,
    visibility = ["//visibility:private"],
)
