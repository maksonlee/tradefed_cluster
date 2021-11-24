# Copyright 2018 Google Inc. All Rights Reserved.
# Author: xingdai@example.com (Xing Dai)
#
# Package:
#   tradefed_cluster/configs
#
# Description:
#   Tools for configs.
load("//tradefed_cluster:adapter.bzl", "proto_library", "py_library", "py_proto_library", "third_party")

package(default_visibility = ["//tradefed_cluster:tradefed_cluster_clients"])

licenses(["notice"])

py_library(
    name = "lab_config_lib",
    srcs = [
        "lab_config.py",
    ],
    srcs_version = "PY2AND3",
    visibility = ["//visibility:public"],
    deps = [
        ":lab_config_py_pb2",
        ":unified_lab_config_lib",
        third_party("strictyaml"),
        "//net/proto2/python/public",
    ],
)

py_library(
    name = "unified_lab_config_lib",
    srcs = [
        "unified_lab_config.py",
    ],
    srcs_version = "PY2AND3",
    visibility = ["//visibility:public"],
    deps = [
        third_party("ansible"),
        third_party("strictyaml"),
    ],
)

proto_library(
    name = "lab_config_proto",
    srcs = [
        "lab_config.proto",
    ],
)

py_proto_library(
    name = "lab_config_py_pb2",
    srcs = [
        "lab_config.proto",
    ],
    api_version = 2,
    deps = [
        ":lab_config_proto",
    ],
)

py_test(
    name = "lab_config_test",
    srcs = ["lab_config_test.py"],
    data = [
        ":testdata",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":lab_config_lib",
        third_party("six"),
    ],
)

py_test(
    name = "unified_lab_config_test",
    srcs = [
        "unified_lab_config_test.py",
    ],
    data = [
        ":testdata",
    ],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":unified_lab_config_lib",
    ],
)


filegroup(
    name = "testdata",
    srcs = glob(["testdata/**"]),
)
