#!/usr/bin/env python3
"""
can_reverse_from_dump_debug.py

File-only CAN reverse workflow with rich debug logging.

Examples:
  python3 can_reverse_from_dump_debug.py --dump can0dump.txt --verbose
  python3 can_reverse_from_dump_debug.py --dump can0dump.txt --calib 8 --monitor 12 --verbose --id-summary
  python3 can_reverse_from_dump_debug.py --dump can0dump.txt --read 0x285 --bytes all --verbose
  python3 can_reverse_from_dump_debug.py --dump can0dump.txt --variance top --limit 50000 --verbose
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

MAX_CAN_DLC = 8

# ---------- Parsing ----------

candump_patterns = [
    re.compile(r"\((?P<ts>[\d\.]+)\)\s+can\d+\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)"),
    re.compile(r"(?:can\d+\s+)(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)"),
]

@dataclass
class Frame:
    ts: Optional[float]
    can_id: int
    dlc: int
    data: bytes

def parse_candump(path: str, limit: Optional[int], verbose: bool) -> List[Frame]:
    frames: List[Frame] = []
    bad_lines = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for lineno, raw in enumerate(f, start=1):
            if limit is not None and len(frames) >= limit:
                break
            line = raw.strip()
            if not line:
                continue
            m = None
            for pat in candump_patterns:
                m = pat.search(line)
                if m:
                    break
            if not m:
                bad_lines += 1
                if verbose and bad_lines <= 10:
                    print(f"[DBG] Unparsed line {lineno}: {line}")
                continue
            ts = float(m.group("ts")) if "ts" in m.groupdict() and m.group("ts") else None
            try:
                can_id = int(m.group("id"), 16)
                dlc = int(m.group("dlc"))
                data_bytes = bytes(int(b, 16) for b in m.group("data").split())[:dlc]
            except Exception as e:
                bad_lines += 1
                if verbose:
                    print(f"[DBG] Parse error line {lineno}: {e} :: {line}")
                continue
            frames.append(Frame(ts, can_id, dlc, data_bytes))

    if verbose:
        print(f"[INFO] Parsed frames: {len(frames)} (bad/unparsed lines: {bad_lines})")
        if frames:
            print(f"[INFO] First frame: ts={frames[0].ts} id=0x{frames[0].can_id:03X} dlc={frames[0].dlc} data={frames[0].data.hex(' ')}")
            print(f"[INFO] Last  frame: ts={frames[-1].ts} id=0x{frames[-1].can_id:03X} dlc={frames[-1].dlc} data={frames[-1].data.hex(' ')}")
    if not frames:
        print("[!] No frames parsed from file. Check format or use --verbose to inspect.", file=sys.stderr)
    return frames

# ---------- Reverse logic ----------

@dataclass
class ByteState:
    value: int = 0
    disqualified: bool = False

@dataclass
class IdState:
    can_id: int
    seen_len: int = 0
    fully_disqualified: bool = False
    bytes: List[ByteState] = field(default_factory=lambda: [ByteState() for _ in range(MAX_CAN_DLC)])

    def ingest_for_calibration(self, data: bytes):
        if not data:
            return
        self.seen_len = max(self.seen_len, len(data))
        for i, b in enumerate(data):
            bs = self.bytes[i]
            if bs.disqualified:
                continue
            if self.seen_len <= 1 and bs.value == 0:
                bs.value = b
            else:
                if b != bs.value:
                    bs.disqualified = True
        self.fully_disqualified = all(self.bytes[i].disqualified for i in range(self.seen_len))

    def diff_and_report(self, data: bytes) -> List[Tuple[int, int, int]]:
        out = []
        for i, b in enumerate(data):
            if i >= self.seen_len:
                break
            bs = self.bytes[i]
            if not bs.disqualified and b != bs.value:
                out.append((i, bs.value, b))
                bs.value = b
        return out

class ReverseTool:
    def __init__(self, verbose: bool = False):
        self.states: Dict[int, IdState] = {}
        self.verbose = verbose

    def _state(self, can_id: int) -> IdState:
        if can_id not in self.states:
            if self.verbose:
                print(f"[DBG] New ID observed: 0x{can_id:03X}")
            self.states[can_id] = IdState(can_id)
        return self.states[can_id]

    def calibrate(self, frames: Iterable[Frame], label: str = "calib"):
        print("--------- Calibration Start ----------")
        cnt = 0
        for fr in frames:
            self._state(fr.can_id).ingest_for_calibration(fr.data)
            cnt += 1
            if self.verbose and cnt % 5000 == 0:
                print(f"[DBG] {label}: processed {cnt} frames...")
        print(f"[INFO] Calibration processed frames: {cnt}")
        print("--------- Calibration Complete --------")
        printed = 0
        for cid in sorted(self.states.keys()):
            st = self.states[cid]
            if st.seen_len == 0 or st.fully_disqualified:
                continue
            row = []
            for i in range(st.seen_len):
                bs = st.bytes[i]
                row.append("XX" if bs.disqualified else f"{bs.value:02X}")
            print(f"{cid:03X} " + " ".join(row))
            printed += 1
        if self.verbose:
            print(f"[DBG] Calibration summary rows printed: {printed}")

    def monitor(self, frames: Iterable[Frame], label: str = "monitor"):
        print("--------- Monitoring Start -----------")
        cnt = 0
        changes_total = 0
        for fr in frames:
            st = self.states.get(fr.can_id)
            if not st or st.fully_disqualified or st.seen_len == 0:
                cnt += 1
                continue
            changes = st.diff_and_report(fr.data)
            if changes:
                for i, old, new in changes:
                    print(f"Change ID={fr.can_id:03X} Byte={i} Old={old:02X} New={new:02X}")
                    changes_total += 1
            cnt += 1
            if self.verbose and cnt % 5000 == 0:
                print(f"[DBG] {label}: processed {cnt} frames... changes so far={changes_total}")
        print(f"[INFO] Monitoring processed frames: {cnt}, changes printed: {changes_total}")
        print("--------- Monitoring Complete --------")

    def read_mode(self, frames: Iterable[Frame], filter_id: int, byte_idxs: Optional[List[int]]):
        print(f"------- Read Mode: ID 0x{filter_id:03X} -------")
        hits = 0
        all_bytes = byte_idxs is None
        for fr in frames:
            if fr.can_id != filter_id:
                continue
            hits += 1
            if all_bytes:
                idxs = list(range(fr.dlc))
                vals = [f"{b:02X}" for b in fr.data]
            else:
                idxs = byte_idxs
                vals = [f"{fr.data[i]:02X}" if i < fr.dlc else "--" for i in byte_idxs]
            ts = f"{fr.ts:.6f}" if fr.ts is not None else "-"
            print(f"t={ts}  {filter_id:03X}  bytes[{','.join(map(str, idxs)) if not all_bytes else 'all'}]: {' '.join(vals)}")
        if self.verbose:
            print(f"[DBG] Read-mode frames matched for 0x{filter_id:03X}: {hits}")

    def variance_report(self, frames: List[Frame], top_n: int = 15):
        from collections import defaultdict
        sums = defaultdict(lambda: [0]*MAX_CAN_DLC)
        sums2 = defaultdict(lambda: [0]*MAX_CAN_DLC)
        counts = defaultdict(int)
        for idx, fr in enumerate(frames):
            counts[fr.can_id] += 1
            for i in range(min(fr.dlc, MAX_CAN_DLC)):
                b = fr.data[i]
                sums[fr.can_id][i] += b
                sums2[fr.can_id][i] += b*b
            if self.verbose and (idx+1) % 10000 == 0:
                print(f"[DBG] variance: processed {idx+1} frames...")
        scores = []
        for cid, n in counts.items():
            if n < 2:
                continue
            score = 0.0
            for i in range(MAX_CAN_DLC):
                mean = sums[cid][i] / n
                var = max(0.0, (sums2[cid][i] / n) - (mean*mean))
                score += var
            scores.append((cid, score, n))
        scores.sort(key=lambda x: x[1], reverse=True)
        print(f"------ Variance Top {top_n} ------")
        for cid, sc, n in scores[:top_n]:
            print(f"{cid:03X}  var_sum={sc:.2f}  frames={n}")
        if self.verbose:
            print(f"[DBG] variance: IDs ranked = {len(scores)}")

    def id_summary(self, frames: List[Frame], top_n: int = 30):
        from collections import defaultdict, deque
        counts: Dict[int,int] = defaultdict(int)
        first: Dict[int,bytes] = {}
        last: Dict[int,bytes] = {}
        for idx, fr in enumerate(frames):
            counts[fr.can_id] += 1
            if fr.can_id not in first:
                first[fr.can_id] = fr.data
            last[fr.can_id] = fr.data
        items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        print("------ ID Summary (top by frame count) ------")
        for cid, n in items:
            fhex = first[cid].hex(' ')
            lhex = last[cid].hex(' ')
            print(f"{cid:03X}  frames={n:6d}  first={fhex}  last={lhex}")
        if self.verbose:
            print(f"[DBG] id_summary: unique IDs = {len(counts)}")

# ---------- Helpers ----------

def slice_by_time(frames: List[Frame], start: float, end: float) -> Iterable[Frame]:
    for fr in frames:
        if fr.ts is None:
            yield fr
        elif start <= fr.ts < end:
            yield fr

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Run CAN reverse workflow on a candump file (debug version)")
    ap.add_argument("--dump", required=True, help="Path to candump text file")
    ap.add_argument("--calib", type=float, default=0.0, help="Calibration seconds (0 = auto-split if timestamps)")
    ap.add_argument("--monitor", type=float, default=0.0, help="Monitoring seconds (0 = auto-split if timestamps)")
    ap.add_argument("--read", type=lambda x: int(x, 0), help="Read-mode CAN ID (e.g., 0x285)")
    ap.add_argument("--bytes", nargs="+", help="'all' or byte indices (e.g., 0 1 2 3)")
    ap.add_argument("--variance", choices=["top"], help="Print variance ranking")
    ap.add_argument("--id-summary", action="store_true", help="Print per-ID counts and first/last payloads")
    ap.add_argument("--limit", type=int, help="Limit number of frames parsed from file")
    ap.add_argument("--verbose", action="store_true", help="Verbose debug logging")
    args = ap.parse_args()

    frames = parse_candump(args.dump, limit=args.limit, verbose=args.verbose)
    if not frames:
        sys.exit(1)

    have_ts = frames[0].ts is not None and frames[-1].ts is not None
    t_min = frames[0].ts if have_ts else None
    t_max = frames[-1].ts if have_ts else None
    if args.verbose:
        print(f"[INFO] Timestamp present: {have_ts}; t_min={t_min}, t_max={t_max}")

    tool = ReverseTool(verbose=args.verbose)

    if args.id_summary:
        tool.id_summary(frames)

    if args.variance == "top":
        tool.variance_report(frames, top_n=15)

    # Decide calibration + monitoring windows
    if args.calib == 0.0 and args.monitor == 0.0 and have_ts and t_max > t_min:
        span = t_max - t_min
        c0, c1 = t_min, t_min + span/3.0
        m0, m1 = t_min + span/3.0, t_min + 2*span/3.0
        if args.verbose:
            print(f"[INFO] Auto-split windows: calib=({c0:.6f},{c1:.6f}) monitor=({m0:.6f},{m1:.6f})")
        tool.calibrate(slice_by_time(frames, c0, c1), label="calib_auto")
        tool.monitor(slice_by_time(frames, m0, m1), label="monitor_auto")
    else:
        # Without timestamps or with explicit seconds, just run through full list
        if args.calib > 0:
            if args.verbose:
                print(f"[INFO] Running calibration for ~{args.calib}s worth of frames (no hard stop without timestamps).")
            tool.calibrate(frames)
        if args.monitor > 0:
            if args.verbose:
                print(f"[INFO] Running monitoring for ~{args.monitor}s worth of frames (no hard stop without timestamps).")
            tool.monitor(frames)

    if args.read is not None:
        if args.bytes and len(args.bytes) == 1 and args.bytes[0].lower() == "all":
            byte_idxs = None
        elif args.bytes:
            byte_idxs = [int(b) for b in args.bytes]
        else:
            byte_idxs = None
        tool.read_mode(frames, args.read, byte_idxs)

if __name__ == "__main__":
    main()
