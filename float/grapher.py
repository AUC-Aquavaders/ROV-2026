import matplotlib.pyplot as plt
import datetime
import argparse

# ASSUMPTIONS:
# depth is in meters not centimeters
# pressure is in kpa
# depth is inverted to look like the float's trajectory
# time is in actual time not seconds (1:51:42)
# file is .txt

# python grapher.py test_data.txt

# This file will be run on ground station computer
# Get data from receiver ESP into computer then run this grapher

def grapher(filename):
    DATA_FILE = filename
    USE_CLOCK_TIME = True         

    time_values = []
    depth_values = []

    with open(DATA_FILE, "r") as file:
        for line in file:
            parts = line.strip().split()

            if len(parts) < 6:
                continue  # Skip incomplete lines

            # Example packet:
            # EX01 00:00:05 9.8 kpa 0.40 m

            time_data = parts[1]
            depth = float(parts[4])

            #TODO: REVISIT TIME FORMATTING
            if USE_CLOCK_TIME:
                # Convert HH:MM:SS to seconds
                t = datetime.datetime.strptime(time_data, "%H:%M:%S")
                seconds = t.hour * 3600 + t.minute * 60 + t.second
                time_values.append(seconds)
            else:
                # Float time already in seconds
                time_values.append(float(time_data))

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
