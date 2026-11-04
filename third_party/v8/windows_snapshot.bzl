"""Run an @llvm-built Windows snapshot generator with declared Wine on Linux.

V8 15.2's Windows unwind writer is guarded by the generator's host OS. A Linux
generator with V8_TARGET_OS_WIN would silently omit embedded .pdata/.xdata.
The Windows payload is data for Wine, not a Linux exec-platform executable.
"""

def _windows_generator_platform_impl(settings, attr):
    # V8 supports x64-hosted ARM64 code generation. Preserve the caller's
    # explicit V8 target CPU/profile while making the payload runnable in Wine.
    return {"//command_line_option:platforms": [str(Label("@llvm//platforms:windows_x86_64_msvc"))]}

_windows_generator_platform = transition(
    implementation = _windows_generator_platform_impl,
    inputs = [],
    outputs = ["//command_line_option:platforms"],
)

def _windows_snapshot_impl(ctx):
    outputs = [
        ctx.actions.declare_file(ctx.label.name + "/snapshot.cc"),
        ctx.actions.declare_file(ctx.label.name + "/embedded.S"),
    ]
    args = ctx.actions.args()
    args.add_all([
        ctx.file._runner,
        ctx.file._wine,
        ctx.file._wineserver,
        ctx.file.tool,
        "--embedded_variant=Default",
        "--target_os",
        "win",
        "--target_arch",
        ctx.attr.target_arch,
        "--startup_src",
        outputs[0],
        "--embedded_src",
        outputs[1],
    ])
    args.add_all(ctx.attr.args)
    ctx.actions.run_shell(
        arguments = [args],
        command = 'source "$1" "${@:2}"',
        inputs = depset(
            [ctx.file._runner, ctx.file.tool],
            transitive = [ctx.attr._wine_runtime[DefaultInfo].files],
        ),
        tools = [ctx.file._wine, ctx.file._wineserver],
        outputs = outputs,
        mnemonic = "V8WindowsSnapshot",
        progress_message = "Generating Windows V8 snapshot under hermetic Wine",
    )
    return [DefaultInfo(files = depset(outputs))]

def windows_snapshot_rule(cpu_transition):
    """Use V8's existing CPU inference before transitioning the payload to x64."""
    return rule(
        implementation = _windows_snapshot_impl,
        cfg = cpu_transition,
        attrs = {
            "args": attr.string_list(),
            "target_arch": attr.string(mandatory = True, values = ["arm64", "x64"]),
            "tool": attr.label(
                allow_single_file = True,
                mandatory = True,
                cfg = _windows_generator_platform,
            ),
            "_allowlist_function_transition": attr.label(
                default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
            ),
            "_runner": attr.label(default = "//third_party/v8:windows_snapshot.sh", allow_single_file = True),
            "_wine": attr.label(default = "@wine_linux_x86_64//:wine", allow_single_file = True, cfg = "exec"),
            "_wineserver": attr.label(default = "@wine_linux_x86_64//:wineserver", allow_single_file = True, cfg = "exec"),
            "_wine_runtime": attr.label(default = "@wine_linux_x86_64//:runtime", cfg = "exec"),
        },
    )
