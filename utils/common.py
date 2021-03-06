from os import mkdir
from os.path import exists
from shutil import rmtree
from tarfile import open as tar_open
from typing import List

import numpy as np
import torch
from tqdm.auto import tqdm

SOS = '<SOS>'
EOS = '<EOS>'
PAD = '<PAD>'
UNK = '<UNK>'
NAN = 'NAN'
METHOD_NAME = 'METHOD_NAME'


def get_device() -> torch.device:
    # CUDA for PyTorch
    use_cuda = torch.cuda.is_available()
    device = torch.device('cuda:0' if use_cuda else 'cpu')
    return device


def fix_seed(seed: int = 7) -> None:
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    np.random.seed(seed)


def extract_tar_gz(tar_path: str, extract_path: str) -> None:
    def tqdm_progress(members):
        extract_progress_bar = tqdm(total=len(list(members.getnames())))
        for member in members:
            extract_progress_bar.update()
            yield member
        extract_progress_bar.close()

    with tar_open(tar_path, 'r:gz') as tarball:
        tarball.extractall(extract_path, members=tqdm_progress(tarball))


def create_folder(path: str, is_clean: bool = True) -> None:
    if is_clean and exists(path):
        rmtree(path)
    if not exists(path):
        mkdir(path)


def segment_sizes_to_slices(sizes: List) -> List:
    cum_sums = np.cumsum(sizes)
    start_of_segments = np.append([0], cum_sums[:-1])
    return [slice(start, end) for start, end in zip(start_of_segments, cum_sums)]


def is_current_step_match(current_step: int, template: int) -> bool:
    return template != -1 and current_step % template == 0
