import csv
from pathlib import Path

def create_small_sample(input_file, output_file, rows=100000):
    # هذا الجزء ينشئ عينة صغيرة من CSV باستخدام Streaming،
    # ويمنع تحويل الملف كاملًا إلى List في الذاكرة.
    input_file = Path(input_file)
    output_file = Path(output_file)

    with open(input_file, "r", encoding="utf-8-sig", newline="") as src:
        reader = csv.reader(src)
        header = next(reader)

        with open(output_file, "w", encoding="utf-8", newline="") as dst:
            writer = csv.writer(dst)
            writer.writerow(header)

            for i, row in enumerate(reader):
                if i >= rows:
                    break
                writer.writerow(row)

    return output_file
