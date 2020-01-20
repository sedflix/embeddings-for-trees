from argparse import ArgumentParser
from json import load as json_load
from pickle import load as pkl_load
from typing import Dict

import torch
import torch.nn as nn
from tqdm.auto import tqdm

from data_workers.dataset import JavaDataset
from model.tree2seq import ModelFactory, Tree2Seq
from utils.common import fix_seed, get_device, is_current_step_match
from utils.learning_info import LearningInfo
from utils.logging import get_possible_loggers, FileLogger, WandBLogger, FULL_DATASET, TerminalLogger
from utils.training import train_on_batch, evaluate_dataset


def train(params: Dict, logging: str) -> None:
    fix_seed()
    device = get_device()
    print(f"using {device} device")

    training_set = JavaDataset(params['paths']['train'], params['batch_size'], True)
    validation_set = JavaDataset(params['paths']['validate'], params['batch_size'], True)

    with open(params['paths']['vocabulary'], 'rb') as pkl_file:
        vocabulary = pkl_load(pkl_file)
        token_to_id = vocabulary['token_to_id']
        type_to_id = vocabulary['type_to_id']
        label_to_id = vocabulary['label_to_id']

    print('model initializing...')
    # create model
    model_factory = ModelFactory(
        params['embedding'], params['encoder'], params['decoder'],
        params['hidden_states'], token_to_id, type_to_id, label_to_id
    )
    model: Tree2Seq = model_factory.construct_model(device)

    # create optimizer
    optimizer = torch.optim.Adam(
        model.parameters(), lr=params['lr'], weight_decay=params['weight_decay']
    )

    # define loss function
    criterion = nn.CrossEntropyLoss(ignore_index=model.decoder.pad_index).to(device)

    # init logging class
    logger = None
    if logging == TerminalLogger.name:
        logger = TerminalLogger(params['checkpoints_folder'])
    elif logging == FileLogger.name:
        logger = FileLogger(params, params['logging_folder'], params['checkpoints_folder'])
    elif logging == WandBLogger.name:
        logger = WandBLogger('treeLSTM', params, model, params['checkpoints_folder'])

    # train loop
    print("ok, let's train it")
    for epoch in range(params['n_epochs']):
        train_acc_info = LearningInfo()

        # iterate over training set
        for batch_id in tqdm(range(len(training_set))):
            graph, labels = training_set[batch_id]
            graph.ndata['token_id'] = graph.ndata['token_id'].to(device)
            graph.ndata['type_id'] = graph.ndata['type_id'].to(device)
            batch_info = train_on_batch(
                model, criterion, optimizer, graph, labels, params, device
            )
            train_acc_info.accumulate_info(batch_info)
            if is_current_step_match(batch_id, params['logging_step']):
                logger.log(train_acc_info.get_state_dict(), epoch, batch_id)
                train_acc_info = LearningInfo()
            if is_current_step_match(batch_id, params['evaluation_step']):
                eval_epoch_info = evaluate_dataset(validation_set, model, criterion, device)
                logger.log(eval_epoch_info.get_state_dict(), epoch, FULL_DATASET, False)

        # iterate over validation set
        eval_epoch_info = evaluate_dataset(validation_set, model, criterion, device)
        logger.log(eval_epoch_info.get_state_dict(), epoch, FULL_DATASET, False)

        if is_current_step_match(epoch, params['checkpoint_step']):
            logger.save_model(model, epoch, model_factory.save_configuration())


if __name__ == '__main__':
    arg_parse = ArgumentParser()
    arg_parse.add_argument('--config', type=str, required=True, help='path to config json')
    arg_parse.add_argument('--logging', choices=get_possible_loggers(), required=True)
    args = arg_parse.parse_args()

    with open(args.config) as config_file:
        train(json_load(config_file), args.logging)
