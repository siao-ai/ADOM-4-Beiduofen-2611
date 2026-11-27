#!/usr/bin/env python3 -B
"""Cross-compile adom.c for a bare-metal Cortex-M4 (thumbv7em-none-eabi, -ffreestanding, no libc)
and report flash / RAM use from the ELF section headers.  Compile-only: nothing is flashed.

    python3 -B ports/c/mcu_size.py [extra clang flags...]
"""
import os, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
FLAGS = ["--target=thumbv7em-none-eabi", "-mcpu=cortex-m4", "-mthumb", "-ffreestanding", "-fno-builtin",
         "-nostdlib", "-Os", "-std=c99", "-pedantic", "-Wall", "-DADOM_NO_MAIN",
         "-DADOM_MAX_CP=2048", "-DADOM_MAX_LABELS=256", "-DADOM_MAX_STARTS=512",
         "-DADOM_SEEN_SLOTS=1024", "-DADOM_SEEN_ARENA=8192", "-DADOM_MAX_SHORT=24"]

def sections(path):
    b = open(path, "rb").read()
    assert b[:4] == b"\x7fELF" and b[4] == 1, "expected ELF32"
    shoff, = struct.unpack_from("<I", b, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", b, 0x2E)
    sh = [struct.unpack_from("<IIIIIIIIII", b, shoff + i * shentsize) for i in range(shnum)]
    stro = sh[shstrndx][4]
    name = lambda off: b[stro + off:b.index(b"\0", stro + off)].decode()
    return [(name(s[0]), s[1], s[2], s[5]) for s in sh]   # name, type, flags, size

def main():
    out = os.path.join(tempfile.mkdtemp(), "adom_cm4.o")
    cmd = ["clang"] + FLAGS + sys.argv[1:] + ["-c", os.path.join(HERE, "adom.c"), "-o", out]
    subprocess.run(cmd, check=True)
    flash = ram = 0
    for n, t, fl, size in sections(out):
        if not fl & 2: continue                      # SHF_ALLOC
        if t == 8: ram += size                       # SHT_NOBITS (.bss)
        elif fl & 1: ram += size; flash += size      # writable data: lives in both
        else: flash += size                          # .text / .rodata
    print("target: thumbv7em-none-eabi (Cortex-M4), freestanding, no libc, -Os")
    print("flash (.text+.rodata+.data): %d bytes (%.1f KiB)" % (flash, flash / 1024))
    print("static RAM (.data+.bss):    %d bytes (%.1f KiB)" % (ram, ram / 1024))
    undef = subprocess.run(["nm", "-u", out], capture_output=True, text=True).stdout.split()
    print("undefined external symbols:", [u for u in undef if u not in ("U",)] or "none")

if __name__ == "__main__":
    main()
