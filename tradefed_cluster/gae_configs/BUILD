load("//tools/build_defs/testing:bzl_library.bzl", "bzl_library")
load("//tradefed_cluster:adapter.bzl", "pytype_strict_binary", "third_party_py3")

package(
    default_applicable_licenses = ["//tradefed_cluster:license"],
    default_visibility = ["//visibility:public"],
)

licenses(["notice"])

filegroup(
    name = "cron_yaml",
    srcs = [
        "cron.yaml",
    ],
)

filegroup(
    name = "gae_configs",
    srcs = [
        ":cron_yaml",
        ":index_yaml",
        ":queue_yaml",
        ":service_yamls",
    ],
)

filegroup(
    name = "index_yaml",
    srcs = [
        "index.yaml",
    ],
)

pytype_strict_binary(
    name = "merge_yamls",
    srcs = [
        "merge_yamls.py",
    ],
    python_version = "PY3",
    srcs_version = "PY2AND3",
    deps = [
        third_party_py3("absl:app"),
        third_party_py3("six"),
        third_party_py3("yaml"),
    ],
)

filegroup(
    name = "queue_yaml",
    srcs = [
        "queue.yaml",
    ],
)

filegroup(
    name = "service_yamls",
    srcs = [
        "app.yaml",
        "tfc.yaml",
    ],
)

bzl_library(
    name = "build_defs_bzl",
    srcs = ["build_defs.bzl"],
    parse_tests = False,
    visibility = ["//visibility:private"],
)
