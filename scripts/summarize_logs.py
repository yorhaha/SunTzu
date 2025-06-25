import glob
import os
import shutil

from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument("--delete_unfinished", action="store_true", help="Delete unfinished folders")
parser.add_argument("--delete_failed", action="store_true", help="Delete failed folders")
args = parser.parse_args()

folders = glob.glob(r"logs\sc2agent-2\*\*\*")

res = {}

for folder in folders:
    keys = folder.split("\\")
    folder_key = f"{keys[-3]}_{keys[-2]}"
    if folder_key not in res:
        res[folder_key] = [0, 0]  # win count, loss count

    if not os.path.isfile(folder + "/replay.SC2Replay") or not os.path.isfile(folder + "/trace.json"):
        if args.delete_unfinished:
            print(f"Deleting unfinished folder: {folder}")
            shutil.rmtree(folder)
        continue
    trace_file = os.path.join(folder, "trace.json")
    with open(trace_file, "r", encoding="utf-8") as f:
        trace_data = f.read()
    if "Victory" in trace_data:
        res[folder_key][0] += 1
    else:
        res[folder_key][1] += 1
        if args.delete_failed:
            print(f"Deleting failed folder: {folder}")
            shutil.rmtree(folder)

for key, value in res.items():
    print(f"{key}: {value[0]} wins, {value[1]} losses")
