"""Diagnostic: compare the SDK case overlay before and after changing cwd."""

load("@bazel_skylib//rules/directory:providers.bzl", "DirectoryInfo")

def _sdk_overlay_probe_impl(ctx):
    output = ctx.actions.declare_file(ctx.label.name + ".txt")
    shared = ctx.attr._shared[DirectoryInfo]
    args = ctx.actions.args()
    args.add(ctx.file._script)
    args.add(ctx.executable._clang)
    args.add(ctx.file._overlay)
    args.add(shared.path)
    args.add(output)
    ctx.actions.run_shell(
        arguments = [args],
        command = 'source "$1" "${@:2}"',
        inputs = depset(
            [ctx.file._script, ctx.file._overlay],
            transitive = [shared.transitive_files],
        ),
        tools = [ctx.attr._clang[DefaultInfo].files_to_run],
        outputs = [output],
        mnemonic = "MsvcOverlayCwdProbe",
    )
    return [DefaultInfo(files = depset([output]))]

sdk_overlay_probe = rule(
    implementation = _sdk_overlay_probe_impl,
    attrs = {
        "_clang": attr.label(
            default = "@llvm//tools:clang",
            executable = True,
            cfg = "exec",
            allow_single_file = True,
        ),
        "_overlay": attr.label(
            default = "@llvm//runtimes/msvc:msvc_sdk_header_case_overlay",
            allow_single_file = True,
        ),
        "_shared": attr.label(
            default = "@llvm//runtimes/msvc:winsdk_shared_include",
            providers = [DirectoryInfo],
        ),
        "_script": attr.label(
            default = "probe.sh",
            allow_single_file = True,
        ),
    },
)
