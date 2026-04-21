import matplotlib.pyplot as plt
import argparse
import csv

# ASSUMPTIONS:
# depth is in meters not centimeters
# pressure is in kpa
# depth is inverted to look like the float's trajectory
# file is .txt

# python grapher.py test_data.txt

# This file will be run on ground station computer
# Get data from receiver ESP into computer then run this grapher

def grapher(filename):
    DATA_FILE = filename

    time_values = []
    depth_values = []

    # Station output format (CSV, one DATA packet per line):
    # companyID,timestamp_s,profile,state,seq,pressure_kPa,depth_m
    #
    # Lines starting with '#' are status (READY/DONE/etc) and are ignored.
    with open(DATA_FILE, "r", newline="") as file:
        for raw in file:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Be tolerant of accidental whitespace logs: try CSV first.
            if "," in line:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 7:
                    continue
                try:
                    t_s = float(parts[1])
                    depth = float(parts[6])
                except ValueError:
                    continue
            else:
                # Legacy fallback: "PN01 00:00:05 9.8 kPa 0.40 meters"
                parts = line.split()
                if len(parts) < 6:
                    continue
                try:
                    # If time is HH:MM:SS, convert to seconds
                    hh, mm, ss = parts[1].split(":")
                    t_s = int(hh) * 3600 + int(mm) * 60 + int(ss)
                    depth = float(parts[4])
                except Exception:
                    continue

            time_values.append(t_s)
            depth_values.append(depth)

    plt.figure()

    plt.plot(time_values, depth_values)
    plt.xlabel("Time (seconds)")
    plt.ylabel("Depth (meters)")
    plt.title("Float Profile: Depth vs Time")

    # Invert y-axis so deeper depth appears lower
    plt.gca().invert_yaxis()

    plt.grid(True)
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Graph data received from float")

    parser.add_argument("data_file", type=str, help="Path to data text file")

    args = parser.parse_args()

    grapher(args.data_file)


if __name__ == "__main__":
    main()
