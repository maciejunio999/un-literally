import os



DIR_PATH = os.path.dirname(os.path.realpath(__file__))
FILE = 'slowa_piecioliterowe.txt'



# chceck some letters (in form of list) are in given word
def check(list, word):
    j = 0
    for i in list:
        if i not in word:
            j += 1
    if j == len(list):
        return word



# we get them from txt file
all_words = []

with open(f'{DIR_PATH}\\{FILE}', "r", encoding='utf-8', newline='\n') as f:
    for i in f:
        slowo, _ = i.split('\r')
        if 5 == len(slowo):
            all_words.append(slowo)



### first filter ###
slowa_1 = [] # words after first filter
starts_with = 'p'

for i in all_words:
    if i.startswith(starts_with):
        slowa_1.append(i)


### second filter ###
#no_letters = ['a', 'j', 't', 'e', 'ę', 'o', 'd', 'p', 'ą', 'y'] # list of letters that are not in our word
no_letters = ['s', 'e', 'y', 'u', 'd', 'k', 'i', 'm', 'n', 'b', 'ę', 'ż', 'j', 't']
slowa_2 = [] # words after second filter

for i in slowa_1:
    if not check(no_letters, i) == None:
        slowa_2.append(check(no_letters, i))


### third filter ###
#letters = {'z': [1, 3], 'i': [2, 3, 4]}
letters = {'l': [1], 'a': [2]}
slowa_3 = []
lists = [] # words after third filter

for key, values in letters.items():
    words_helping = []
    for i in slowa_2:
        for v in values:
            if i[v] == key and i not in words_helping:
                words_helping.append(i)
    lists.append(words_helping)


words = lists[0]
for i in lists[1:]:
    for j in words:
        if j not in i:
            words.remove(j)

# i know this functions are the same, but after one iteration there might be some words not matching conditions
# but after second iteration we gat what we should expect
for i in lists[1:]:
    for j in words:
        if j not in i:
            words.remove(j)

print(words)