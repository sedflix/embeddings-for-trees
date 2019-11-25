from typing import Dict, Union

import torch
import torch.nn as nn
from dgl import BatchedDGLGraph

from model.attention import LuongConcatAttention
from model.attention_decoder import LSTMAttentionDecoder, _IAttentionDecoder
from model.decoder import _IDecoder, LinearDecoder, LSTMDecoder
from model.embedding import _IEmbedding, FullTokenEmbedding, SubTokenEmbedding
from model.encoder import _IEncoder
from model.treelstm import TreeLSTM


class Tree2Seq(nn.Module):
    def __init__(self, embedding: _IEmbedding, encoder: _IEncoder,
                 decoder: Union[_IDecoder, _IAttentionDecoder], using_attention: bool) -> None:
        super().__init__()
        self.embedding = embedding
        self.encoder = encoder
        self.decoder = decoder
        self.using_attention = using_attention

    def forward(self,
                graph: BatchedDGLGraph, root_indexes: torch.LongTensor,
                ground_truth: torch.Tensor, device: torch.device) -> torch.Tensor:
        """

        :param graph: the batched graph with function's asts
        :param root_indexes: indexes of roots in the batched graph
        :param ground_truth: [length of the longest sequence, batch size]
        :param device: torch device
        :return: [length of the longest sequence, batch size, number of classes] logits for each element in sequence
        """
        embedded_graph = self.embedding(graph, device)
        # [number of nodes, hidden state]
        node_hidden_states, node_memory_cells = self.encoder(embedded_graph, device)
        # [1, batch size, hidden state] (LSTM input requires)
        root_hidden_states = node_hidden_states[root_indexes].unsqueeze(0)
        root_memory_cells = node_memory_cells[root_indexes].unsqueeze(0)

        max_length, batch_size = ground_truth.shape
        # [length of the longest sequence, batch size, number of classes]
        outputs = torch.zeros(max_length, batch_size, self.decoder.out_size).to(device)

        encoder_outputs = None
        if self.using_attention:
            start_of_tree = root_indexes.tolist()
            end_of_tree = start_of_tree[1:] + [node_hidden_states.shape[0]]
            hidden_states_per_tree = [
                node_hidden_states[start:end] for start, end in zip(start_of_tree, end_of_tree)
            ]
            number_of_nodes = [tree_hs.shape[0] for tree_hs in hidden_states_per_tree]
            max_number_of_nodes = max(number_of_nodes)
            encoder_outputs = torch.zeros(batch_size, max_number_of_nodes, self.decoder.hidden_size).to(device)
            for num, (tree_hs, tree_sz) in enumerate(zip(hidden_states_per_tree, number_of_nodes)):
                encoder_outputs[num, :tree_sz] = tree_hs

        current_input = ground_truth[0]
        for step in range(1, max_length):

            if self.using_attention:
                output, root_hidden_states, root_memory_cells = \
                    self.decoder(current_input, root_hidden_states, root_memory_cells, encoder_outputs)
            else:
                output, root_hidden_states, root_memory_cells = \
                    self.decoder(current_input, root_hidden_states, root_memory_cells)

            outputs[step] = output
            current_input = ground_truth[step]

        return outputs

    @staticmethod
    def predict(logits: torch.Tensor) -> torch.Tensor:
        """Predict token for each step by given logits

        :param logits: [max length, batch size, number of classes] logits for each position in sequence
        :return: [max length, batch size] token's ids for each position in sequence
        """
        tokens_probas = nn.functional.softmax(logits, dim=-1)
        return tokens_probas.argmax(dim=-1)


class ModelFactory:
    _embeddings = {
        'FullTokenEmbedding': FullTokenEmbedding,
        'SubTokenEmbedding': SubTokenEmbedding
    }
    _encoders = {
        'TreeLSTM': TreeLSTM
    }
    _decoders = {
        'LinearDecoder': LinearDecoder,
        'LSTMDecoder': LSTMDecoder,
        'LSTMAttentionDecoder': LSTMAttentionDecoder
    }
    _attentions = {
        'LuongConcatAttention': LuongConcatAttention
    }

    def __init__(self, embedding_info: Dict, encoder_info: Dict, decoder_info: Dict):
        self.embedding_info = embedding_info
        self.encoder_info = encoder_info
        self.decoder_info = decoder_info

        self.embedding = self._get_module(self.embedding_info['name'], self._embeddings)
        self.encoder = self._get_module(self.encoder_info['name'], self._encoders)

        self.using_attention = 'attention' in self.decoder_info
        if self.using_attention:
            self.attention_info = self.decoder_info['attention']
            self.attention = self._get_module(self.attention_info['name'], self._attentions)
        self.decoder = self._get_module(self.decoder_info['name'], self._decoders)

    @staticmethod
    def _get_module(module_name: str, modules_dict: Dict) -> nn.Module:
        if module_name not in modules_dict:
            raise ModuleNotFoundError(f"Unknown module {module_name}, try one of {', '.join(modules_dict.keys())}")
        return modules_dict[module_name]

    def construct_model(self, device: torch.device) -> Tree2Seq:
        if self.using_attention:
            attention_part = self.attention(**self.attention_info['params'])
            decoder_part = self.decoder(**self.decoder_info['params'], attention=attention_part)
        else:
            decoder_part = self.decoder(**self.decoder_info['params'])
        return Tree2Seq(
            self.embedding(**self.embedding_info['params']),
            self.encoder(**self.encoder_info['params']),
            decoder_part,
            self.using_attention
        ).to(device)
