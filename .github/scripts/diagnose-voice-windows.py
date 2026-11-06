"""Fork-only comparison; do not modify the production voice build recipe."""

import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys


REMOVAL = "10d794dee9bfb5c95c30b6b39f557cc3ee613a6b"
EVIDENCE = Path("voice-diagnostic")
MODE = os.environ["DIAGNOSTIC_MODE"]
CPU = os.environ.get("VOICE_CPU", "x86_64")
TARGET = CPU + "-pc-windows-msvc"
RUNTIME_NAME = "native_runtime_windows_" + CPU
RUNTIME = "//third_party/voice:" + RUNTIME_NAME
HELPER = "//codex-rs/voice-host:codex-voice-host"
TEST = "relocated_runtime_initializes_closes_and_rejects_duplicate_initialization"


def run(name, command, quiet=False, **kwargs):
    (EVIDENCE / (name + ".command.json")).write_text(json.dumps(command, indent=2))
    with (EVIDENCE / (name + ".log")).open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", **kwargs)
        for line in process.stdout:
            output.write(line)
            output.flush()
            if not quiet:
                print(line, end="", flush=True)
        code = process.wait()
    result_file = EVIDENCE / "results.json"
    results = json.loads(result_file.read_text()) if result_file.exists() else {}
    results[name] = code
    result_file.write_text(json.dumps(results, indent=2))
    return code


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


def build(helper=False):
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

    if helper:
        result = run("helper-build", startup + ["build"] + flags + [HELPER])
        binary = Path("bazel-bin/codex-rs/voice-host/codex-voice-host.exe")
        if binary.exists():
            # Preserve path evidence even if the post-link hermeticity check
            # rejects an otherwise successfully linked executable.
            data = binary.read_bytes()
            import re
            paths = []
            for pattern in (rb"[\x20-\x7e]{12,}", rb"(?:[\x20-\x7e]\x00){12,}"):
                for match in re.finditer(pattern, data):
                    value = match.group().decode("utf-16-le" if b"\x00" in match.group() else "ascii")
                    if "execroot" in value.lower():
                        paths.append(value)
            (EVIDENCE / "helper-embedded-paths.json").write_text(json.dumps(paths, indent=2))
        if result:
            return result
        binary = Path("bazel-bin/codex-rs/voice-host/codex-voice-host.exe").resolve(strict=True)
        inspect_binary("bazel-helper", binary)
        environment = dict(os.environ)
        runtime_bin = (Path("bazel-bin/third_party/voice") / RUNTIME_NAME / "bin").resolve(strict=True)
        environment["PATH"] = str(runtime_bin) + os.pathsep + environment["PATH"]
        return run("bazel-helper-identity", [str(binary), "--build-commit"], env=environment)

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
    for source in Path("C:/v/o/external").glob("*/rustc/BUILD.bazel"):
        if "declare_rustc_toolchains" in source.read_text(errors="replace"):
            shutil.copy2(source, EVIDENCE / (source.parent.parent.name + "-rustc.BUILD.txt"))
    outputs = Path("bazel-bin/third_party/voice")
    if outputs.exists():
        for source in outputs.glob("native_*windows_" + CPU + "*.json"):
            shutil.copy2(source, EVIDENCE / source.name)
        for name in ("runtime.json", "sdk.json"):
            directory = RUNTIME_NAME + ("_sdk" if name == "sdk.json" else "")
            source = outputs / directory / name
            if source.exists():
                shutil.copy2(source, EVIDENCE / name)
    return result


def inspect_binary(name, binary):
    (EVIDENCE / (name + ".sha256")).write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + "\n")
    dumpbin = shutil.which("dumpbin")
    if not dumpbin:
        raise RuntimeError("MSVC dumpbin is unavailable")
    if run(name + "-pe", [dumpbin, "/headers", "/imports", str(binary)], quiet=True):
        raise RuntimeError("PE inspection failed")


def cargo():
    # The integration test also builds the real binary. Compile once, then use
    # that same existing test to exercise the Cargo and Bazel executables.
    command = ["cargo", "test", "--release", "--locked", "-p", "codex-voice-host",
               "--target", TARGET, "--test", "packaged_runtime",
               "--no-run", "--message-format=json"]
    result = run("cargo-build", command, cwd="codex-rs")
    if result:
        return result
    artifacts = []
    for line in (EVIDENCE / "cargo-build.log").read_text().splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("reason") == "compiler-artifact" and message.get("executable"):
            artifacts.append(message)
    test = next(Path(a["executable"]) for a in artifacts if a["target"]["name"] == "packaged_runtime")
    binary = next(Path(a["executable"]) for a in artifacts if a["target"]["name"] == "codex-voice-host")
    inspect_binary("cargo-helper", binary)
    environment = dict(os.environ)
    environment["PATH"] = str(Path(environment["CODEX_TEST_VOICE_RUNTIME"]) / "bin") + os.pathsep + environment["PATH"]
    result = run("cargo-helper-identity", [str(binary), "--build-commit"], env=environment)
    binaries = {"cargo": binary}
    bazel_binary = Path("bazel-bin/codex-rs/voice-host/codex-voice-host.exe")
    if bazel_binary.exists():
        binaries["bazel"] = bazel_binary.resolve(strict=True)
    for name, executable in binaries.items():
        environment["CARGO_BIN_EXE_codex-voice-host"] = str(executable)
        result |= run(name + "-relocated-runtime", [str(test), "--ignored", "--exact", TEST, "--nocapture"], env=environment)
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["configure"]:
        configure()
    elif sys.argv[1:] == ["build"]:
        sys.exit(build())
    elif sys.argv[1:] == ["helper"]:
        sys.exit(build(helper=True))
    elif sys.argv[1:] == ["cargo"]:
        sys.exit(cargo())
    else:
        raise SystemExit("Expected configure, build, helper or cargo")
