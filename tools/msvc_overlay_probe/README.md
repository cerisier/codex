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
The likely owning fix is in hermetic-llvm: make both classes of paths relative
to the overlay file and emit LLVM's `root-relative: overlay-dir` and
`overlay-relative: true` settings. This proposal has not been implemented or
validated; the hermetic-llvm checkout remains untouched.
