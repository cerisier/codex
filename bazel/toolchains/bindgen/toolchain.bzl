"""Pair bindgen's statically linked parser with the selected LLVM sources."""

def _bindgen_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(bindgen = ctx.executable.bindgen)]

bindgen_toolchain = rule(
    implementation = _bindgen_toolchain_impl,
    attrs = {
        "bindgen": attr.label(
            allow_single_file = True,
            cfg = "exec",
            executable = True,
            mandatory = True,
        ),
    },
)
