#!/usr/bin/env python3
"""
Plot all four wheel speeds from a candump log for:
  - Infiniti G37 (Nissan): IDs 0x284 (front), 0x285 (rear), 0.005 kph/bit
  - Mercedes E-class (C207/E350/E400): ID 0x203, 11-bit BE fields @0, 0.0375 mph/bit

Usage:
  python3 plot_wheels.py --car g37 --dump can0dump.txt --units kph
  python3 plot_wheels.py --car mercedes --dump can0dump.txt --units mph

  # If you want to use your own DBC for Mercedes:
  python3 plot_wheels.py --car mercedes --dump can0dump.txt --dbc /path/to/your.dbc

Requires:
  pip install cantools matplotlib
"""

import re, sys, struct, argparse
import matplotlib.pyplot as plt

# ---------------- candump parsing ----------------
PAT_TS = re.compile(r"\((?P<ts>[\d\.]+)\)\s+can\d+\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)")
PAT_NO_TS = re.compile(r"(?:can\d+\s+)?(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)")

def parse_dump(path):
    frames = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
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
    return frames

# ---------------- G37 decoder ----------------
G37_SCALE_KPH = 0.005
def decode_g37(frames):
    x, fl, fr, rl, rr = [], [], [], [], []
    for idx, (ts, cid, data) in enumerate(frames):
        if cid == 0x284 and len(data) >= 4:  # fronts
            w1 = struct.unpack(">H", data[0:2])[0] * G37_SCALE_KPH  # FR (heuristic)
            w2 = struct.unpack(">H", data[2:4])[0] * G37_SCALE_KPH  # FL
            fr.append(w1); fl.append(w2)
            rr.append(None); rl.append(None)
            x.append(idx)
        elif cid == 0x285 and len(data) >= 4:  # rears
            w1 = struct.unpack(">H", data[0:2])[0] * G37_SCALE_KPH  # RR
            w2 = struct.unpack(">H", data[2:4])[0] * G37_SCALE_KPH  # RL
            rr.append(w1); rl.append(w2)
            fr.append(None); fl.append(None)
            x.append(idx)
    return x, fl, fr, rl, rr, "kph"

# ---------------- Mercedes decoder (cantools) ----------------
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

def decode_mercedes(frames, dbc_path=None):
    import cantools
    if dbc_path:
        db = cantools.database.load_file(dbc_path)
    else:
        db = cantools.database.load_string(MERCEDES_WHEEL_DBC, database_format='dbc')

    x, fl, fr, rl, rr = [], [], [], [], []
    for idx, (ts, cid, data) in enumerate(frames):
        if cid == 0x203 and len(data) > 0:  # 515 dec = 0x203
            try:
                d = db.decode_message(515, data)
            except Exception:
                continue
            # Values are mph per DBC; keep mph here and convert later if needed
            fl.append(d.get("WHEEL_SPEED_FL", 0.0))
            fr.append(d.get("WHEEL_SPEED_FR", 0.0))
            rl.append(d.get("WHEEL_SPEED_RL", 0.0))
            rr.append(d.get("WHEEL_SPEED_RR", 0.0))
            x.append(idx)
    return x, fl, fr, rl, rr, "mph"

# ---------------- plotting ----------------
def convert_units(values, src, dst):
    if src == dst:
        return values
    out = []
    if src == "mph" and dst == "kph":
        f = 1.609344
    elif src == "kph" and dst == "mph":
        f = 0.621371
    else:
        f = 1.0
    for v in values:
        out.append(None if v is None else v * f)
    return out

def plot_four(x, fl, fr, rl, rr, units):
    # Clean (drop None by carrying last valid value forward for smoother line)
    def carry(vals):
        out, last = [], None
        for v in vals:
            if v is None:
                out.append(last if last is not None else 0.0)
            else:
                last = v
                out.append(v)
        return out

    fl = carry(fl); fr = carry(fr); rl = carry(rl); rr = carry(rr)

    plt.figure(figsize=(12,6))
    plt.plot(x, fl, label="Front Left")
    plt.plot(x, fr, label="Front Right")
    plt.plot(x, rl, label="Rear Left")
    plt.plot(x, rr, label="Rear Right")
    plt.title("Wheel Speeds (x = frame index)")
    plt.xlabel("Frame index")
    plt.ylabel(f"Speed ({units})")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.show()

def main():
    ap = argparse.ArgumentParser(description="Plot four wheel speeds from a candump log")
    ap.add_argument("--car", required=True, choices=["g37","mercedes"], help="Which decoder to use")
    ap.add_argument("--dump", required=True, help="candump text file")
    ap.add_argument("--dbc", help="(Mercedes only) path to DBC file (optional)")
    ap.add_argument("--units", choices=["kph","mph"], default="kph", help="Output units on plot")
    args = ap.parse_args()

    frames = parse_dump(args.dump)
    if not frames:
        print("No frames parsed. Check file format.")
        sys.exit(1)

    if args.car == "g37":
        x, fl, fr, rl, rr, src_units = decode_g37(frames)
    else:
        x, fl, fr, rl, rr, src_units = decode_mercedes(frames, dbc_path=args.dbc)

    # convert units if needed
    fl = convert_units(fl, src_units, args.units)
    fr = convert_units(fr, src_units, args.units)
    rl = convert_units(rl, src_units, args.units)
    rr = convert_units(rr, src_units, args.units)

    plot_four(x, fl, fr, rl, rr, args.units)

if __name__ == "__main__":
    main()
