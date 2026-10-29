#!/usr/bin/env python3
"""dbgdrive -- drive the DOSBox-X ncurses debugger through tmux.

The debugger runs in a tmux session started by `dosdbg`. Commands are typed
with send-keys and the screen is read back with capture-pane. Import it from
a scenario script, or use the CLI:

    dbgdrive screen                    print the debugger screen
    dbgdrive regs                      parsed registers (+ link EIP)
    dbgdrive run [TIMEOUT]             F5, wait for the next break
    dbgdrive send 'BPINT 21 3D'        type one debugger command
    dbgdrive dump SEG OFF [N]          bytes at SEG:OFF (<= 112)
    dbgdrive calibrate SITE [DATA EXPECT]
                                       derive the code load delta (see below)

Link <-> runtime addresses. A DOS extender (DOS/4GW) does not load LE
objects at their link bases; each object lands at link + delta, flat
selectors, base 0. Set the deltas for this session with env vars (hex):

    DBG_CODE_DELTA  DBG_DATA_DELTA  DBG_CS (default 0x160)  DBG_DS (0x168)

and use rt_code()/rt_data()/link_code()/link_data(). The deltas move with
memsize and the DOSBox-X build. `calibrate SITE` re-derives the code delta:
it arms BPINT 21 3D, runs to the first 32-bit protected-mode break and
reports EIP - SITE, where SITE is the link address of the program's own
`int 0x21` instruction in its CRT open (`mov ah,0x3d` ... `int 0x21` in the
listing). The break reports EIP AT the int instruction. DATA/EXPECT
optionally check the data delta against a known string. Verified on
Cyberia 2: `calibrate 3356B 400D4 'c:\\cyberia2'` -> code 0x1c3000, data
0x1c1000 OK (memsize 32, DOSBox-X 2026.05.02 debug build).

Rules earned the hard way (Cyberia 2 c2trace):
  * Breakpoints are INT3 patches placed at set time: a `BP sel:off` typed
    while still in the real-mode stub lands in conventional memory and never
    fires. Arm BPINT 21 3D first, run to the first Pr32 break, THEN set BPs.
  * Nothing interrupts a running emulation -- the debugger polls keys only
    while stopped. Every "look now" must be a breakpoint armed beforehand.
  * Never queue a second F5: one typed while running is consumed at the
    next break and silently continues past it. run() only presses F5 when
    the prompt is showing.
  * Each DOS/4GW int 21h breaks twice (protected-mode + real-mode
    reflection); filter on regs()['mode'] == 'Pr32'.
  * BPLM memory watches check every instruction (slow); prefer BP at the
    known writer sites.
  * Input is poked (SM) into the game's keyboard-state cells at a
    breakpoint in its poll loop -- there is no window to type into.
"""
import os
import re
import subprocess
import sys
import time

SESSION = os.environ.get("DOSDBG_SESSION", "dosdbg")
CODE_DELTA = int(os.environ.get("DBG_CODE_DELTA", "0"), 16)
DATA_DELTA = int(os.environ.get("DBG_DATA_DELTA", "0"), 16)
CS_SEL = int(os.environ.get("DBG_CS", "160"), 16)
DS_SEL = int(os.environ.get("DBG_DS", "168"), 16)


def tmux(*args):
    return subprocess.run(["tmux", *args], capture_output=True, text=True).stdout


def screen():
    return tmux("capture-pane", "-p", "-t", SESSION)


def send(cmd):
    """Type one debugger command line."""
    tmux("send-keys", "-t", SESSION, cmd, "Enter")


def key(k):
    """Press one key (tmux key name: F5, F10, Enter, ...)."""
    tmux("send-keys", "-t", SESSION, k)


def stopped():
    lines = [l for l in screen().splitlines() if l.strip()]
    return bool(lines) and lines[-1].startswith("I->")


def run(timeout=30.0, poll=0.25):
    """F5 (only if stopped), then wait until the prompt shows again.
    Returns False on timeout (the program is still running)."""
    if stopped():
        key("F5")
        time.sleep(0.3)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if stopped():
            return True
        time.sleep(poll)
    return False


def regs():
    s = screen()
    r = {}
    for m in re.finditer(r"\b(E[A-D]X|ESI|EDI|EBP|ESP|EIP)=([0-9A-F]{8})", s):
        r[m.group(1)] = int(m.group(2), 16)
    for m in re.finditer(r"\b(CS|DS|ES|SS|FS|GS)=([0-9A-F]{4})", s):
        r[m.group(1)] = int(m.group(2), 16)
    m = re.search(r"SS=[0-9A-F]{4}\s+(Real|Pr16|Pr32|V86)", s)
    r["mode"] = m.group(1) if m else "?"
    r["link_eip"] = r.get("EIP", 0) - CODE_DELTA
    return r


def dump(seg, off, n=16):
    """Bytes at seg:off via the D command. The data view shows 7 lines
    (112 bytes); asking for more returns a short read."""
    send("D %04X:%08X" % (seg, off))
    time.sleep(0.4)
    out = b""
    for line in screen().splitlines():
        m = re.match(r"%04X:([0-9A-F]{8}) ((?:[0-9A-F]{2} ){16})" % seg, line)
        if m and int(m.group(1), 16) >= off:
            out += bytes.fromhex(m.group(2).replace(" ", ""))
    return out[:n]


def cstr(seg, off, n=64):
    return dump(seg, off, n).split(b"\0", 1)[0].decode("latin-1", "replace")


def rt_code(link): return link + CODE_DELTA
def rt_data(link): return link + DATA_DELTA
def link_code(rt): return rt - CODE_DELTA
def link_data(rt): return rt - DATA_DELTA


def bp_code(link):
    send("BP %04X:%08X" % (CS_SEL, rt_code(link)))


def bplm_data(link):
    send("BPLM %08X" % rt_data(link))


def poke(link_data_addr, *values):
    """SM: set bytes at a data link address (input injection)."""
    send("SM %04X:%08X %s" % (DS_SEL, rt_data(link_data_addr),
                              " ".join("%02X" % v for v in values)))


def calibrate(site, data_link=None, expect=None, tries=40):
    send("BPINT 21 3D")
    time.sleep(0.3)
    for _ in range(tries):
        if not run(30):
            print("timeout waiting for a break")
            return None
        r = regs()
        if r["mode"] != "Pr32":
            continue
        cd = r["EIP"] - site
        print("CODE_DELTA = 0x%x  (EIP 0x%x, CS=%04X DS=%04X)"
              % (cd, r["EIP"], r.get("CS", 0), r.get("DS", 0)))
        print("filename at DS:EDX: %r" % cstr(r["DS"], r["EDX"], 48))
        if data_link is not None:
            s = cstr(r["DS"], data_link + DATA_DELTA, 32)
            print("DATA_DELTA 0x%x check at link 0x%x: %r%s"
                  % (DATA_DELTA, data_link, s,
                     "" if expect is None else
                     ("  OK" if s.startswith(expect) else "  MISMATCH")))
        return cd
    print("no Pr32 open seen")
    return None


def _fmt(r):
    return {k: (hex(v) if isinstance(v, int) else v) for k, v in r.items()}


def main(argv):
    if not argv or argv[0] == "screen":
        print(screen())
    elif argv[0] == "regs":
        print(_fmt(regs()))
    elif argv[0] == "run":
        ok = run(float(argv[1]) if len(argv) > 1 else 30.0)
        print("stopped" if ok else "TIMEOUT", _fmt(regs()))
    elif argv[0] == "send":
        send(" ".join(argv[1:]))
        time.sleep(0.4)
        print("\n".join([l for l in screen().splitlines() if l.strip()][-6:]))
    elif argv[0] == "dump":
        n = int(argv[3]) if len(argv) > 3 else 16
        print(dump(int(argv[1], 16), int(argv[2], 16), n).hex(" "))
    elif argv[0] == "calibrate":
        calibrate(int(argv[1], 16),
                  int(argv[2], 16) if len(argv) > 2 else None,
                  argv[3] if len(argv) > 3 else None)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
