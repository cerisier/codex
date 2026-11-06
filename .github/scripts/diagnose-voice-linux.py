"""Fork-only Linux voice validation using the existing packaged-runtime test."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


EVIDENCE = Path("voice-linux-diagnostic").resolve()
CPU = os.environ["VOICE_CPU"]
TARGET = CPU + "-unknown-linux-gnu"
RUNTIME = "native_runtime_linux_" + CPU
HELPER = "//codex-rs/voice-host:codex-voice-host"
TEST = "relocated_runtime_initializes_closes_and_rejects_duplicate_initialization"


def run(name, command, **kwargs):
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / (name + ".command.json")).write_text(json.dumps(command, indent=2))
    with (EVIDENCE / (name + ".log")).open("w") as output:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors="replace", **kwargs)
        for line in process.stdout:
            output.write(line)
            output.flush()
            print(line, end="", flush=True)
        code = process.wait()
    path = EVIDENCE / "results.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    results[name] = code
    path.write_text(json.dumps(results, indent=2))
    return code


def inspect(name, binary):
    (EVIDENCE / (name + ".sha256")).write_text(hashlib.sha256(binary.read_bytes()).hexdigest() + "\n")
    return run(name + "-elf", ["readelf", "-h", "-d", "-V", "--dyn-syms", "--wide", str(binary)])


def build(helper=False):
    # Native public runners have no private RBE credentials. The matching RBE
    # routes are validated separately from the developer's configured machine.
    command = ["bazel", "--nosystem_rc", "--nohome_rc", "--output_base=/tmp/voice-bazel", "build",
               "--config=release", "--host_platform=//:local_linux",
               "--platforms=@llvm//platforms:linux_" + CPU + "_gnu.2.28",
               "--jobs=4", "--verbose_failures", "--color=no", "--curses=no"]
    targets = [HELPER] if helper else ["//third_party/voice:native_sdk", "//third_party/voice:native_runtime"]
    result = run("helper-build" if helper else "native-build", command + targets)
    if result:
        return result
    if helper:
        return inspect("bazel-helper", Path("bazel-bin/codex-rs/voice-host/codex-voice-host").resolve(strict=True))
    runtime = Path("bazel-bin/third_party/voice") / RUNTIME
    for name in ("runtime.json", "sdk.json"):
        source = runtime / name if name == "runtime.json" else runtime.with_name(RUNTIME + "_sdk") / name
        shutil.copy2(source, EVIDENCE / name)
    return inspect("pcre2", runtime / "lib/libpcre2-8.so.0")


def cargo():
    result = run("cargo-build", ["cargo", "test", "--release", "--locked", "-p", "codex-voice-host",
                 "--target", TARGET, "--test", "packaged_runtime", "--no-run", "--message-format=json"],
                 cwd="codex-rs")
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
    test = next(a["executable"] for a in artifacts if a["target"]["name"] == "packaged_runtime")
    binary = next(Path(a["executable"]) for a in artifacts if a["target"]["name"] == "codex-voice-host")
    result |= inspect("cargo-helper", binary)
    binaries = {"cargo": binary}
    bazel = Path("bazel-bin/codex-rs/voice-host/codex-voice-host")
    if bazel.exists():
        binaries["bazel"] = bazel.resolve(strict=True)
    environment = dict(os.environ)
    environment.pop("LD_LIBRARY_PATH", None)
    # Identity queries also launch the original helper. Place an unchanged copy
    # in the real package layout so its existing $ORIGIN/../lib rpath suffices.
    destination = Path(environment["CODEX_TEST_VOICE_RUNTIME"]) / "bin/codex-voice-host"
    destination.parent.mkdir(exist_ok=True)
    for name, executable in binaries.items():
        shutil.copyfile(executable, destination)
        # The test copies this source tree, then installs the selected helper
        # over its copy. Do not propagate Bazel's read-only output permissions.
        destination.chmod(0o755)
        environment["CARGO_BIN_EXE_codex-voice-host"] = str(destination)
        result |= run(name + "-identity", [str(destination), "--build-commit"], env=environment)
        result |= run(name + "-relocated-runtime", [test, "--ignored", "--exact", TEST, "--nocapture"], env=environment)
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        sys.exit(build())
    if sys.argv[1:] == ["helper"]:
        sys.exit(build(helper=True))
    if sys.argv[1:] == ["cargo"]:
        sys.exit(cargo())
    raise SystemExit("Expected build, helper or cargo")
