from os import listdir
from os.path import exists as path_exists
from os.path import join as path_join
from pickle import load as pkl_load
from typing import Tuple, List

from dgl import BatchedDGLGraph, unbatch, batch, reverse
from torch.utils.data import Dataset
from tqdm.auto import tqdm


class JavaDataset(Dataset):

    def __init__(self, batched_graphs_path: str, batch_size: int, invert_edges: bool = False) -> None:
        self.batched_graphs_path = batched_graphs_path
        self.batch_size = batch_size
        self.invert_edges = invert_edges
        assert path_exists(self.batched_graphs_path)

        self.batched_graph_files = sorted(list(filter(
            lambda filename: filename.endswith('.pkl'),
            listdir(self.batched_graphs_path)
        )), key=lambda name: int(name[6:-4]))
        self.batch_desc = {}
        self.n_batches = 0

        self.loaded_batch_basename = None
        self.loaded_batched_graph = None

        # iterate over pkl files to aggregate information about batches
        print(f"prepare the {batched_graphs_path} dataset...")
        for batched_graph_file in tqdm(self.batched_graph_files):
            with open(path_join(self.batched_graphs_path, batched_graph_file), 'rb') as pkl_file:
                batched_graph = pkl_load(pkl_file)
            n_graphs = len(batched_graph['batched_graph'].batch_num_nodes)
            batches_per_file = n_graphs // self.batch_size + (1 if n_graphs % self.batch_size > 0 else 0)

            # collect information from the file
            for batch_id in range(batches_per_file):
                batch_slice = slice(
                    batch_id * self.batch_size,
                    min((batch_id + 1) * self.batch_size, n_graphs)
                )
                self.batch_desc[self.n_batches + batch_id] = (
                    batched_graph_file, batch_slice
                )

            self.n_batches += batches_per_file

    def __len__(self) -> int:
        return self.n_batches

    def __getitem__(self, item) -> Tuple[BatchedDGLGraph, List[str]]:
        batch_basename, batch_slice = self.batch_desc[item]

        # read file only if previous wasn't the same
        if self.loaded_batch_basename != batch_basename:
            with open(path_join(self.batched_graphs_path, batch_basename), 'rb') as pkl_file:
                self.loaded_batched_graph = pkl_load(pkl_file)
            self.loaded_batch_basename = batch_basename

        graphs = unbatch(self.loaded_batched_graph['batched_graph'])

        graphs_for_batch = graphs[batch_slice]
        if self.invert_edges:
            graphs_for_batch = list(map(lambda g: reverse(g, share_ndata=True), graphs_for_batch))

        batched_graph = batch(graphs_for_batch)
        batched_labels = self.loaded_batched_graph['labels'][batch_slice]

        return batched_graph, batched_labels
