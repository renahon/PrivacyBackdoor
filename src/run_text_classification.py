import torch.nn as nn
from transformers import BertForSequenceClassification, BertTokenizer, AutoConfig
from edit_bert import bert_backdoor_initialization, bert_semi_active_initialization
from data import get_dataloader, load_text_dataset
from torch.optim import SGD
from train import text_train, text_evaluation
import torch


def build_bert_classifier(info_dataset, info_model, info_train, logger=None, save_path=None):
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased', do_lower_case=True)

    dataset_name = info_dataset['NAME']
    max_len = info_dataset['MAX_LEN']

    batch_size = info_train['BATCH_SIZE']
    learning_rate = info_train['LR']
    learning_rate_probe = info_train['LR_PROBE']
    num_epochs = info_train['EPOCHS']
    device = info_train['DEVICE']
    num_workers = info_train['NUM_WORKERS']
    is_debug = info_train['IS_DEBUG']

    train_dataset, test_dataset, num_classes = load_text_dataset(dataset=dataset_name, tokenizer=tokenizer, max_len=max_len)
    train_dataloader, test_dataloader = get_dataloader(train_dataset, ds1=test_dataset, batch_size=batch_size, num_workers=num_workers)

    use_backdoor_initialization = info_model['USE_BACKDOOR_INITIALIZATION']
    use_semi_active_initialization = info_model['USE_SEMI_ACTIVE_INITIALIZATION']
    arch = info_model['ARCH']

    config = AutoConfig.from_pretrained('bert-base-uncased')
    config.hidden_act = arch['relu']
    config.hidden_dropout_prob = arch['dropout']
    config.attention_probs_dropout_prob = arch['dropout']
    config.num_labels = num_classes
    config.output_attentions = True
    config.output_hidden_states = True
    classifier = BertForSequenceClassification.from_pretrained(pretrained_model_name_or_path='bert-base-uncased', config=config)
    classifier.bert.pooler.activation = getattr(nn, 'ReLU')()

    weight_path = info_model.get('PATH', None)
    if weight_path is not None:
        classifier.load_state_dict(torch.load(weight_path, map_location='cpu'))

    if use_backdoor_initialization:
        num_backdoors = info_model['NUM_BACKDOORS']
        args_weight = info_model['WEIGHT_SETTING']
        args_bait = info_model['BAIT']
        # TODO: use another dataset to generate bait
        bert_monitor = bert_backdoor_initialization(classifier, dataloader4bait=train_dataloader, args_weight=args_weight, args_bait=args_bait,
                                                    max_len=max_len, num_backdoors=num_backdoors)
        print('use backdoor initialization')
    elif use_semi_active_initialization:
        args = {'regular_features_group': (0, 8), 'large_constant': 5e3, 'embedding_multiplier': 20.0}
        bert_semi_active_initialization(classifier, args)
        bert_monitor = None
        print('use semi-active initialization')
    else:
        bert_monitor = None

    optimizer = SGD([{'params': classifier.bert.parameters(), 'lr': learning_rate}, {'params': classifier.classifier.parameters(), 'lr': learning_rate_probe}])
    classifier = classifier.to(device)

    for j in range(num_epochs):
        print(f'Epoch: {j}')
        text_train(classifier, train_dataloader=train_dataloader, optimizer=optimizer, device=device, logger=logger,
                   is_debug=is_debug, monitor=bert_monitor)
        acc, val_loss = text_evaluation(classifier, evaluation_dataloader=test_dataloader, device=device)
        print(f'Validation ACC:{acc}, LOSS:{val_loss}')

    if save_path is not None:
        if bert_monitor is not None:
            torch.save(bert_monitor, f'{save_path}_monitor.pth')
        torch.save(classifier.state_dict(), f'{save_path}_wt.pth')


if __name__ == '__main__':
    # this is used for debugging
    # TODO: finish bait setting
    model_path = None  # './weights/.pth'
    info_dataset = {'NAME': 'trec', 'ROOT': None, 'MAX_LEN': 48}
    info_model = {'PATH': model_path, 'USE_BACKDOOR_INITIALIZATION': True, 'USE_SEMI_ACTIVE_INITIALIZATION': False,
                  'ARCH': {'hidden_act': 'relu', 'dropout': 0.0, 'pooler_act': 'ReLU'}, 'NUM_BACKDOORS': 32}
    bait_setting = {}
    weight_setting = {
        'HIDDEN_GROUP': {'features': (0, 8), 'position': (8, 9), 'signal': (9, 11), 'backdoor': (11, 12)},
        'EMBEDDING': {'emb_multiplier': 100.0, 'pst_multiplier': 200.0, 'large_constant': 5000.0},
        'FEATURE_SYNTHESIZER': {'large_constant': 5000.0, 'signal_value_multiplier': 1.0, 'signal_out_multiplier': 1.0, 'add': 5.0},
        'BACKDOOR': {'multiplier': 25.0, 'large_constant': 5000.0},
        'LIMITER': {'large_constant': 5000.0},
        'PASSING_AMPLIFIER': {'MULTIPLIER': [0.2, 0.2, 0.2, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
                              'PASS_THRESHOLD': [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2]},
        'ENDING': {'pooler_multiplier': 0.5, 'pooler_noise_threshold': 0.8, 'classifier_backdoor_multiplier': 20.0}
    }
    info_model['BAIT_SETTING'] = bait_setting
    info_model['WEIGHT_SETTING'] = weight_setting

    info_train = {'BATCH_SIZE': 32, 'LR': 1e-4, 'LR_PROBE': 0.2, 'EPOCHS': 1, 'DEVICE': 'cpu', 'NUM_WORKERS': 2,
                  'VERBOSE': False, 'IS_DEBUG': False}
    build_bert_classifier(info_dataset=info_dataset, info_model=info_model, info_train=info_train)
    # TODO: allows to load weight from trained
