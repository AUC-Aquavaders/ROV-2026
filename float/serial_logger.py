import argparse
import datetime as dt
import sys

import serial


def main() -> int:
    parser = argparse.ArgumentParser(description="Log station ESP32 serial CSV to a file.")
    parser.add_argument("--port", required=True, help="Serial port (e.g. COM5)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default 115200)")
    parser.add_argument(
        "--out",
        default="",
        help="Output filename. Default: auto timestamped .csv in current directory",
    )
    parser.add_argument(
        "--stop-on-done",
        action="store_true",
        help="Stop logging when a '#DONE,...' line is received",
    )
    parser.add_argument(
        "--include-status",
        action="store_true",
        help="Include '#READY/#DONE/#ERR' lines in output as comments",
    )
    args = parser.parse_args()

    out_path = args.out.strip()
    if not out_path:
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"float_log_{stamp}.csv"

    print(f"[logger] Opening {args.port} @ {args.baud}")
    print(f"[logger] Writing to {out_path}")

    # Open serial first so we fail fast if port is wrong.
    with serial.Serial(args.port, args.baud, timeout=1) as ser, open(out_path, "w", newline="") as f:
        # Header for the station CSV format we emit
        f.write("companyID,timestamp_s,profile,state,seq,pressure_kPa,depth_m\n")
        f.flush()

        while True:
            raw = ser.readline()
            if not raw:
                continue

            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue

            if not line:
                continue

            # Echo to console so you can see it's alive
            print(line)

            if line.startswith("#"):
                if args.include_status:
                    f.write(line + "\n")
                    f.flush()
                if args.stop_on_done and line.startswith("#DONE"):
                    print("[logger] DONE received; stopping.")
                    break
                continue

            # Data CSV line
            f.write(line + "\n")
            f.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

