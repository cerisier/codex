# Windows MSVC private-libc++ integration proof

Dedicated consumer experiment, 2026-10-30. No push or PR publication.

## Scope and acceptance

Codex checkout: `/Users/corentinkerisit/Documents/Codex/2026-08-28/codex-cli-windows-msvc-toolchain/work/codex-msvc-current`,
branch `codex/msvc-hermetic-current`, upstream `13ab0b254e7b9ed0ab473d38d978fa100bf417ae`.

LLVM checkout: sibling `hermetic-llvm-cxx-stdlib`, branch
`cerisier/cxx-stdlib-opt-outs`, base `fd2addebff08b29675ee266bc2766e475ce9263b`,
settings commit `6cc810fe3aba4d87192531de7c24974472f9f60d`.
This standalone commit contains only the two settings, implementation, docs,
and regression scenarios. The original LLVM checkouts remain unchanged.

Acceptance:

1. Independently suppress implicit C++ headers and libraries; preserve defaults,
   C/SDK headers, static CRT, compiler-rt, and the independent Linux unwinder.
2. Use explicit `scope = "target"`; verify ordinary execution tools reset to
   defaults. Explicitly reapply private-runtime policy to V8's generators.
3. Build V8 and its matching Rust bindings from source with Chromium libc++,
   selected `@llvm` clang-cl/lld-link, declared Microsoft inputs, and `/MT`.
4. Execute the Windows snapshot generator under declared Wine on Linux RBE;
   inspect its Windows unwind output and the final code-mode-host PE.
5. Link the real code-mode host and run a side-effect-free command under Wine.

No layering checks, MSVC-host implementation, prebuilt publication, or release
changes. This continuation tests Rust's direct native-link path, not a new
`cc_common.link` action. The CLI itself does not contain V8; V8 belongs to the
separate code-mode-host executable.

## Commands

Run in the Codex checkout. Common Windows x64 proof invocation:

```sh
bazel build --config=buildbuddy-generic-rbe --host_platform=//:rbe \
  --disk_cache= --remote_download_minimal \
  --repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1 \
  --repo_env=BAZEL_WINDOWS_SDK_EULA=1 \
  --features=-dynamic_link_msvcrt --features=static_link_msvcrt \
  --features=cargo-rebase-json-vfs-overlays \
  --platforms=@llvm//platforms:windows_x86_64_msvc \
  --extra_execution_platforms=//:rbe,//bazel/platforms:linux_x86_64_rbe \
  //codex-rs/code-mode-host:codex-code-mode-host --verbose_failures
```

The artifact-inspection run restores the repository's top-level download policy
with `--remote_download_outputs=toplevel` and additionally sets:
`--remote_download_regex='.*(mksnapshot.exe|generated_snapshot_files_windows/(embedded.S|snapshot.cc))$'`.
The initial regex omitted the leading `.*` and did not download those cached
transitive outputs; the corrected inspection run below did.

The same Windows configuration separately builds:

- `//third_party/v8:v8_152_2_0_x86_64_pc_windows_msvc_bazel`
- `//third_party/v8:src_binding_x86_64_pc_windows_msvc_152_2_0_bazel`
- `@llvm//tests/cxxstdlib_settings:defaults`
- `@llvm//tests/cxxstdlib_settings:headers_only`
- `@llvm//tests/cxxstdlib_settings:libraries_only`
- `@llvm//tests/cxxstdlib_settings:both`

The settings matrix also builds for `--platforms=//:rbe`, omitting the
Microsoft EULA and CRT feature arguments. Each scenario builds target and
execution binaries and asserts compile/link/runtime-provider policy.

Bindgen regression:

```sh
bazel test --config=buildbuddy-generic-rbe --host_platform=//:rbe \
  --platforms=//:rbe --disk_cache= --remote_download_minimal \
  @rules_rs//rs/private:bindgen_tests
```

The final test run adds
`@rules_rust//cargo/private/cargo_build_script_runner:test` and `:bin_test`.
The static-CRT/path regression uses the Windows command above with
`//tools/msvc_overlay_probe:cargo_probe`.

## Failure, owner, correction ledger

| Invocation | Observation | Owner and correction |
| --- | --- | --- |
| `cad69dcb-8faf-486c-bc99-f307c5222b68` | Windows ICU sees both Chromium and toolchain C++ headers. | LLVM lacked independent standard-library opt-outs; add target-scoped settings without altering CRT or optimization policy. |
| `91613132-5a7e-4946-b3da-d650a982a63d` | Windows header collision gone; Linux generator still collides. | V8 integration: target scope intentionally resets at exec transitions; explicitly select private runtime on V8 generator binaries. |
| `66c7eabe-43a5-4208-87b6-a97f16a19a84` | Generator wrapper resolves its select label in `@v8`. | Project Starlark: anchor the label in the defining repository. |
| `268923f5-0a86-4d38-9aad-2efc04d1cc6d` | Pinned Abseil uses an attribute deprecated by Clang 23; V8 treats it as an error. | Pinned source compatibility: backport Abseil `0784689a65b4ea1329fbc5174b8a57c88ec796a9`; keep warning policy. |
| `f112c1cd-cbb3-4d09-b9c6-f5ad5d03b877` | Prebuilt bindgen parser rejects Clang 23 resource intrinsics; also reports missing `max_align_t`. | Parser/resource version mismatch: source-build bindgen with selected LLVM. Treat the second error separately. |
| `2c42bffc-5965-4f6a-b117-fcde3f55c899` | GitHub API archive URL has no recognized suffix. | Project repository declaration: provide `type = "tar.gz"`. |
| `993d2940-2b33-49e6-97b9-f403646384df` | Incorrect `archive_type` spelling rejected. | Implementation error: verified `http_archive` uses `type`. |
| `87b82c0e-86d9-4837-8d11-7ea0f19c22c4` | Importing bindgen as a module conflicts with Codex's Rust toolchain registration. | Project dependency composition: consume only its pinned Cargo manifest/lockfile through `http_archive`; do not import producer toolchain policy. |
| `bcdc1ec1-454d-4515-83e9-0ac80f797e9d` | Matching libclang fixes intrinsic errors; `max_align_t` still absent. | rules_rs bindgen normalization promotes `/imsvc` SDK roots ahead of builtin headers. Guarded correction under explicit `-nostdlibinc`, preserving native-discovery and `/external:I` behavior. |
| `630f265d-7d6a-47d9-9d0e-fd759d7d29c1` | New ordering regression fails against unchanged normalizer. | Required failing control. |
| `21328d04-39bb-44f2-964e-66ce1c19a768` | All three bindgen helper tests pass after correction. | Same regression, including joined/separate paths and option-looking operands. |
| `2d29b239-c507-4b8c-a696-95bc09a74d79` | Full code-mode-host link requests unavailable dynamic `msvcprt.lib`. | rules_rust target metadata: `rustc --print=cfg` omitted configured target flags. rusty_v8's existing static/dynamic selection was correct; no crate patch or dynamic CRT fallback. |
| `8237b281-8ea9-47f8-ab6d-d3ed5638acb5` | Real Cargo probe cannot see configured `crt-static`. | Failing control for the target-feature regression. |
| `62c8982f-aa4c-40e0-9dc0-d692278e3fc1` | Target-feature probe passes after flags are forwarded. | Initial fix; review then identified the separate build-script compilation flags boundary. |
| `74562cf9-de78-4e27-bcb1-947e5bddf056` | `@$(location ...)` response-file probe fails in the target cfg query. | Implementation regression reproduced from review. Separate configured target flags from the host build-script executable's `rustc_flags`; preserve its legacy environment exposure. |
| `4941fbb0-4b8e-4daa-aa58-48554aeb2a14` | Corrected runner passes the real response-file/static-CRT/SDK probe and full host build. | No remaining review finding; target/exec flag selection follows the consuming configuration. |

The SDK-overlay cwd problem is separately owned by the Cargo runner adapter,
not LLVM's overlay generator. See `../../tools/msvc_overlay_probe/README.md`.
Codex commit `36bb2cb` isolates that previously proven direct-link/VFS work.

The Mac briefly had under 500 MiB free. Builds switched to minimal downloads
with shared disk caching disabled. The user freed space manually; no cache or
source deletion was performed. An overbroad union aquery produced a large
report; its redundant follow-up (`32752c45-4496-49b8-af79-176e75d98e0a`) was
cancelled during reporting. Neither is a compiler/build failure.

## Completed evidence

| Invocation | Result |
| --- | --- |
| `efab29a0-055e-416b-a3a1-fbd2ba4c7fb7` | Four Windows x64 settings combinations pass, 21.167s. All four PE files are AMD64, import only KERNEL32.dll, and print `replacement runtime: 42` under Wine, exit 0. |
| `ebf1f091-4f99-4aba-9836-cc3c24a1b39b` | Four Linux ARM64 settings combinations pass, 19.706s. Static and dynamic unwinder providers remain; exec scope assertions pass. Linux binaries not executed. |
| `080e07bc-130e-43bf-a0da-6ed067cb744d` | V8 Windows x64 source archive passes, 154.792s. Windows mksnapshot links with private libc++ and runs under declared Wine. |
| `4836e575-abd2-4e32-a247-d8a7ea2824b4` | Matching Windows Rust bindings pass, 15.259s. Diagnostic paths now confirm Clang's builtin `__stddef_offsetof.h`, not the SDK fallback. |
| `3c24d988-f1c7-446c-8d80-a6892d4159a4` | Archive action graph inspected. Windows mksnapshot uses Linux ARM64 clang-cl, `--target=x86_64-pc-windows-msvc`, `/MACHINE:X64`, `/MT`, SDK/static CRT search roots, private `libcxx_native_windows.lib`, and no implicit `/DEFAULTLIB:libc++.lib`. Wine snapshot action selects Linux x64. |
| `0aeaf63f-4582-47c5-bc52-fbc0415a9e3b` | First full static-CRT host link passes, 94.127s; superseded by the reviewed flags-boundary correction below. |
| `4941fbb0-4b8e-4daa-aa58-48554aeb2a14` | Full host and Cargo probe pass with the corrected runner, 63.493s. |
| `039d2565-916c-4c5f-87fd-fce239a0aa2f` | Five runner/bindgen test targets pass, 15.663s. |
| `25ffd6a3-6a83-48c7-99a1-3a2d48bb6ccb` | Successful artifact-download run, 18.698s. Downloaded host, Windows mksnapshot, snapshot source, and embedded assembly. |
| `b3fccc7e-e707-400f-8533-cc90c7ab205b` | Final host Rustc action: Linux ARM64 exec, Windows x64 MSVC target, `+crt-static`, `/MACHINE:X64`, `/lldignoreenv`, SDK/static CRT roots. Both rules_rs's linker symlink and underlying `@llvm` lld-link are declared inputs; no user-home/installed Visual Studio arguments. |
| `3cf19b7a-4c68-4aa6-9beb-36b0e28a8d88` | Both Linux and Windows ICU compile actions inspected. Materialized Windows parameters use `/clang:-nostdinc++`, `/MT`, Chromium libc++ headers, declared SDK roots, and no toolchain C++ header root. |
| `f67e3027-98da-4663-95ce-edcb11a43c90` | Final source-built bindgen action uses the selected LLVM resource headers, corrected `-idirafter` ordering, and `-fms-runtime-lib=static`. |
| `6c27b066-c0a7-4440-a61e-87d160c1c013` | Final combined real CLI and code-mode-host build passes, 396.555s. Recompiles Rust dependents affected by the target-metadata correction. |
| `6989d4b7-5ae8-4a80-8c29-e748dd26a3fa` | Final CLI Rustc action again confirms direct @llvm lld-link, Linux ARM64 exec, x64 MSVC target, static CRT and declared SDK inputs, with no ambient user/install paths. |

Raw logs/action reports live in the dedicated project's `outputs/` directory,
not the repository. `current-msvc-v8-selected-actions.json` contains the
snapshot/link commands; `current-msvc-v8-bindgen.aquery.json` records the
pre-correction binding arguments. The LLVM settings matrix reports are
`@llvm//tests/cxxstdlib_settings:contract` outputs under each configuration.

The final Rust executable intentionally retains the ordinary LLVM C++ runtime
default for non-V8 dependencies. The two opt-outs are scoped to V8's private
profile; neither the proof nor the implementation claims to remove the default
runtime from the entire consumer graph. Its Windows mksnapshot link has no
implicit LLVM libc++ default and explicitly links the Chromium runtime.

The corrected rusty_v8 build-script output is:

```text
-lstatic=rusty_v8
-ldylib=winmm
-ldylib=dbghelp
-llibcpmt
```

### Artifacts and execution

`llvm readobj --file-headers --coff-imports` identifies both executables as
`IMAGE_FILE_MACHINE_AMD64 (0x8664)`. Neither imports `msvcp`, `vcruntime`, or
`ucrtbase` DLLs. mksnapshot imports only WINMM, dbghelp, ADVAPI32, and KERNEL32.
The host additionally imports Windows system libraries (networking, crypto,
COM, UI, and synchronization); inspecting imports does not execute that behavior.

SHA-256:

- code-mode-host: `86ad37e6a1ae9a975071df27a74eabd0af57f49909591923fe31d2b29e3f8567`
- mksnapshot: `76f718b86435bd9f591758cd3d04c82fa96e5fad03e8b146da21df87e12d0689`

Preserved as `outputs/codex-code-mode-host-x86_64-msvc-private-libcxx.exe` and
`outputs/mksnapshot-x86_64-msvc-private-libcxx.exe` at the dedicated project root.
The downloaded generated `embedded.S` contains `.xdata` at line 80424 and
`.pdata` at line 80434, confirming the Windows unwind writer ran.

With a new isolated prefix `/tmp/codex-code-mode-wine.1VX78q`:

```sh
env WINEPREFIX=/tmp/codex-code-mode-wine.1VX78q WINEARCH=win64 WINEDEBUG=-all \
  WINEDLLOVERRIDES='mscoree,mshtml=' /opt/homebrew/bin/wine \
  /Users/corentinkerisit/Documents/Codex/2026-08-28/codex-cli-windows-msvc-toolchain/work/codex-msvc-current/bazel-out/windows_x86_64_msvc-fastbuild/bin/codex-rs/code-mode-host/codex-code-mode-host.exe \
  --help
```

Exit 0; output begins `Usage: codex-code-mode-host.exe [OPTIONS]`. The source
calls `Cli::parse()` before runtime/telemetry startup, so this command does not
authenticate, load user data, start listeners, or exercise networked behavior.
It is not a JavaScript-evaluation test. Windows mksnapshot execution on RBE
does exercise V8 initialization and snapshot generation with the private runtime.

The final combined build used the common Windows command with both
`//codex-rs/cli:codex` and `//codex-rs/code-mode-host:codex-code-mode-host`, plus
`--remote_download_regex='.*(codex[.]exe|crates__github[.]com_seanh-oai_rusty_v8[.]git_350c5a85/_bs[.](linkflags|flags|linksearchpaths))$'`.
The final CLI is also AMD64 and imports no VC redistributable DLLs. SHA-256:
`08ecae5fb788f7feed57848a108c6e6edf05bcc080d4b219dbac8ddcb7f65313`.
Preserved as `outputs/codex-current-x86_64-msvc-final.exe`.

Using the same isolated Wine prefix and environment, the exact executable
`work/codex-msvc-current/bazel-out/windows_x86_64_msvc-fastbuild/bin/codex-rs/cli/codex.exe`
(absolute path under the dedicated project) with `--version` exits 0 and prints
`codex-cli 0.0.0`. Output: `outputs/current-msvc-cli-final-wine-version.txt`.
No authentication, networked product command, or user-data access was exercised.

### Replaying action inspection

Use the same common Windows arguments, replace `build` with `aquery`, and add
`--include_param_files --output=jsonproto` plus one expression at a time:

```text
mnemonic("Rustc", //codex-rs/code-mode-host:codex-code-mode-host)
inputs(".*putil.cpp", mnemonic("CppCompile", deps(//third_party/v8:v8_152_2_0_x86_64_pc_windows_msvc_bazel)))
mnemonic(".*Bindgen.*", deps(//third_party/v8:src_binding_x86_64_pc_windows_msvc_152_2_0_bazel))
```

The compile/bindgen inspections also used `--noinclude_artifacts`. Clang-cl's
Windows compile parameters live in a separately materialized `.obj.params`
file, copied to `outputs/current-msvc-v8-windows-icu.params`. Input declarations
for the final Rust action are summarized in
`outputs/current-msvc-code-mode-host-final-inputs.txt`.

## Extractable changes and remaining validation

LLVM commit `6cc810fe3aba4d87192531de7c24974472f9f60d` is standalone. Suggested
future PR motivation: allow consumers supplying their own C++ runtime to opt
out independently from default headers and libraries, using compiler semantics
and target-scoped settings, without changing CRT, unwinder, or default policy.

Separate Codex commits:

- `36bb2cb86b2b787db4c5ce0eeb2d2f5e24f49ade`: direct MSVC links and Cargo overlay rebasing.
- `cf44db7ce8a4e9493802a521a44f4dfb565ea8cc`: correct Cargo target-feature metadata; preserve build-script response-file inputs.
- `13f73122ff6f29d29fe513a8978a01e05e86b06f`: preserve clang-cl header precedence in bindgen, with fail-before/pass-after regression.
- `3f0ad9ddb32beab24f3fcc602e2401faace53b8a`: source-built V8/bindgen, private libc++, declared Windows snapshot execution, and consumer configuration.

ARM64 Windows, native Windows execution, macOS/MinGW setting combinations,
JavaScript evaluation through code-mode-host, and full release packaging are
not proven by these results. Native bindgen discovery behavior is intentionally
unchanged, not newly validated. No push, PR, or publication was performed.
