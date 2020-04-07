# A test infra software for Android testing labs.
load("//tradefed_cluster:adapter.bzl", "py_appengine_binary", "py_appengine_library", "py_appengine_test", "third_party")

package(default_visibility = [":tradefed_cluster_clients"])

licenses(["notice"])  # Apache 2.0

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

PY_APPENGINE_ENVS = [{"runtime": "python27"}]

PY_APPENGINE_TEST_ENVS = [{
    "libraries": {
        "PIL": "latest",
        "pycrypto": "2.6",
    },
    "runtime": "python27",
}]

py_appengine_library(
    name = "api_common_lib",
    srcs = [
        "api_common.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
    ],
)

py_appengine_library(
    name = "api_lib",
    srcs = [
        "api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    visibility = ["//visibility:public"],
    deps = [
        ":cluster_api_lib",
        ":cluster_device_api_lib",
        ":cluster_host_api_lib",
        ":command_attempt_api_lib",
        ":command_event_api_lib",
        ":command_event_handler_lib",
        ":command_task_api_lib",
        ":commander_lib",
        ":common_lib",
        ":coordinator_api_lib",
        ":device_snapshot_api_lib",
        ":host_event_api_lib",
        ":lab_management_api_lib",
        ":report_api_lib",
        ":request_api_lib",
        ":run_target_api_lib",
    ],
)

py_appengine_library(
    name = "api_messages_lib",
    srcs = [
        "api_messages.py",
    ],
    envs = PY_APPENGINE_ENVS,
    visibility = ["//visibility:public"],
    deps = [
        ":common_lib",
    ],
)

py_appengine_test(
    name = "api_messages_test",
    srcs = [
        "api_messages_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":api_messages_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_library(
    name = "api_test_lib",
    testonly = 1,
    srcs = [
        "api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":api_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_binary(
    name = "app",
    configs = [
        "//tradefed_cluster/gae_configs",
    ],
    deps = [":app_lib"],
)

py_appengine_library(
    name = "app_lib",
    visibility = ["//visibility:public"],
    deps = [
        ":api_lib",
        ":command_event_handler_lib",
        ":commander_lib",
        ":device_history_cleaner_lib",
        ":device_info_reporter_lib",
        ":device_monitor_lib",
        ":env_config_lib",
        ":notification_handler_lib",
        ":notifier_lib",
        third_party("pytz"),
        "//tradefed_cluster/plugins:registry_lib",
        "//tradefed_cluster/util:env_util_lib",
    ],
)

py_appengine_library(
    name = "cluster_api_lib",
    srcs = [
        "cluster_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_manager_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "cluster_api_test",
    srcs = [
        "cluster_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "cluster_device_api_lib",
    srcs = [
        "cluster_device_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "cluster_device_api_test",
    srcs = [
        "cluster_device_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "cluster_host_api_lib",
    srcs = [
        "cluster_host_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "cluster_host_api_test",
    srcs = [
        "cluster_host_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "lab_management_api_lib",
    srcs = [
        "lab_management_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
    ],
)

py_appengine_test(
    name = "lab_management_api_test",
    srcs = [
        "lab_management_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "command_attempt_api_lib",
    srcs = [
        "command_attempt_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "command_attempt_api_test",
    srcs = [
        "command_attempt_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_appengine_test(
    name = "command_attempt_monitor_test",
    srcs = [
        "command_attempt_monitor_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":command_event_test_util",
        ":command_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "command_error_type_config_lib",
    srcs = [
        "command_error_type_config.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_test(
    name = "command_error_type_config_test",
    srcs = [
        "command_error_type_config_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":command_error_type_config_lib",
        ":testbed_dependent_test_lib",
    ],
)

py_appengine_library(
    name = "command_event_api_lib",
    srcs = [
        "command_event_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":command_event_handler_lib",
        ":common_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "command_event_api_test",
    srcs = [
        "command_event_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_appengine_library(
    name = "command_event_handler_lib",
    srcs = [
        "command_event_handler.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":command_lib",
        ":metric_lib",
    ],
)

py_appengine_test(
    name = "command_event_handler_test",
    srcs = [
        "command_event_handler_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":command_event_handler_lib",
        ":command_event_test_util",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "command_event_lib",
    srcs = [
        "command_event.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":command_error_type_config_lib",
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_test(
    name = "command_event_test",
    srcs = [
        "command_event_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":command_event_lib",
        ":command_event_test_util",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "command_event_test_util",
    srcs = [
        "command_event_test_util.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":command_event_lib",
    ],
)

py_appengine_library(
    name = "command_lib",
    srcs = [
        "command_attempt_monitor.py",
        "command_file.py",
        "command_manager.py",
        "command_monitor.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":command_event_lib",
        ":command_task_store_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_lib",
        third_party("googleapiclient"),
        third_party("httplib2"),
        third_party("oauth2client_1_4_12_plus"),
        "//tradefed_cluster/util:command_util",
    ],
)

py_appengine_test(
    name = "command_manager_test",
    srcs = [
        "command_manager_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_messages_lib",
        ":command_event_test_util",
        ":command_lib",
        ":command_task_store_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        ":metric_lib",
        ":request_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

py_appengine_test(
    name = "command_monitor_test",
    srcs = [
        "command_monitor_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":command_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "command_task_api_lib",
    srcs = [
        "command_task_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":command_task_matcher_lib",
        ":command_task_store_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":metric_lib",
        "//tradefed_cluster/util:command_util",
    ],
)

py_appengine_test(
    name = "command_task_api_test",
    srcs = [
        "command_task_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_appengine_library(
    name = "command_task_matcher_lib",
    srcs = [
        "command_task_matcher.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_test(
    name = "command_task_matcher_test",
    srcs = [
        "command_task_matcher_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":api_messages_lib",
        ":command_task_matcher_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "command_task_store_lib",
    srcs = [
        "command_task_store.py",
    ],
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_test(
    name = "command_task_store_test",
    srcs = [
        "command_task_store_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":command_task_store_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "commander_lib",
    srcs = [
        "commander.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":command_lib",
        ":request_lib",
    ],
)

py_appengine_test(
    name = "commander_test",
    srcs = [
        "commander_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":commander_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "common_lib",
    srcs = [
        "common.py",
    ],
    data = [
        ":email_templates",
    ],
    visibility = ["//visibility:public"],
    deps = [
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "common_test",
    srcs = [
        "common_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":common_lib",
    ],
)

py_appengine_library(
    name = "config_syncer_gcs_to_ndb_lib",
    srcs = [
        "config_syncer_gcs_to_ndb.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":datastore_entities_lib",
        "//tradefed_cluster/configs:lab_config_lib",
    ],
)

py_appengine_test(
    name = "config_syncer_gcs_to_ndb_test",
    srcs = [
        "config_syncer_gcs_to_ndb_test.py",
    ],
    data = [
        "test_yaml/dockerized-tf.yaml",
    ],
    use_public_sdk = 1,
    deps = [
        ":config_syncer_gcs_to_ndb_lib",
        ":datastore_test_util_lib",
        ":testbed_dependent_test_lib",
        third_party("cloudstorage"),
    ],
)

py_appengine_library(
    name = "coordinator_api_lib",
    srcs = [
        "coordinator_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":command_lib",
        ":common_lib",
        ":datastore_entities_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "coordinator_api_test",
    srcs = [
        "coordinator_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "datastore_entities_lib",
    srcs = [
        "datastore_entities.py",
    ],
    deps = [
        ":api_messages_lib",
        ":common_lib",
    ],
)

py_appengine_test(
    name = "datastore_entities_test",
    srcs = [
        "datastore_entities_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
        ":testbed_dependent_test_lib",
    ],
)

py_appengine_library(
    name = "datastore_util_lib",
    srcs = [
        "datastore_util.py",
    ],
    visibility = ["//visibility:public"],
)

py_appengine_test(
    name = "datastore_util_test",
    srcs = [
        "datastore_util_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":datastore_entities_lib",
        ":datastore_test_util_lib",
        ":datastore_util_lib",
        ":testbed_dependent_test_lib",
    ],
)

py_appengine_library(
    name = "datastore_test_util_lib",
    testonly = 1,
    srcs = [
        "datastore_test_util.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_library(
    name = "device_history_cleaner_lib",
    srcs = [
        "device_history_cleaner.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":common_lib",
        ":datastore_entities_lib",
    ],
)

py_appengine_test(
    name = "device_history_cleaner_test",
    srcs = [
        "device_history_cleaner_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":device_history_cleaner_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "device_info_reporter_lib",
    srcs = [
        "device_info_reporter.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        third_party("cloudstorage"),
        third_party("dateutil"),
        "//tradefed_cluster/util:email_sender_lib",
    ],
)

py_appengine_test(
    name = "device_info_reporter_test",
    srcs = [
        "device_info_reporter_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":datastore_test_util_lib",
        ":device_info_reporter_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "device_manager_lib",
    srcs = [
        "device_manager.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":host_event_lib",
        ":metric_lib",
    ],
)

py_appengine_test(
    name = "device_manager_test",
    srcs = [
        "device_manager_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":datastore_test_util_lib",
        ":device_manager_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
    ],
)

py_appengine_library(
    name = "device_monitor_lib",
    srcs = [
        "device_monitor.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":datastore_util_lib",
        ":device_manager_lib",
        ":metric_lib",
        third_party("lazy_object_proxy"),
        "//tradefed_cluster/util:pubsub_client_lib",
    ],
)

py_appengine_test(
    name = "device_monitor_test",
    srcs = [
        "device_monitor_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":datastore_test_util_lib",
        ":device_monitor_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webapp2"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "device_snapshot_api_lib",
    srcs = [
        "device_snapshot_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":device_info_reporter_lib",
    ],
)

py_appengine_test(
    name = "device_snapshot_api_test",
    srcs = [
        "device_snapshot_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

filegroup(
    name = "email_templates",
    srcs = glob([
        "email_templates/**",
    ]),
)

py_appengine_library(
    name = "env_config_lib",
    srcs = [
        "env_config.py",
    ],
    deps = [
        ":common_lib",
        "//tradefed_cluster/plugins:metric_client_lib",
        "//tradefed_cluster/plugins:registry_lib",
        "//tradefed_cluster/util:env_util_lib",
    ],
)

py_appengine_library(
    name = "host_event_api_lib",
    srcs = [
        "host_event_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_manager_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "host_event_api_test",
    srcs = [
        "host_event_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_library(
    name = "host_event_lib",
    srcs = [
        "host_event.py",
    ],
)

py_appengine_test(
    name = "host_event_test",
    srcs = [
        "host_event_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_messages_lib",
        ":host_event_lib",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "metric_lib",
    srcs = [
        "metric.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":env_config_lib",
        third_party("pytz"),
        "//tradefed_cluster/util:metric_util_lib",
    ],
)

py_appengine_test(
    name = "metric_test",
    size = "large",
    srcs = [
        "metric_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    deps = [
        ":metric_lib",
        third_party("mock"),
        third_party("webapp2"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "notification_handler_lib",
    srcs = [
        "notification_handler.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":notifier_lib",
        ":request_lib",
    ],
)

py_appengine_test(
    name = "notification_handler_test",
    srcs = [
        "notification_handler_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":notification_handler_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "notifier_lib",
    srcs = [
        "notifier.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":common_lib",
        ":env_config_lib",
        ":request_lib",
        third_party("lazy_object_proxy"),
        "//tradefed_cluster/util:pubsub_client_lib",
    ],
)

py_appengine_test(
    name = "notifier_test",
    srcs = [
        "notifier_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":env_config_lib",
        ":notifier_lib",
        ":testbed_dependent_test_lib",
        third_party("mock"),
        third_party("webtest"),
    ],
)

py_appengine_library(
    name = "report_api_lib",
    srcs = [
        "report_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_info_reporter_lib",
    ],
)

py_appengine_test(
    name = "report_api_test",
    srcs = [
        "report_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_appengine_library(
    name = "request_api_lib",
    srcs = [
        "request_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":commander_lib",
        ":common_lib",
        ":datastore_entities_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "request_api_test",
    srcs = [
        "request_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
    ],
)

py_appengine_library(
    name = "request_lib",
    srcs = [
        "request_manager.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_messages_lib",
        ":command_error_type_config_lib",
        ":common_lib",
        ":datastore_entities_lib",
        ":env_config_lib",
        "//tradefed_cluster/util:command_util",
    ],
)

py_appengine_test(
    name = "request_manager_test",
    srcs = [
        "request_manager_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":env_config_lib",
        ":request_lib",
        ":testbed_dependent_test_lib",
        third_party("hamcrest"),
        third_party("mock"),
    ],
)

py_appengine_library(
    name = "run_target_api_lib",
    srcs = [
        "run_target_api.py",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":api_messages_lib",
        ":common_lib",
        ":device_manager_lib",
        third_party("pytz"),
    ],
)

py_appengine_test(
    name = "run_target_api_test",
    srcs = [
        "run_target_api_test.py",
    ],
    envs = PY_APPENGINE_TEST_ENVS,
    use_public_sdk = 1,
    deps = [
        ":api_test_lib",
        ":datastore_test_util_lib",
    ],
)

py_appengine_library(
    name = "testbed_dependent_test_lib",
    testonly = 1,
    srcs = [
        "testbed_dependent_test.py",
    ],
    data = [
        "test_yaml/queue.yaml",
    ],
    envs = PY_APPENGINE_ENVS,
    deps = [
        ":api_common_lib",
        ":common_lib",
        third_party("mock"),
    ],
)
