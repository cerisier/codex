"""Fork-only comparison; do not modify the production voice build recipe."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REMOVAL = "10d794dee9bfb5c95c30b6b39f557cc3ee613a6b"
EVIDENCE = Path("voice-diagnostic")
MODE = os.environ["DIAGNOSTIC_MODE"]
RUNTIME = "//third_party/voice:native_runtime_windows_x86_64"
HELPER = "//codex-rs/voice-host:codex-voice-host"


def configure():
    EVIDENCE.mkdir(exist_ok=True)
    if MODE == "before-removal":
        subprocess.run(["git", "fetch", "--depth=2", "origin", REMOVAL], check=True)
        for name in (
            ".bazelrc",
            "MODULE.bazel",
            "bazel/rules/runtime_package.bzl",
            "third_party/voice/cargo-ci/produce/action.yml",
            ".github/workflows/rust-release-windows.yml",
        ):
            data = subprocess.check_output(["git", "show", f"{REMOVAL}^:{name}"])
            destination = name + ".disabled" if name.startswith(".github/workflows/") else name
            Path(destination).write_bytes(data)
    elif MODE == "restored-msvc":
        with Path("MODULE.bazel").open("a", encoding="utf-8") as output:
            output.write('\n# Diagnostic: expose installed MSVC only for this invocation.\n'
                         'cc_configure = use_extension("@rules_cc//cc:extensions.bzl", "cc_configure_extension")\n'
                         'use_repo(cc_configure, "local_config_cc")\n')
    elif MODE != "current":
        raise ValueError(MODE)
    (EVIDENCE / "source.diff").write_bytes(subprocess.check_output(["git", "diff"]))
    (EVIDENCE / "revision.json").write_text(json.dumps({
        "mode": MODE,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "comparison_commit": REMOVAL,
        "runner_image": os.environ.get("ImageVersion"),
    }, indent=2))


def build():
    bazel = shutil.which("bazel")
    if not bazel:
        raise RuntimeError("Bazel is unavailable")
    startup = [bazel, "--nosystem_rc", "--nohome_rc", "--output_user_root=C:/v/u", "--output_base=C:/v/o"]
    flags = [
        "--config=release", "--config=ci-windows-msvc",
        "--platforms=//:local_windows_msvc", "--host_platform=//:local_windows_msvc",
        "--repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1",
        "--extra_toolchains=//third_party/voice:windows_pkg_config_toolchain,//third_party/voice:windows_cmake_toolchain",
        "--inject_repository=voice_windows_tools=" + os.environ["VOICE_WINDOWS_BAZEL_REPOSITORY"],
        "--//third_party/voice:windows_installed_tools=@voice_windows_tools//:tools",
        "--workspace_status_command=./scripts/workspace-status.cmd",
        "--jobs=4", "--verbose_failures", "--color=no", "--curses=no",
    ]
    if MODE == "restored-msvc":
        flags += [
            "--repo_env=BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=0",
            "--extra_toolchains=@local_config_cc//:cc-toolchain-x64_windows,@local_config_cc//:cc-toolchain-arm64_windows",
        ]
    for name in ("SystemRoot", "PROCESSOR_ARCHITECTURE"):
        flags += [f"--action_env={name}={os.environ[name]}", f"--host_action_env={name}={os.environ[name]}"]

    results = {}

    def run(name, command, quiet=False):
        (EVIDENCE / (name + ".command.json")).write_text(json.dumps(command, indent=2))
        with (EVIDENCE / (name + ".log")).open("w", encoding="utf-8") as output:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace")
            for line in process.stdout:
                output.write(line)
                output.flush()
                if not quiet:
                    print(line, end="", flush=True)
            results[name] = process.wait()
        (EVIDENCE / "results.json").write_text(json.dumps(results, indent=2))
        return results[name]

    # Analyze the larger helper graph separately: an analysis failure should not
    # prevent testing whether the standalone SDK producer works.
    run("helper-analysis", startup + ["aquery"] + flags + [
        "--output=text", "--include_artifacts=false",
        'mnemonic("(CppCompile|CppLink|Rustc|CargoBuildScriptRun|VoiceWindows.*)", deps(' + HELPER + '))',
    ], quiet=True)
    run("runtime-analysis", startup + ["aquery"] + flags + [
        "--output=text", "--include_artifacts=false", "deps(" + RUNTIME + ")",
    ], quiet=True)
    result = run("native-build", startup + ["build"] + flags + [
        "--output_groups=default,sdk", RUNTIME,
    ])
    outputs = Path("bazel-bin/third_party/voice")
    if outputs.exists():
        for source in outputs.glob("native_*windows_x86_64*.json"):
            shutil.copy2(source, EVIDENCE / source.name)
    if result == 0:
        print("Native SDK/runtime build passed; Cargo linkage and runtime execution remain untested.")
    return result or int(any(results.values()))


if __name__ == "__main__":
    if sys.argv[1:] == ["configure"]:
        configure()
    elif sys.argv[1:] == ["build"]:
        sys.exit(build())
    else:
        raise SystemExit("Expected configure or build")
