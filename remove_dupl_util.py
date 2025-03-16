import os
import hashlib


def file_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def remove_duplicates(directory):
    file_hashes = {}
    for filename in os.listdir(directory):
        if filename.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
            filepath = os.path.join(directory, filename)
            filehash = file_hash(filepath)
            if filehash not in file_hashes:
                file_hashes[filehash] = filepath
            else:
                print(f"Removing duplicate file: {filepath}")
                os.remove(filepath)


directory_path = 'C:\\Users\\edis0n\\Downloads\\Telegram Desktop'
remove_duplicates(directory_path)
