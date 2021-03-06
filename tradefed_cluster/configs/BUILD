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
        third_party("strictyaml"),
        "//net/proto2/python/public",
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
        "//net/proto2/python/public:use_pure_python",  # Automatically added go/proto_python_default
    ],
)


filegroup(
    name = "testdata",
    srcs = glob(["testdata/**"]),
)
