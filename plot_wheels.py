#!/usr/bin/env python3
"""
Wheel-speed plotter with ESP intervention overlay.

Supports:
  - Infiniti G37 (Nissan): 0x284 (front), 0x285 (rear), 0.005 kph/bit
  - Mercedes C/E (CAN-C):
      * 'counters' (default): 0x201 has 4x 8-bit wheel counters (FL,FR,RL,RR).
        We compute speed = Δticks / Δt using candump timestamps (wrap-aware).
        Optional direction from 0x200 bits.
      * 'dbc11': 0x203-style 11-bit fields via DBC (0.0375 mph/bit).

ESP overlay:
  Uses 0x200 flags (defaults: BL bit=2, DL bit=3). You can change via CLI.
  Optional brake pressure overlay (ID, byte index, scale, threshold).

Examples
--------
# Recommended capture WITH timestamps:
candump -tz can0,0:0,#FFFFFFFF > merc_ts.log

# Mercedes, counters on 0x201, mark ESP from 0x200:
python3 plot_wheels.py --car mercedes --dump merc_ts.log \
  --mercedes-id 0x201 --mercedes-format counters --units mph \
  --scale 0.10 --esp-id 0x200 --esp-bl-bit 2 --esp-dl-bit 3 --median 5

# Use DBC 11-bit layout (0x203):
python3 plot_wheels.py --car mercedes --dump merc_ts.log \
  --mercedes-id 0x203 --mercedes-format dbc11 --units mph

# G37
python3 plot_wheels.py --car g37 --dump g37_ts.log --units kph
"""

import re, sys, struct, argparse, math
import matplotlib.pyplot as plt

# ---------- candump parsing ----------
PAT_TS = re.compile(
    r"\((?P<ts>[\d\.]+)\)\s+can\d+\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)"
)
PAT_NO_TS = re.compile(
    r"(?:can\d+\s+)?(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)"
)

def parse_dump(path):
    frames = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            m = PAT_TS.search(line) or PAT_NO_TS.search(line)
            if not m:
                continue
            cid = int(m.group("id"), 16)
            dlc = int(m.group("dlc"))
            data = bytes(int(b, 16) for b in m.group("data").split())[:dlc]
            ts = float(m.group("ts")) if "ts" in m.groupdict() and m.group("ts") else None
            frames.append((ts, cid, data))
    # If timestamps exist, sort by them
    if frames and frames[0][0] is not None:
        frames.sort(key=lambda t: t[0])
    return frames

# ---------- G37 decoder ----------
G37_SCALE_KPH = 0.005
def decode_g37(frames):
    x, fl, fr, rl, rr, ts_out = [], [], [], [], [], []
    for idx, (ts, cid, data) in enumerate(frames):
        if cid == 0x284 and len(data) >= 4:  # fronts
            w1 = struct.unpack(">H", data[0:2])[0] * G37_SCALE_KPH  # FR
            w2 = struct.unpack(">H", data[2:4])[0] * G37_SCALE_KPH  # FL
            fr.append(w1); fl.append(w2); rr.append(None); rl.append(None)
            ts_out.append(ts if ts is not None else idx); x.append(idx)
        elif cid == 0x285 and len(data) >= 4:  # rears
            w1 = struct.unpack(">H", data[0:2])[0] * G37_SCALE_KPH  # RR
            w2 = struct.unpack(">H", data[2:4])[0] * G37_SCALE_KPH  # RL
            rr.append(w1); rl.append(w2); fr.append(None); fl.append(None)
            ts_out.append(ts if ts is not None else idx); x.append(idx)
    return ts_out, fl, fr, rl, rr, "kph"

# ---------- Mercedes decoders ----------
MERCEDES_WHEEL_DBC = r"""
VERSION ""
NS_ :
BS_:
BU_: XXX
BO_ 515 WHEEL_SPEEDS: 8 XXX
 SG_ WHEEL_MOVING_FR : 22|1@1+ (1,0) [0|1] "" XXX
 SG_ WHEEL_MOVING_RL : 38|1@0+ (1,0) [0|1] "" XXX
 SG_ WHEEL_MOVING_FL : 6|1@0+ (1,0) [0|1] "" XXX
 SG_ WHEEL_MOVING_RR : 54|1@0+ (1,0) [0|1] "" XXX
 SG_ WHEEL_SPEED_FL : 2|11@0+ (0.0375,0) [0|255] "mph" XXX
 SG_ WHEEL_SPEED_FR : 18|11@0+ (0.0375,0) [0|255] "mph" XXX
 SG_ WHEEL_SPEED_RL : 34|11@0+ (0.0375,0) [0|255] "mph" XXX
 SG_ WHEEL_SPEED_RR : 50|11@0+ (0.0375,0) [0|255] "mph" XXX
"""

def diff_u8_wrap(prev, cur):
    return (cur - prev) % 256

def decode_mercedes(frames, dbc_path=None, wheel_id=0x201, fmt="counters",
                    scale=None, dir_id=0x200, esp_id=0x200,
                    esp_bl_bit=2, esp_dl_bit=3):
    """
    fmt:
      - 'dbc11'  : use DBC (515/0x203 layout)
      - 'bytes'  : interpret 0x201 as raw byte values (FL,FR,RL,RR)
      - 'counters': interpret 0x201 as 8-bit counters -> Δticks/Δt
    Returns: (t_list, fl, fr, rl, rr, units, esp_spans, brake_series)
      esp_spans: list of (t_start, t_end) where ESP flag true
    """
    # Pre-extract frames of interest
    wheel_samples = []   # (ts, data)
    esp_samples = []     # (ts, data) for esp flags/brake overlay
    for ts, cid, data in frames:
        if cid == wheel_id and len(data) >= 4:
            wheel_samples.append((ts, data))
        if cid == esp_id and len(data) > 0:
            esp_samples.append((ts, data))

    # --- ESP overlay detection (simple OR of two bits) ---
    def get_bit(b, bit_index):
        if bit_index < 0: return 0
        byte = bit_index // 8
        shift = 7 - (bit_index % 8)
        if byte >= len(b): return 0
        return (b[byte] >> shift) & 0x1

    esp_ts = []
    esp_on = []
    for ts, b in esp_samples:
        bl = get_bit(b, esp_bl_bit)
        dl = get_bit(b, esp_dl_bit)
        esp_ts.append(ts if ts is not None else math.nan)
        esp_on.append(1 if (bl or dl) else 0)

    # Convert discrete on/off to spans (t_start, t_end)
    esp_spans = []
    if esp_ts and all(t is not None for t in esp_ts):
        cur_on = 0
        t0 = None
        for i in range(len(esp_ts)):
            if esp_on[i] and not cur_on:
                t0 = esp_ts[i]; cur_on = 1
            elif (not esp_on[i]) and cur_on:
                esp_spans.append((t0, esp_ts[i])); cur_on = 0
        if cur_on:
            esp_spans.append((t0, esp_ts[-1]))

    # --- Decode wheels ---
    if fmt == "dbc11":
        import cantools
        if dbc_path:
            db = cantools.database.load_file(dbc_path)
        else:
            db = cantools.database.load_string(MERCEDES_WHEEL_DBC, database_format='dbc')
        try:
            msg = db.get_message_by_name("WHEEL_SPEEDS")
        except KeyError:
            msg = db.get_message_by_frame_id(515)

        t, fl, fr, rl, rr = [], [], [], [], []
        for ts, data in wheel_samples:
            try:
                d = msg.decode(data)
            except Exception:
                continue
            t.append(ts)
            fl.append(float(d.get("WHEEL_SPEED_FL", 0.0)))
            fr.append(float(d.get("WHEEL_SPEED_FR", 0.0)))
            rl.append(float(d.get("WHEEL_SPEED_RL", 0.0)))
            rr.append(float(d.get("WHEEL_SPEED_RR", 0.0)))
        return t, fl, fr, rl, rr, "mph", esp_spans, None

    if fmt == "bytes":
        t, fl, fr, rl, rr = [], [], [], [], []
        for ts, data in wheel_samples:
            b0, b1, b2, b3 = data[0], data[1], data[2], data[3]
            if scale is None:
                fl_v, fr_v, rl_v, rr_v = float(b0), float(b1), float(b2), float(b3)
                units = "raw"
            else:
                fl_v, fr_v, rl_v, rr_v = b0scale, b1scale, b2scale, b3scale
                units = "mph"
            t.append(ts)
            fl.append(fl_v); fr.append(fr_v); rl.append(rl_v); rr.append(rr_v)
        return t, fl, fr, rl, rr, units, esp_spans, None

    # fmt == "counters": turn byte counters into speed via Δticks/Δt
    t, c0, c1, c2, c3 = [], [], [], [], []
    for ts, data in wheel_samples:
        t.append(ts)
        c0.append(data[0]); c1.append(data[1]); c2.append(data[2]); c3.append(data[3])

    def diff_per_sec(ts_list, vals):
        out = [0.0]
        for i in range(1, len(vals)):
            prev, cur = vals[i-1], vals[i]
            dt = None if (ts_list[i] is None or ts_list[i-1] is None) else (ts_list[i] - ts_list[i-1])
            if not dt or dt <= 0:
                out.append(0.0); continue
            dv = diff_u8_wrap(prev, cur)
            out.append(dv / dt)
        return out

    d0 = diff_per_sec(t, c0)
    d1 = diff_per_sec(t, c1)
    d2 = diff_per_sec(t, c2)
    d3 = diff_per_sec(t, c3)

    if scale is None:
        units = "ticks/s"
        fl, fr, rl, rr = d0, d1, d2, d3
    else:
        units = "mph"
        fl = [vscale for v in d0]; fr = [vscale for v in d1]
        rl = [vscale for v in d2]; rr = [vscale for v in d3]

    return t, fl, fr, rl, rr, units, esp_spans, None

# ---------- utils ----------
def convert_units(values, src, dst):
    if src == dst: return values
    f = 1.0
    if src == "mph" and dst == "kph": f = 1.609344
    elif src == "kph" and dst == "mph": f = 0.621371
    return [None if v is None else v * f for v in values]

def median_filter(vals, k=1):
    if k <= 1 or k % 2 == 0: return vals
    from collections import deque
    import bisect
    win, out, dq = [], [], deque()
    mid = k // 2
    for v in vals:
        x = 0.0 if v is None else v
        bisect.insort(win, x); dq.append(x)
        if len(win) > k:
            old = dq.popleft()
            win.pop(bisect.bisect_left(win, old))
        out.append(win[mid] if len(win) == k else x)
    return out

def carry(vals):
    out, last = [], None
    for v in vals:
        if v is None:
            out.append(last if last is not None else 0.0)
        else:
            last = v; out.append(v)
    return out

# ---------- plotting ----------
def plot_four(t, fl, fr, rl, rr, units, esp_spans=None, title="Wheel Speeds"):
    fl = carry(fl); fr = carry(fr); rl = carry(rl); rr = carry(rr)

    fig, ax = plt.subplots(figsize=(12,6))
    ax.plot(t, fl, label="Front Left")
    ax.plot(t, fr, label="Front Right")
    ax.plot(t, rl, label="Rear Left")
    ax.plot(t, rr, label="Rear Right")
    ax.set_title(title)
    ax.set_xlabel("Time (s)" if t and t[0] is not None else "Frame index")
    ax.set_ylabel(f"Speed ({units})")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()

    # ESP overlay shading
    if esp_spans:
        ymin, ymax = ax.get_ylim()
        for (t0, t1) in esp_spans:
            ax.axvspan(t0, t1, color="red", alpha=0.12)

    plt.tight_layout()
    plt.show()

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Plot four wheel speeds from a candump log with ESP overlay")
    ap.add_argument("--car", required=True, choices=["g37","mercedes"], help="Decoder to use")
    ap.add_argument("--dump", required=True, help="candump text file (use -tz for timestamps)")
    ap.add_argument("--units", choices=["kph","mph","raw","ticks/s"], default="kph", help="Y-axis units")
    # Mercedes options
    ap.add_argument("--dbc", help="(Mercedes only) DBC path (for --mercedes-format dbc11)")
    ap.add_argument("--mercedes-id", type=lambda s: int(s, 0), default=0x201,
                    help="Wheel frame ID (default 0x201)")
    ap.add_argument("--mercedes-format", choices=["dbc11","bytes","counters"], default="counters",
                    help="Mercedes decode mode")
    ap.add_argument("--scale", type=float, default=None,
                    help="Scale factor (mph per (tick/sec) in 'counters', mph per byte in 'bytes')")
    # ESP overlay controls
    ap.add_argument("--esp-id", type=lambda s: int(s, 0), default=0x200,
                    help="ESP status frame ID for overlay (default 0x200)")
    ap.add_argument("--esp-bl-bit", type=int, default=2,
                    help="Bit index for ESP_INFO_BL (flashing) in --esp-id (default 2)")
    ap.add_argument("--esp-dl-bit", type=int, default=3,
                    help="Bit index for ESP_INFO_DL (steady)   in --esp-id (default 3)")
    # smoothing
    ap.add_argument("--median", type=int, default=1, help="Median window (odd int), e.g., 5")
    args = ap.parse_args()

    frames = parse_dump(args.dump)
    if not frames:
        print("No frames parsed. Check file and candump format."); sys.exit(1)

    if args.car == "g37":
        t, fl, fr, rl, rr, src_units = decode_g37(frames)
        esp_spans = None
    else:
        t, fl, fr, rl, rr, src_units, esp_spans, _ = decode_mercedes(
            frames,
            dbc_path=args.dbc,
            wheel_id=args.mercedes_id,
            fmt=args.mercedes_format,
            scale=args.scale,
            esp_id=args.esp_id,
            esp_bl_bit=args.esp_bl_bit,
            esp_dl_bit=args.esp_dl_bit,
        )

    # smoothing
    if args.median and args.median > 1:
        fl = median_filter(fl, args.median)
        fr = median_filter(fr, args.median)
        rl = median_filter(rl, args.median)
        rr = median_filter(rr, args.median)

    # unit conversion
    fl = convert_units(fl, src_units, args.units)
    fr = convert_units(fr, src_units, args.units)
    rl = convert_units(rl, src_units, args.units)
    rr = convert_units(rr, src_units, args.units)

    plot_four(t, fl, fr, rl, rr, args.units, esp_spans=esp_spans,
              title="Wheel Speeds (ESP shaded)")

if __name__ == "__main__":
    main()
