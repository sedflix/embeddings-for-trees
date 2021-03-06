import unittest

import dgl
import torch

from model.embedding import SubTokenEmbedding
from utils.common import fix_seed, get_device


class EmbeddingTest(unittest.TestCase):

    def test_subtoken_embedding(self):
        fix_seed()
        device = get_device()
        h_emb = 5
        token_to_id = {
            'token|name|first': 0,
            'token|second': 1,
            'token|third|name': 2
        }
        g = dgl.DGLGraph()
        g.add_nodes(3, {'token_id': torch.tensor([0, 1, 2])})
        subtoken_embedding = SubTokenEmbedding(token_to_id, {}, h_emb)

        embed_weight = torch.zeros(len(subtoken_embedding.subtoken_to_id), h_emb)
        embed_weight[subtoken_embedding.subtoken_to_id['token'], 0] = 1
        embed_weight[subtoken_embedding.subtoken_to_id['name'], 1] = 1
        embed_weight[subtoken_embedding.subtoken_to_id['first'], 2] = 1
        embed_weight[subtoken_embedding.subtoken_to_id['second'], 3] = 1
        embed_weight[subtoken_embedding.subtoken_to_id['third'], 4] = 1

        subtoken_embedding.subtoken_embedding.weight = torch.nn.Parameter(embed_weight, requires_grad=True)

        embed_g = subtoken_embedding(g, device)
        true_embeds = torch.tensor([
            [1, 1, 1, 0, 0],
            [1, 0, 0, 1, 0],
            [1, 1, 0, 0, 1]
        ], device=device, dtype=torch.float)

        self.assertEqual(torch.allclose(true_embeds, embed_g.ndata['token_embeds']), True)


if __name__ == '__main__':
    unittest.main()
