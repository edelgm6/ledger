import csv
import os

chase_profile = {
    'clear_prepended_until': 'Settlement Date',
    'clear_out_rows_key_values': [
        ('Transaction Type',['Reinvestment','Sweep in','Sweep out','Buy'])
    ],
    'inflow_column': 'Amount',
    'outflow_column': 'Amount'
}


def read_csv_file(file_path):
    # Step 2: Read the CSV file into a list of lists
    data_list = []
    with open(file_path, 'r', newline='') as csv_file:
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            data_list.append(row)

    return data_list

def clear_prepended_rows(csv_data):
    PREPEND_UNTIL_FLAG = chase_profile['clear_prepended_until']

    target_row_index = None
    for i, row in enumerate(csv_data):
        if PREPEND_UNTIL_FLAG in row:
            target_row_index = i
            break

    if target_row_index is not None:
        del csv_data[:target_row_index]

    return csv_data

def list_of_lists_to_list_of_dicts(list_of_lists):
    column_headings = list_of_lists[0]
    list_of_dicts = [dict(zip(column_headings, row)) for row in list_of_lists[1:]]
    return list_of_dicts

def clear_extraneous_rows(rows_list):

    CLEAR_OUT_ROWS_WITH  = chase_profile['clear_out_rows_key_values']

    cleaned_rows = []
    for row in rows_list:
        for key_clear_pairs in CLEAR_OUT_ROWS_WITH:
            column_name = key_clear_pairs[0]
            clear_out_values = key_clear_pairs[1]
            try:
                if row[column_name] in clear_out_values:
                    continue
            except KeyError:
                continue
        cleaned_rows.append(row)

    return cleaned_rows

if __name__ == "__main__":
    # Step 1: Define the file path to your CSV file on the desktop
    desktop_path = os.path.join(os.path.join(os.path.expanduser('~')), 'Desktop')
    csv_file_path = os.path.join(desktop_path, 'example.csv')

    # Step 3: Read the entire CSV file into a list of lists
    csv_data = read_csv_file(csv_file_path)

    rows_cleaned_csv = clear_prepended_rows(csv_data)
    dict_based_csv = list_of_lists_to_list_of_dicts(rows_cleaned_csv)
    cleared_rows_csv = clear_extraneous_rows(dict_based_csv)
    print(cleared_rows_csv)


