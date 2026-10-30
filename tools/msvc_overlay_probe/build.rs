use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    let source = out.join("overlay_probe.c");
    fs::write(&source, "#if !__has_include(<WlanTypes.h>)\n#error CASE_OVERLAY_LOOKUP_FAILED\n#endif\n").unwrap();
    let flags = env::var("CFLAGS").unwrap();
    // This action's execroot and toolchain paths contain no whitespace.
    // Do not infer general cc-rs flag quoting coverage from this probe.
    let result = Command::new(env::var_os("CC").unwrap())
        .args(flags.split_whitespace())
        .args(["/E", "/TC"])
        .arg(&source)
        .output()
        .unwrap();
    assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
    let report = format!("manifest cwd: {}\nCC: {}\nCFLAGS: {flags}\nchanged-directory SDK lookup: PASS\n",
        env::current_dir().unwrap().display(), env::var("CC").unwrap());
    fs::write(out.join("overlay-proof.txt"), report).unwrap();
}
