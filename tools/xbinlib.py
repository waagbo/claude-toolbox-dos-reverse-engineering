"""Shared code for the xbin-* tools: load a flatdis listing and reduce each
instruction to its address-free SHAPE, so two builds of one program (or two
games on one engine) can be compared where their addresses differ, or where
the same address means different code.

Normalisation of each instruction text:
  * a hex literal >= ADDR_MIN            -> 'A'  (code addresses, branch targets)
  * the hex literal after "ds:"          -> 'D'  (data displacements; these move
                                                   between builds even when tiny)
  * everything else kept verbatim        (ports, shift counts, strides, magics,
                                          esp/ebp frame offsets = the fingerprint)

ADDR_MIN defaults to 0x8000, right for Watcom LE images linked at 0x10000.
For an image based at 0 (Phar Lap P3, raw blobs) lower it, or every small
code address survives as a literal and nothing matches.
Origin: re2/tools/xbin_*.py (Cyberia RE project).
"""
import bisect
import re

LINE = re.compile(r'^\s*([0-9a-f]+):\t([0-9a-f ]+)\t(.*)$')
DSHEX = re.compile(r'ds:0x[0-9a-f]+')
HEX = re.compile(r'0x([0-9a-f]+)')
CALL = re.compile(r'^call\s+0x([0-9a-f]+)$')


def norm(text, addr_min=0x8000):
    t = text.split('#')[0].strip()
    if t.startswith('(bad)'):
        return 'bad'
    t = DSHEX.sub('ds:D', t)
    return HEX.sub(lambda m: 'A' if int(m.group(1), 16) >= addr_min else m.group(0), t)


class Listing:
    """One flatdis listing: parallel arrays of address, shape and raw text."""

    def __init__(self, path, addr_min=0x8000):
        self.path = path
        rows = []
        self.calls = set()
        for ln in open(path, errors='replace'):
            m = LINE.match(ln.rstrip('\n'))
            if not m:
                continue          # header, blank, or a long insn's byte continuation
            a = int(m.group(1), 16)
            raw = m.group(3).split('#')[0].rstrip()
            rows.append((a, norm(raw, addr_min), raw))
            c = CALL.match(raw.strip())
            if c:
                self.calls.add(int(c.group(1), 16))
        rows.sort()
        self.addr = [r[0] for r in rows]
        self.shape = [r[1] for r in rows]
        self.raw = [r[2] for r in rows]

    def at(self, addr):
        """Index of the first instruction at or after addr."""
        return bisect.bisect_left(self.addr, addr)

    def span(self, lo, hi):
        return self.at(lo), self.at(hi)


def index_rows(path):
    """(addr, name, size) rows of a ghidra-dump _index.tsv, FAIL rows included.

    Rows whose address carries a space prefix (`.image::00016210`) are skipped:
    the LE loader leaves 1-byte placeholders there, and taking them as
    function starts would split real functions in two."""
    out = []
    for ln in open(path):
        p = ln.rstrip('\n').split('\t')
        if len(p) < 3 or not re.fullmatch(r'[0-9a-fA-F]{5,8}', p[0]):
            continue
        out.append((int(p[0], 16), p[1], int(p[2])))
    return sorted(out)


def functions(lst, index=None):
    """Split a listing into candidate functions.

    Starts = every direct `call` target that lands on an instruction, plus the
    Ghidra index starts if given; each function runs to the next start. Coverage
    therefore does not depend on Ghidra having found the function, but a body
    can over-run into a neighbour that is only reached indirectly -- variants()
    compensates."""
    starts = set(lst.calls)
    if index:
        starts |= {r[0] for r in index}
    have = set(lst.addr)
    starts = sorted(s for s in starts if s in have)
    funcs = {}
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else lst.addr[-1] + 1
        lo, hi = lst.span(s, e)
        funcs[s] = lst.shape[lo:hi]
    return funcs


def variants(toks):
    """The full body plus its prefix up to the first ret."""
    out = [toks]
    for i, x in enumerate(toks):
        if x == 'ret' or x.startswith('ret '):
            if i + 1 < len(toks):
                out.append(toks[:i + 1])
            break
    return out


def shingles(toks, n=4):
    return {tuple(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def hexarg(s):
    return int(s, 16)
