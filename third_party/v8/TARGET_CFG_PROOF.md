This report preserves the verification performed on consumer commit `35d088e984030f1d967cec52f1ae14caf8367059`. The source snapshot retains its existing local LLVM override and prerequisite integration patches; it is not a claim of an unmodified fresh-clone build. Large output binaries, local caches and Wine prefixes are not part of this source backup.

# PR #101 narrow revision proof

PR: https://github.com/hermeticbuild/rules_rust/pull/101

## Source identities and scope

- PR worktree: `/Users/corentinkerisit/Documents/Codex/2026-08-28/codex-cli-windows-msvc-toolchain/work/rules_rust-target-cfg-revision`
- Branch: `codex/cargo-target-rustflags`; base `2ab43f0bbaa406ffb1a0dd64ae2ecb8f7734f733`.
- Production revision: `539fdde4da8e646e52e06f378cac17add55503c2`.
- Regression revision / final PR head: `7af88118f828632c17b9db5b72517172afea4ae7`.
- Baseline worktree: `work/rules_rust-target-cfg-baseline`, local branch `codex/cargo-target-cfg-baseline`, commit `0ecdf6644b58d7ed443f9add2ebff09073471a4c`. Only the identical new fixture is added to the PR base. Intentionally failing proof, not pushed.
- Consumer worktree: `work/codex-target-cfg-consumer`, local branch `codex/cargo-target-cfg-consumer`, commit `35d088e984030f1d967cec52f1ae14caf8367059`, based on existing consumer `26a8a94`. Only `patches/rules_rust_cargo_target_flags.patch` changed. Not pushed.
- Consumer LLVM: existing clean `work/hermetic-llvm-cxx-stdlib`, `3ddcf979c40e9b4acd949eabe388bf933bc958e7`, read-only.

The production change shares configuration-wide flag collection and passes ordered repeated runner arguments to the target cfg query. No invented crate type/root. Existing compiler flag order and target/exec selection are preserved. `CARGO_ENCODED_RUSTFLAGS` is unchanged from the PR base. No new public API, global/per-crate build-script support, or default CRT policy.

The consumer patch is the exact production net diff at one context line, adjusted solely because its pre-existing release-profile patch already imports `collect_extra_rustc_flags`. All other patches were preserved: build-script tool transition, clang-cl paths, JSON VFS overlays (#100), prost, release profile, direct MSVC link arguments (#102), clang-cl forwarding, process-wrapper temporary outputs/parameter files, execroot separators and THP. Existing rules_rs/native bindgen/V8 integration fixes also remain. This is integration-stack proof, not a claim that #101 alone ports Codex to Windows.

## Before / after regression

In each rules_rust worktree, Bazel 9.1.0:

```sh
USE_BAZEL_VERSION=9.1.0 bazel test --config=remote \
  --extra_toolchains=@llvm//toolchain:all \
  --platforms=@llvm//platforms:macos_aarch64 \
  --@rules_cc//cc/toolchains/args/archiver_flags:use_libtool_on_macos=False \
  //test/cargo_build_script/target_cfg:target_cfg_test \
  --test_output=errors
```

- Baseline invocation `56fd36dd-5cb4-45bc-ac5c-3a9f5f4d67d3`: failed in the real build.rs assertion, missing `crt-static`; actual features `cmpxchg16b,fxsr,sse,sse2,sse3`. Not a fixture-loading failure.
- Revised invocation `b22758d0-775f-4a2a-b4b2-2c08178ac389`: all eight tests passed, using the same command plus `//cargo/private/cargo_build_script_runner:bin_test //test/toolchain:toolchain_test_suite //test/unit/extra_rustc_flags:all`.
- Exact fixture equality verified with `git diff codex/cargo-target-cfg-baseline HEAD -- test/cargo_build_script/target_cfg` (empty).
- Fixture selects a real native rustc/toolchain input closure for a Windows cfg query; no internal env or TARGET override. Split `-C`/`target-cpu=x86-64` then `-Ctarget-cpu=x86-64-v3` tests argument boundaries/order. `crt-static` and `avx2` present. `avx512f` absent (exec and rlib-only flags excluded). Native build.rs asserts its response-file cfg is present, while target features exclude the script-only cfg.

Focused aquery invocation `4d025b74-633e-4e24-8786-63ee904aa67c`, saved `target-cfg-revision-aquery.json`. The action contains ordered sysroot / split CPU / v3 / crt-static arguments; TARGET Windows and HOST aarch64-apple-darwin. Its 143 declared inputs include rustc, compiler driver/LLVM and rustlib data. The executable-only response file is not a Cargo run input. Legacy CARGO encoded flags retain the raw `@$(location script_flags)` entry, unchanged, and are not reused for the cfg query.

Formatting: buildifier check, rustfmt check, `git diff --check` pass. Existing unrelated buildifier lint warnings were not changed. The first symlinked rustfmt invocation lacked its matching driver library; the check succeeded with the complete cached rustfmt distribution, without repository or toolchain changes.

## Real consumer command and results

From `work/codex-target-cfg-consumer`, Bazel 9.2.0. The endpoint-bearing config includes the repository's `remote` config.

```sh
bazel build --config=buildbuddy-generic-rbe --host_platform=//:rbe \
  --disk_cache= --remote_download_minimal \
  --repo_env=BAZEL_MSVC_RUNTIME_VISUAL_STUDIO_EULA=1 \
  --repo_env=BAZEL_WINDOWS_SDK_EULA=1 \
  --features=-dynamic_link_msvcrt --features=static_link_msvcrt \
  --features=cargo-rebase-json-vfs-overlays \
  --platforms=@llvm//platforms:windows_x86_64_msvc \
  --extra_execution_platforms=//:rbe,//bazel/platforms:linux_x86_64_rbe \
  --remote_download_regex='.*(binding_generated_152_2_0.rs|/codex.exe|/codex-code-mode-host.exe|rusty_v8.*_bs\.(flags|linkflags|linksearchpaths))$' \
  //third_party/v8:v8_152_2_0_x86_64_pc_windows_msvc_bazel \
  //third_party/v8:src_binding_x86_64_pc_windows_msvc_152_2_0_bazel \
  //codex-rs/cli:codex //codex-rs/code-mode-host:codex-code-mode-host \
  --verbose_failures
```

- Initial revised-files build `b90fd2a0-0ba4-4f4b-ae9f-c8547c325cab`: passed all four targets, 189.081 seconds; 35,266 processes: 22,629 remote cache hits, 12,403 internal, 234 remote. Initial download regex used `v8_152_2_0.*` in place of `rusty_v8.*_bs`, so the committed replay above downloaded the small metadata files.
- Committed replay `8d7664e5-2ad0-41cd-b309-70d238c1167a`: passed all four targets, 47.372 seconds; 35,261 action-cache hits, one remote-cache hit, two internal and two remote actions. Log: `target-cfg-consumer-committed-replay.log`.
- Profile inspection: native V8 static-archive and merge action intervals contain remote cache checks and no remote-execution event. V8 CargoBuildScriptRun contains an actual 9.754279-second remote-execution event. No fresh V8 C++ recompilation is claimed.
- Consumer aquery `a439d1a9-8497-4787-9a81-a15740be35e7`: `target-cfg-consumer-aquery.json`. Windows V8 query: HOST `aarch64-unknown-linux-gnu`, TARGET `x86_64-pc-windows-msvc`, Linux RBE execution platform, sysroot and `-Ctarget-feature=+crt-static` runner arguments. Exec-config V8 query separately has Linux TARGET and no crt-static.
- Windows V8 run has 7,769 declared inputs, including revised runner, Linux rustc/driver/LLVM, Windows libstd and source-built `rusty_v8_native_windows.lib`. That library is generated by llvm-lib from V8 native objects plus compiler-rt; graph does not select the downloaded prebuilt V8 archive.
- Actual `_bs.linkflags`: `-lstatic=rusty_v8`, `-ldylib=winmm`, `-ldylib=dbghelp`, `-llibcpmt`; no `msvcprt`. Path: `bazel-bin/external/rules_rs++crate+crates__github.com_seanh-oai_rusty_v8.git_350c5a85/_bs.linkflags`.
- Both final Rustc actions target Windows with crt-static. Both downloaded outputs are PE32+ AMD64. `llvm readobj --file-headers --coff-imports` found no dynamic MSVC/UCRT runtime DLL imports; details saved in `target-cfg-consumer-imports.txt`.
- CLI SHA256 `5446b73a47a2fbb7bf43d54ac5708a94472e65162ceaacbca8ed213c9be5cd99`.
- Code-mode-host SHA256 `86ad37e6a1ae9a975071df27a74eabd0af57f49909591923fe31d2b29e3f8567`.

## Safe runtime smoke

Fresh task-owned Wine prefix `/tmp/codex-target-cfg-wine.5jqJqn`, `WINEARCH=win64 WINEDEBUG=-all`:

```sh
/opt/homebrew/bin/wine bazel-bin/codex-rs/cli/codex.exe --version
/opt/homebrew/bin/wine bazel-bin/codex-rs/code-mode-host/codex-code-mode-host.exe --help
```

Both exit 0. CLI prints `codex-cli 0.0.0`; host prints its CLI help. Logs: `target-cfg-consumer-cli-version.log`, `target-cfg-consumer-code-mode-help.log`. This validates loading/startup, not V8 JS evaluation, authentication, networking or complete product functionality. Native Microsoft compiler support is not added or claimed.

## Publication gate

Independent narrow production/test review found no findings. Parent approved publication conditional on the successful consumer/artifact checks above. Original shared rules_rust, consumer and LLVM checkouts stayed clean and unchanged. Only PR #101 branch is authorized for push; baseline and consumer commits stay local.

Published with a normal fast-forward push, `b0ef263c0..7af88118f`, and the concise PR description updated. `gh pr view` and `git ls-remote` independently confirm remote head `7af88118f828632c17b9db5b72517172afea4ae7`, base unchanged, PR open. Final `check-runs` query returns `total_count: 0`; `gh pr checks` reports no checks and branch run listing is empty. Repository Actions permissions and workflow states currently say enabled/active, so the earlier disabled-CI observation is not asserted as current. No workflow mutation, CI dispatch, merge, rebase or force push performed.
