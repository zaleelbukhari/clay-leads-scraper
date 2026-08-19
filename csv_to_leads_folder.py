"""Convert Excel lead files into CSVs in the Clay source folder."""

import argparse
import os

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Convert xlsx lead files to CSV.")
    parser.add_argument("input_folder", help="Folder containing .xlsx files")
    parser.add_argument("output_folder", help="Folder to write .csv files (e.g. D:\\LEADS CSV)")
    args = parser.parse_args()

    os.makedirs(args.output_folder, exist_ok=True)

    for filename in os.listdir(args.input_folder):
        if not (filename.endswith(".xlsx") or filename.endswith(".xls")):
            continue
        file_path = os.path.join(args.input_folder, filename)
        try:
            df = pd.read_excel(file_path, engine="openpyxl")
            csv_filename = os.path.splitext(filename)[0] + ".csv"
            csv_path = os.path.join(args.output_folder, csv_filename)
            df.to_csv(csv_path, index=False)
            print(f"Converted: {filename} -> {csv_filename}")
        except Exception as e:
            print(f"Failed to convert {filename}: {e}")


if __name__ == "__main__":
    main()
