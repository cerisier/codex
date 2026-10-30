# SDK overlay working-directory reproducer

This diagnostic reproduces the curl-sys Windows cross-build failure against
hermetic-llvm `fd2addebff08b29675ee266bc2766e475ce9263b`. It is not a substitute
for building or running the Codex CLI.

```sh
bazel build \
  --config=buildbuddy-generic-rbe \
  --host_platform=//:rbe \
  --repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1 \
  --repo_env=BAZEL_WINDOWS_SDK_EULA=1 \
  --features=-dynamic_link_msvcrt \
  --features=static_link_msvcrt \
  --platforms=@llvm//platforms:windows_x86_64_msvc \
  //tools/msvc_overlay_probe:probe
```

The Linux ARM64 remote action uses declared Clang, SDK shared headers and the
generated case overlay. Identical absolute compiler arguments locate
`WlanTypes.h` from the execroot but fail from another working directory.
The SDK contains `wlantypes.h`; this is a case-overlay failure, not an absent
SDK header. The diagnostic succeeds when it reproduces that difference; read
`bazel-bin/tools/msvc_overlay_probe/probe.txt` for both compiler results.

BuildBuddy execution: `de407baf-c5d5-4fb9-a480-a037ace599d4`.
Checked-in local module override replay: `e8eba2fa-3eae-4f50-abe5-03a29197ad8f`.

The generator writes cwd-relative virtual roots and `external-contents` paths.
Cargo correctly runs build scripts from their manifest directory. Rewriting
the overlay filename in CFLAGS does not relocate the paths inside it.
The initial hypothesis was an overlay-relative hermetic-llvm fix. Experiments
rejected that approach: it emits absolute header names that Bazel cannot resolve
from remote depfiles. A two-layer variant retained relative dependency names
but could shadow unrelated paths after cwd changes. Neither is a valid generic
toolchain fix. The LLVM checkouts are unchanged.

## Cargo-boundary regression

`cargo_probe` runs through the real rules_rust build-script runner and uses its
selected compiler and CFLAGS. With unchanged LLVM, the same SDK lookup fails
without the adapter and succeeds with it:

```sh
bazel build \
  --config=buildbuddy-generic-rbe \
  --host_platform=//:rbe \
  --repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1 \
  --repo_env=BAZEL_WINDOWS_SDK_EULA=1 \
  --features=-dynamic_link_msvcrt \
  --features=static_link_msvcrt \
  --features=cargo-rebase-json-vfs-overlays \
  --platforms=@llvm//platforms:windows_x86_64_msvc \
  //tools/msvc_overlay_probe:cargo_probe
```

Remove `--features=cargo-rebase-json-vfs-overlays` for the failing control.
Control invocation: `df89616d-689b-4b13-b7d6-460886600b61`.
Passing invocation: `96f20d11-d3b0-446a-80c5-e0bbedd08e40`.
Inspect `bazel-bin/tools/msvc_overlay_probe/cargo_probe.out_dir/overlay-proof.txt`:
Linux ARM64 `@llvm` clang-cl, x86_64 MSVC target, `/MT`, declared SDK paths,
manifest cwd, successful mixed-case lookup. Temporary overlays are absent from
the captured output directory.

The project-local rules_rust patch is deliberately opt-in and JSON-only. It
rebases virtual roots and external paths into action-local copies before
running Cargo scripts; original inputs and ordinary C++ actions are unchanged.
It preserves overlay-directory anchoring, absolute paths and VFS settings.
Unsupported YAML and ambiguous path forms fail explicitly; this is not a claim
of general YAML support or validated native Windows host execution.

Runner tests (including JSON rebasing tests):

```sh
bazel test --config=buildbuddy-generic-rbe --host_platform=//:rbe \
  --platforms=//:rbe @rules_rust//cargo/private/cargo_build_script_runner:test
```

Initial passing invocation: `b3b18d63-b469-4b43-8487-b825517f1f03`.
These probes are regression evidence, not a substitute for the full CLI build.

## Target configuration versus build-script compilation

The probe also checks `CARGO_CFG_TARGET_FEATURE` contains `crt-static`, matching
the selected Rust target toolchain. Without target flags on the runner's
`rustc --print=cfg` query, this assertion fails:
`8237b281-8ea9-47f8-ab6d-d3ed5638acb5`. This mismatch made rusty_v8 request
dynamic `msvcprt.lib` despite the actual target using static CRT.

`rules_rust_cargo_target_flags.patch` passes configured target flags through a
separate internal environment variable. The `rustc_flags` attribute belongs to
the build-script executable, not this target query. The probe compiles its
script with an `@$(location ...)` response file in `compile_data`; forwarding
that unexpanded attribute to the query fails before the script runs
(`74562cf9-de78-4e27-bcb1-947e5bddf056`). Keeping the two flag sets separate
passes both assertions and the SDK lookup
(`4941fbb0-4b8e-4daa-aa58-48554aeb2a14`).

Runner library/binary and bindgen helper test targets all pass together:
`039d2565-916c-4c5f-87fd-fce239a0aa2f` (five test targets).

## Real CLI, direct hermetic LLVM link

The real executable now builds without `cc_common.link`, with unchanged
hermetic-llvm `fd2addebff08b29675ee266bc2766e475ce9263b`:

```sh
bazel build --config=buildbuddy-generic-rbe --host_platform=//:rbe \
  --repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1 \
  --repo_env=BAZEL_WINDOWS_SDK_EULA=1 \
  --features=-dynamic_link_msvcrt --features=static_link_msvcrt \
  --features=cargo-rebase-json-vfs-overlays \
  --platforms=@llvm//platforms:windows_x86_64_msvc \
  //codex-rs/cli:codex --verbose_failures
```

Build: `9b829db0-9d25-4920-b107-279b3e2077c2`, 517.263 seconds, success.
The final action is `Rustc`, running on Linux ARM64. Its C++ toolchain-derived
arguments include `/MACHINE:X64`, `/lldignoreenv`, the SDK and static CRT
`/LIBPATH` roots, and the library case overlay. Rust uses `+crt-static` and
the rules_rs toolchain's declared `lld-link` symlink to `@llvm//tools:lld-link`.
The native Cargo regression above demonstrates clang-cl and `/MT`.

The forwarding patch unwraps clang-cl's `/clang:` and decodes `-Xlinker` and
`-Wl,` only for direct Windows MSVC linking. It does not introduce a standalone
link action or bypass toolchain feature selection. A preceding full CLI build
using Rust's bundled LLD also passed (`6690feb4-6436-4fde-86a1-7db200915835`),
but the final proof deliberately uses hermetic-llvm's linker.

Action inspection: `5e3e7c4d-ae2e-432e-b9ef-a77bae681335`, using the same
configuration and `bazel aquery --include_param_files --output=jsonproto
'mnemonic("Rustc", //codex-rs/cli:codex)'`. This inspection additionally enabled
`--extra_execution_platforms=//:rbe,//bazel/platforms:linux_x86_64_rbe`; the CLI
action still selected the same Linux ARM64 platform. SDK inputs and the
underlying Linux ARM64 `lld-link` are declared. No user-home or installed Visual
Studio path occurs in the action arguments.

Artifact SHA-256:
`22a758897548c1e12d94a21e8d09446b56f9d43c5fa9be11e80808170da524cd`.
`llvm readobj --file-headers --coff-imports` reports
`IMAGE_FILE_MACHINE_AMD64 (0x8664)` and Windows system imports, with no
`vcruntime`, `msvcp`, or `ucrtbase` DLL imports. In a fresh Wine prefix,
`wine codex.exe --version` exits zero and prints `codex-cli 0.0.0`.
No authentication or networked product commands were run.

This is a dedicated consumer proof, not out-of-the-box support: the local
rules_rust/rules_rs patches remain required. The JSON adapter is opt-in, not a
generic YAML solution. Native Windows host execution is untested. V8 belongs
to the separate `codex-code-mode-host` executable and is not covered by this
CLI result; neither is the complete Windows release package or ARM64.
