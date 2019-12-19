"""Starlark rules for GAE configs."""

def merge_yamls(
        name,
        srcs,
        out,
        **kwargs):
    """Merge GAE yamls.

    Args:
        name: a unique name for a target.
        srcs: a list of source yaml files.
        out: an output yaml file.
        **kwargs: a dict args.
    """
    kwargs["name"] = name
    kwargs["srcs"] = srcs
    kwargs["outs"] = [out]
    kwargs["tools"] = ["//third_party/py/tradefed_cluster/gae_configs:merge_yamls"]
    kwargs["cmd"] = "$(location //third_party/py/tradefed_cluster/gae_configs:merge_yamls) $(SRCS) > \"$@\""
    native.genrule(**kwargs)
