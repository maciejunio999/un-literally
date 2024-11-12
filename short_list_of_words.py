# gets big txt file to search though and give You only words with 5WORD_LENGTH letters

import os

WORD_LENGTH = 5
DIR_PATH = os.path.dirname(os.path.realpath(__file__))
FILE = 'slowa.txt'
NEW_FILE = 'slowa_piecioliterowe.txt'

def write_file(file_name, mode, slowa):
    with open(file_name, mode, encoding='utf-8') as f:
        for i in slowa:
            f.write(i + '\n')

with open(f'{DIR_PATH}\\{FILE}', "r", encoding='utf-8', newline='\n') as f:
    nowe_slowa = []
    for i in f:
        slowo, _ = i.split('\r')
        if WORD_LENGTH == len(slowo):
            nowe_slowa.append(slowo)

    try:
        write_file(f'{DIR_PATH}\\{NEW_FILE}', 'x', nowe_slowa)
    except FileExistsError:
        write_file(f'{DIR_PATH}\\{NEW_FILE}', 'w', nowe_slowa)