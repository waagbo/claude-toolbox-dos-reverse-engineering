# dos-re-toolbox

An Ubuntu 24.04 container for disassembling and reverse-engineering
1990s DOS binaries — Watcom LE executables under DOS/4GW in particular —
and the data formats they read. It packages the toolset the
Cyberia (1994) / Cyberia 2 (1995) reversal actually ran on, plus generic
versions of that project's helper scripts, and a Claude Code skill
(`.claude/skills/dos-re-toolbox/`) that documents how to use them.

## Quick start

```bash
./rebox build                     # build the image (bakes in your uid/gid)
cd ~/code/some-re-project
~/code/dos-re-toolbox/rebox shell # bash in the container, $PWD at /work

# inside:
le-unpack GAME.EXE out/                       # LE objects -> out/objN.bin + le_report.txt
flatdis out/obj1.bin 0x10000 > out/obj1.asm   # objdump listing at the link base
le-fixups GAME.EXE > out/fixups.tsv           # internal relocations
asmview out/obj1.asm -f out/fixups.tsv -s out/obj2.bin@0x40000 --func 0x1d78c

ghidra-import ghidra-proj game GAME.EXE       # import + auto-analyse (slow)
ghidra-dump ghidra-proj game GAME.EXE out/decomp   # pseudo-C per function + _index.tsv

dosdbg -C cdrive GAME.EXE                     # DOSBox-X debugger, headless, in tmux
dbgdrive send 'BPINT 21 3D'; dbgdrive run; dbgdrive regs
```

### Prebuilt image

Every version tag publishes the image to GHCR
(`.github/workflows/release-image.yml`):

```bash
docker pull ghcr.io/waagbo/claude-toolbox-dos-reverse-engineering:latest   # or :1.0.0
REBOX_IMAGE=ghcr.io/waagbo/claude-toolbox-dos-reverse-engineering:latest ./rebox shell
```

The published image bakes in uid/gid 1000; if your host uid differs, run
`./rebox build` instead so files under `/work` stay yours.

`rebox` works with Docker or Podman (Podman gets `--userns=keep-id`, so
files written under `/work` stay yours). `./rebox run DIR -- CMD…` runs a
single command; `./rebox gui` starts the Ghidra GUI on your X11 display.

## What is in the image

| Tool | Version | Used for |
|---|---|---|
| Ghidra (`analyzeHeadless`, `ghidraRun`) | 12.0.4, JDK 21 | import, auto-analysis, decompiler corpus |
| ghidra-lx-loader | v12.0.1 jar, version-patched to 12.0.4 | LE (DOS/4GW), LX (OS/2), VxD loaders |
| GNU binutils `objdump` | 2.42 | raw i386/i8086 listings of flat object images — the source of truth |
| `nasm` / `ndisasm` | distro | 16-bit stubs and overlays |
| DOSBox-X | 2026.05.02, built from source with `--enable-debug=heavy` | built-in debugger (`DEBUGBOX`, `BP`, `BPINT`, `BPLM`, `SM`) — Ubuntu's package is built without it |
| tmux | distro | drives that debugger headless |
| ffmpeg | 6.1 | decode/transcode video (incl. Interplay C93), render mp4/wav artifacts |
| Python 3.12 + Pillow | distro | format probes, PNG rendering |
| graphviz, ImageMagick | distro | state/call graphs, contact sheets |
| gcc, make, gdb, SDL2 dev | distro | building and debugging a native C99 port headless |
| unzip, 7z, xxd, hexdump, jq, file | distro | archive/installer extraction, byte inspection |

Toolbox scripts (on `PATH`, all `--help`/no-arg self-documenting):

| Script | What |
|---|---|
| `le-unpack EXE OUT` | page-assemble each LE object into `objN.bin` at its link base, write `le_report.txt` (bases, entry, objdump commands) |
| `le-fixups EXE` | internal-reference fixup table as TSV, with per-page desync check |
| `flatdis FILE BASE [START [STOP\|+LEN]]` | `objdump -D -b binary -M intel --adjust-vma` wrapper |
| `asmview LISTING -f FIXUPS …` | listing range / function / xrefs with fixup targets and string literals resolved |
| `ghidra-import`, `ghidra-dump` | headless import, and the per-function decomp dump (`GhidraDumpDecompArg.java`) |
| `decomp-diff` | address-normalised diff of one function across two builds |
| `iso-extract` | pure-Python ISO9660 extractor |
| `dosdbg`, `dbgdrive` | DOSBox-X debugger session in tmux + its Python driver for scenario scripts |

## Pins and upgrades

Ghidra and the LX loader are pinned by URL **and** SHA-256 as build args
in the `Dockerfile`; DOSBox-X by release tag (`DOSBOX_X_TAG`, compiled in
a builder stage — the first build takes a while). To move Ghidra: change `GHIDRA_VERSION`,
`GHIDRA_DATE` (the date stamp in the release zip's name) and
`GHIDRA_SHA256` (printed in the GitHub release notes). The loader's
`extension.properties` is rewritten to the running Ghidra version; if a
future Ghidra changes the loader API, the import will fail loudly and a
loader rebuild (`gradle -PGHIDRA_INSTALL_DIR=/opt/ghidra` in the loader's
source tree) is needed.

## Releasing

```bash
gh release create v1.2.3 --generate-notes   # tag -> workflow -> ghcr.io/…:1.2.3, :1.2, :1, :latest
```

## Using the skill

`.claude/skills/dos-re-toolbox/` is a Claude Code skill. It is active in
sessions started inside this repo; to use it from any project, link it:

```bash
ln -sfn "$PWD/.claude/skills/dos-re-toolbox" ~/.claude/skills/dos-re-toolbox
```

## Not included

Game data and binaries — mount your own workspace. Emscripten (the
Cyberia port's wasm build) and Spice86 are not part of this image.
