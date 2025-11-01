#!/usr/bin/env python3
"""
Universal UDS wheel-speed reader
Works with multiple vehicles via CONFIG at top.
Tested with CANable/CANtact style USB-CAN adapters.
"""

import time, struct
from typing import List, Tuple, Optional
import can, isotp
from udsoncan.client import Client
from udsoncan import configs, Response
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.services import DiagnosticSessionControl
from udsoncan.exceptions import NegativeResponseException, TimeoutException
import contextlib



# ===========================================================
# CONFIG SECTION
# ===========================================================
VEHICLE_CONFIGS = {
    "mercedes_e400_2016": {
        "iface": "can0",
        "baud": 500000,
        "abs_candidates": [
            (0x760, 0x768),  # most common ESP/ABS pair
            (0x764, 0x76C),
            (0x768, 0x770),
        ],
        # placeholder DIDs to probe (real ID must be discovered/sniffed)
        "dids": [0xF40D, 0xF40C, 0xF401, 0xFD00],
        "comment": "UDS over CAN (ISO-TP) via ABS/ESP module"
    },

    "infiniti_g37_2008": {
        "iface": "can0",
        "baud": 500000,
        "abs_candidates": [
            (0x760, 0x768),
            (0x751, 0x759),  # Nissan/Infiniti ABS address range
        ],
        "dids": [0xA000, 0x22A0, 0x22A1, 0x22B0],  # example Mode22 IDs used on older Nissan ECUs
        "comment": "Uses ISO-TP or legacy Nissan Consult-III-style Mode22 requests"
    },
}

# Choose which vehicle to talk to:
vehicle_key = "mercedes_e400_2016"
vehicle_key = "infiniti_g37_2008"
CFG = VEHICLE_CONFIGS[vehicle_key]
print(f"[+] Loaded config for {vehicle_key}: {CFG['comment']}")

# ===========================================================
# Helper Functions (same as before)
# ===========================================================

import can
import isotp
from udsoncan.client import Client
from udsoncan import configs
from udsoncan.connections import PythonIsoTpConnection

def open_uds_client(txid: int, rxid: int):
    """
    Returns (client, bus).
    Caller must:
        client, bus = open_uds_client(...)
        with client:
            ...
        bus.shutdown()
    """
    # Create python-can bus (SocketCAN)
    bus = can.interface.Bus(interface="socketcan", channel=CFG["iface"], receive_own_messages=False)

    # ISO-TP 11-bit normal addressing
    addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=txid, rxid=rxid)

    # ✅ Version-agnostic: don't pass Params/dict; rely on safe defaults
    stack = isotp.CanStack(bus=bus, address=addr)

    # Wrap in UDS connection
    conn = PythonIsoTpConnection(stack)
    cfg = dict(configs.default_client_config)
    cfg["request_timeout"] = 1.0
    cfg["use_server_timing"] = True

    client = Client(conn, request_timeout=1.0, config=cfg)
    return client, bus



def find_abs_ecu():
    for tx, rx in CFG["abs_candidates"]:
        client = None
        bus = None
        try:
            client, bus = open_uds_client(tx, rx)
            with client:
                client.change_session(DiagnosticSessionControl.Session.defaultSession)
                client.tester_present()
                print(f"[+] ABS ECU responded on TX=0x{tx:03X}, RX=0x{rx:03X}")
                return (tx, rx)
        except (NegativeResponseException, TimeoutException):
            print(f"[-] TX=0x{tx:03X}, RX=0x{rx:03X} no response")
        except Exception as e:
            print(f"[-] TX=0x{tx:03X}, RX=0x{rx:03X} error: {e}")
        finally:
            if client is not None:
                # the context manager already closed the UDS connection
                pass
            if bus is not None:
                try:
                    bus.shutdown()
                except Exception:
                    pass
    return None



def probe_wheelspeed_dids(tx, rx, dids):
    found = []
    client, bus = open_uds_client(tx, rx)
    try:
        with client:
            client.change_session(DiagnosticSessionControl.Session.defaultSession)
            for did in dids:
                try:
                    resp = client.read_data_by_identifier(did)
                    data = bytes(resp.service_data.values[did])
                    print(f"[+] DID 0x{did:04X}: {data.hex(' ')} (len={len(data)})")
                    found.append(did)
                except (NegativeResponseException, TimeoutException):
                    print(f"[ ] DID 0x{did:04X}: no response")
    finally:
        bus.shutdown()
    return found


def decode_four_wheels(payload: bytes):
    if len(payload) >= 8:
        fl, fr, rl, rr = struct.unpack(">HHHH", payload[:8])
        scale = 0.01
        return (fl*scale, fr*scale, rl*scale, rr*scale)
    return None

def poll_wheelspeeds(tx: int, rx: int, did: int, hz: float = 10):
    period = 1.0 / hz
    with open_uds_client(tx, rx) as c:
        c.open()
        c.change_session(DiagnosticSessionControl.Session.defaultSession)
        print(f"[+] Polling DID 0x{did:04X} ({vehicle_key}) at {hz:.1f} Hz")
        while True:
            t0 = time.time()
            try:
                resp: Response = c.read_data_by_identifier(did)
                data = bytes(resp.service_data.values[did])
                decoded = decode_four_wheels(data)
                if decoded:
                    fl, fr, rl, rr = decoded
                    print(f"FL={fl:.2f} FR={fr:.2f} RL={rl:.2f} RR={rr:.2f}")
                else:
                    print(f"raw={data.hex(' ')}")
            except Exception as e:
                print(f"(poll) error: {e}")
            dt = time.time() - t0
            if dt < period:
                time.sleep(period - dt)

# ===========================================================
# Main
# ===========================================================
if __name__ == "__main__":
    pair = find_abs_ecu()
    if not pair:
        print("[-] No ABS ECU found. Try editing abs_candidates.")
        exit(1)

    txid, rxid = pair
    positives = probe_wheelspeed_dids(txid, rxid, CFG["dids"])

    if positives:
        poll_wheelspeeds(txid, rxid, positives[0])
    else:
        print("[-] No wheel-speed DIDs responded. Next step: sniff a commercial scanner session.")
