# dos-re-toolbox — Ubuntu 24.04 workbench for disassembling and reverse
# engineering 1990s DOS / DOS-extender binaries (Watcom LE under DOS/4GW,
# MZ, flat images) and their data formats.
#
# The toolset is the one the Cyberia (1994) / Cyberia 2 (1995) reversal
# actually used: Ghidra headless + the LX/LE loader, GNU objdump on flat
# object images, the DOSBox-X debugger driven through tmux, ffmpeg for
# A/V artifacts, Python 3 + Pillow probes, graphviz, and an SDL2 C toolchain
# for headless ports.
#
#   ./rebox build          # (or: docker build -t dos-re-toolbox .)
#   ./rebox shell          # interactive shell, $PWD mounted at /work

# --- stage 1: DOSBox-X with the debugger -----------------------------------
# Ubuntu's dosbox-x package is configured WITHOUT the debugger (C_DEBUG off:
# DEBUGBOX just runs the program, no ncurses UI ever appears). Build it the
# way the Cyberia host did: upstream's build-debug script = internal SDL 1.x
# + ./configure --enable-debug=heavy.
FROM ubuntu:24.04 AS dosbox-x
ARG DEBIAN_FRONTEND=noninteractive
ARG DOSBOX_X_TAG=dosbox-x-v2026.05.02
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git build-essential autoconf automake libtool autogen pkg-config \
        nasm libncurses-dev libpcap-dev libslirp-dev libfluidsynth-dev \
        libavformat-dev libavcodec-dev libswscale-dev libfreetype-dev \
        libxkbfile-dev libxrandr-dev libpng-dev zlib1g-dev libasound2-dev \
        libx11-dev libxext-dev libgl-dev libglu1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${DOSBOX_X_TAG}" https://github.com/joncampbell123/dosbox-x.git /src/dosbox-x
WORKDIR /src/dosbox-x
RUN sed -i 's/^make -j3/make -j"$(nproc)"/' build-debug \
    && ./build-debug \
    && make install DESTDIR=/out

# --- stage 2: the workbench --------------------------------------------------
FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# --- system packages --------------------------------------------------------
# binutils       objdump -b binary -m i386 (the asm source of truth)
# openjdk-21-jdk Ghidra 12 needs JDK 21+; full JDK (not -headless) so the
#                Ghidra GUI also works over X11
# lib*           runtime libraries of the stage-1 DOSBox-X build
# tmux           drives the DOSBox-X debugger headless (send-keys / capture-pane)
# ffmpeg         c93 (Interplay) decoding, mp4/wav artifact rendering
# graphviz       dot -Tsvg/-Tpng for state/call graphs
# imagemagick    montage/convert for contact sheets of extracted frames
# libsdl2-dev    building the native C99 port (SDL_VIDEODRIVER=dummy headless)
# nasm           ndisasm for 16-bit real-mode stubs objdump handles poorly
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git unzip zip xz-utils p7zip-full file jq less \
        bsdextrautils xxd vim-tiny \
        binutils build-essential gdb pkg-config libsdl2-dev nasm \
        python3 python3-pil python3-venv python3-pip \
        openjdk-21-jdk \
        tmux libncurses6 libpcap0.8t64 libslirp0 libfluidsynth3 libfreetype6 \
        libxkbfile1 libxrandr2 libpng16-16t64 libasound2t64 libgl1 libglu1-mesa \
        ffmpeg graphviz imagemagick \
    && rm -rf /var/lib/apt/lists/*

# DOSBox-X (debugger build) from stage 1; fail the build on a missing library
COPY --from=dosbox-x /out/usr/ /usr/
RUN ! ldd /usr/bin/dosbox-x | grep 'not found' \
    && dosbox-x --version | head -1

# --- Ghidra ------------------------------------------------------------------
ARG GHIDRA_VERSION=12.0.4
ARG GHIDRA_DATE=20260303
ARG GHIDRA_SHA256=c3b458661d69e26e203d739c0c82d143cc8a4a29d9e571f099c2cf4bda62a120
RUN curl -fsSL -o /tmp/ghidra.zip \
        "https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_DATE}.zip" \
    && echo "${GHIDRA_SHA256}  /tmp/ghidra.zip" | sha256sum -c - \
    && unzip -q /tmp/ghidra.zip -d /opt \
    && mv /opt/ghidra_${GHIDRA_VERSION}_PUBLIC /opt/ghidra \
    && rm /tmp/ghidra.zip \
    && ln -s /opt/ghidra/support/analyzeHeadless /usr/local/bin/analyzeHeadless \
    && ln -s /opt/ghidra/ghidraRun /usr/local/bin/ghidraRun
ENV GHIDRA_INSTALL_DIR=/opt/ghidra

# --- user --------------------------------------------------------------------
# Match the host uid/gid so files written under /work stay owned by you.
# ubuntu:24.04 ships a uid-1000 "ubuntu" user; drop it to free the ids.
ARG UID=1000
ARG GID=1000
RUN userdel -r ubuntu 2>/dev/null || true \
    && groupadd -g ${GID} re \
    && useradd -m -u ${UID} -g ${GID} -s /bin/bash re

# --- ghidra-lx-loader (LE/LX: DOS/4GW, OS/2, VxD) ------------------------------
# Upstream's newest release targets 12.0.1; the jar loads unchanged on 12.0.4
# once extension.properties carries the running version (same patch as the
# Cyberia host install). Installed as a USER extension, which is where Ghidra
# headless picks it up.
ARG LXLOADER_TAG=v12.0.1
ARG LXLOADER_ZIP=ghidra_12.0.1_PUBLIC_20260129_ghidra-lx-loader.zip
ARG LXLOADER_SHA256=8b7e7461bd48621faa5e32c27a2c7ff8b17b82c7b765c8c6afe2cee8db693cec
USER re
RUN EXT=/home/re/.config/ghidra/ghidra_${GHIDRA_VERSION}_PUBLIC/Extensions \
    && mkdir -p "$EXT" \
    && curl -fsSL -o /tmp/lx.zip \
        "https://github.com/yetmorecode/ghidra-lx-loader/releases/download/${LXLOADER_TAG}/${LXLOADER_ZIP}" \
    && echo "${LXLOADER_SHA256}  /tmp/lx.zip" | sha256sum -c - \
    && unzip -q /tmp/lx.zip -d "$EXT" \
    && rm /tmp/lx.zip \
    && sed -i "s/^version=.*/version=${GHIDRA_VERSION}/" "$EXT/ghidra-lx-loader/extension.properties"
USER root

# --- toolbox scripts ---------------------------------------------------------
COPY tools/ /opt/rebox/tools/
COPY ghidra_scripts/ /opt/rebox/ghidra_scripts/
COPY dosdbg/ /opt/rebox/dosdbg/
# COPY keeps the host's file modes; a restrictive host umask would leave the
# scripts unreadable for the unprivileged user
RUN chmod -R a+rX /opt/rebox \
    && chmod a+x /opt/rebox/tools/* /opt/rebox/dosdbg/dosdbg /opt/rebox/dosdbg/dbgdrive.py \
    && ln -s /opt/rebox/dosdbg/dosdbg /usr/local/bin/dosdbg \
    && ln -s /opt/rebox/dosdbg/dbgdrive.py /usr/local/bin/dbgdrive
ENV PATH=/opt/rebox/tools:$PATH \
    REBOX_GHIDRA_SCRIPTS=/opt/rebox/ghidra_scripts \
    PYTHONPATH=/opt/rebox/dosdbg

USER re
WORKDIR /work
CMD ["/bin/bash"]
