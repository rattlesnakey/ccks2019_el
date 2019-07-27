# -*- coding: utf-8 -*-

"""

@author: alexyang

@contact: alex.yang0326@gmail.com

@file: train_2step.py

@time: 2019/5/16 9:40

@desc:

"""

import os
import gc
import time
import numpy as np
from itertools import product
from keras import optimizers, backend as K
from config import ModelConfig, PROCESSED_DATA_DIR, VOCABULARY_TEMPLATE, MENTION_TO_ENTITY_FILENAME, \
    EMBEDDING_MATRIX_TEMPLATE, LOG_DIR, PERFORMANCE_LOG
from models.recognition_model import RecognitionModel
from utils.data_loader import RecognitionDataGenerator
from utils.io import pickle_load, format_filename, write_log

os.environ['CUDA_VISIBLE_DEVICES'] = "1"


def get_optimizer(op_type, learning_rate):
    if op_type == 'sgd':
        return optimizers.SGD(learning_rate)
    elif op_type == 'rmsprop':
        return optimizers.RMSprop(learning_rate)
    elif op_type == 'adagrad':
        return optimizers.Adagrad(learning_rate)
    elif op_type == 'adadelta':
        return optimizers.Adadelta(learning_rate)
    elif op_type == 'adam':
        return optimizers.Adam(learning_rate, clipnorm=5)
    else:
        raise ValueError('Optimizer Not Understood: {}'.format(op_type))


def train_recognition(model_name, label_schema='BIOES', batch_size=32, n_epoch=50, learning_rate=0.001,
                      optimizer_type='adam', use_char_input=True, embed_type=None, embed_trainable=True,
                      use_bert_input=False, bert_type='bert', bert_trainable=True, bert_layer_num=1,
                      use_bichar_input=False, bichar_embed_type=None, bichar_embed_trainable=True,
                      use_word_input=False, word_embed_type=None, word_embed_trainable=True,
                      use_charpos_input=False, charpos_embed_type=None, charpos_embed_trainable=True,
                      use_softword_input=False, use_dictfeat_input=False, use_maxmatch_input=False,
                      callbacks_to_add=None, overwrite=False, swa_start=3, early_stopping_patience=3, **kwargs):
    config = ModelConfig()
    config.model_name = model_name
    config.label_schema = label_schema
    config.batch_size = batch_size
    config.n_epoch = n_epoch
    config.learning_rate = learning_rate
    config.optimizer = get_optimizer(optimizer_type, learning_rate)
    config.embed_type = embed_type
    config.use_char_input = use_char_input
    if embed_type:
        config.embeddings = np.load(format_filename(PROCESSED_DATA_DIR, EMBEDDING_MATRIX_TEMPLATE, type=embed_type))
        config.embed_trainable = embed_trainable
        config.embed_dim = config.embeddings.shape[1]
    else:
        config.embeddings = None
        config.embed_trainable = True

    config.callbacks_to_add = callbacks_to_add or ['modelcheckpoint', 'earlystopping']
    if 'swa' in config.callbacks_to_add:
        config.swa_start = swa_start
        config.early_stopping_patience = early_stopping_patience

    config.vocab = pickle_load(format_filename(PROCESSED_DATA_DIR, VOCABULARY_TEMPLATE, level='char'))
    config.vocab_size = len(config.vocab) + 2
    config.mention_to_entity = pickle_load(format_filename(PROCESSED_DATA_DIR, MENTION_TO_ENTITY_FILENAME))

    if config.use_char_input:
        config.exp_name = '{}_{}_{}_{}_{}_{}_{}'.format(model_name, config.embed_type if config.embed_type else 'random',
                                                        'tune' if config.embed_trainable else 'fix', batch_size,
                                                        optimizer_type, learning_rate, label_schema)
    else:
        config.exp_name = '{}_{}_{}_{}_{}'.format(model_name, batch_size, optimizer_type, learning_rate, label_schema)
    if config.n_epoch != 50:
        config.exp_name += '_{}'.format(config.n_epoch)
    if kwargs:
        config.exp_name += '_' + '_'.join([str(k) + '_' + str(v) for k, v in kwargs.items()])
    callback_str = '_' + '_'.join(config.callbacks_to_add)
    callback_str = callback_str.replace('_modelcheckpoint', '').replace('_earlystopping', '')
    config.exp_name += callback_str

    config.use_bert_input = use_bert_input
    config.bert_type = bert_type
    config.bert_trainable = bert_trainable
    config.bert_layer_num = bert_layer_num
    assert config.use_char_input or config.use_bert_input
    if config.use_bert_input:
        config.exp_name += '_{}_layer_{}_{}'.format(bert_type, bert_layer_num, 'tune' if config.bert_trainable else 'fix')
    config.use_bichar_input = use_bichar_input
    if config.use_bichar_input:
        config.bichar_vocab = pickle_load(format_filename(PROCESSED_DATA_DIR, VOCABULARY_TEMPLATE, level='bichar'))
        config.bichar_vocab_size = len(config.bichar_vocab) + 2
        if bichar_embed_type:
            config.bichar_embeddings = np.load(format_filename(PROCESSED_DATA_DIR, EMBEDDING_MATRIX_TEMPLATE,
                                                               type=bichar_embed_type))
            config.bichar_embed_trainable = bichar_embed_trainable
            config.bichar_embed_dim = config.bichar_embeddings.shape[1]
        else:
            config.bichar_embeddings = None
            config.bichar_embed_trainable = True
        config.exp_name += '_bichar_{}_{}'.format(bichar_embed_type if bichar_embed_type else 'random',
                                                  'tune' if config.bichar_embed_trainable else 'fix')
    config.use_word_input = use_word_input
    if config.use_word_input:
        config.word_vocab = pickle_load(format_filename(PROCESSED_DATA_DIR, VOCABULARY_TEMPLATE, level='word'))
        config.word_vocab_size = len(config.word_vocab) + 2
        if word_embed_type:
            config.word_embeddings = np.load(format_filename(PROCESSED_DATA_DIR, EMBEDDING_MATRIX_TEMPLATE,
                                                             type=word_embed_type))
            config.word_embed_trainable = word_embed_trainable
            config.word_embed_dim = config.word_embeddings.shape[1]
        else:
            config.word_embeddings = None
            config.word_embed_trainable = True
        config.exp_name += '_word_{}_{}'.format(word_embed_type if word_embed_type else 'random',
                                                'tune' if config.word_embed_trainable else 'fix')
    config.use_charpos_input = use_charpos_input
    if config.use_charpos_input:
        config.charpos_vocab = pickle_load(format_filename(PROCESSED_DATA_DIR, VOCABULARY_TEMPLATE, level='charpos'))
        config.charpos_vocab_size = len(config.charpos_vocab) + 2
        if charpos_embed_type:
            config.charpos_embeddings = np.load(format_filename(PROCESSED_DATA_DIR, EMBEDDING_MATRIX_TEMPLATE,
                                                                type=charpos_embed_type))
            config.charpos_embed_trainable = charpos_embed_trainable
            config.charpos_embed_dim = config.charpos_embeddings.shape[1]
        else:
            config.charpos_embeddings = None
            config.charpos_embed_trainable = True
        config.exp_name += '_charpos_{}_{}'.format(charpos_embed_type if charpos_embed_type else 'random',
                                                   'tune' if config.charpos_embed_trainable else 'fix')
    config.use_softword_input = use_softword_input
    if config.use_softword_input:
        config.exp_name += '_softword'
    config.use_dictfeat_input = use_dictfeat_input
    if config.use_dictfeat_input:
        config.exp_name += '_dictfeat'
    config.use_maxmatch_input = use_maxmatch_input
    if config.use_maxmatch_input:
        config.exp_name += '_maxmatch'

    # logger to log output of training process
    train_log = {'exp_name': config.exp_name, 'batch_size': batch_size, 'optimizer': optimizer_type, 'epoch': n_epoch,
                 'learning_rate': learning_rate, 'other_params': kwargs}

    print('Logging Info - Experiment: %s' % config.exp_name)
    model_save_path = os.path.join(config.checkpoint_dir, '{}.hdf5'.format(config.exp_name))
    model = RecognitionModel(config, **kwargs)

    train_data_type, dev_data_type = 'train', 'dev'
    train_generator = RecognitionDataGenerator(train_data_type, config.batch_size, config.label_schema,
                                               config.label_to_one_hot[config.label_schema],
                                               config.vocab if config.use_char_input else None,
                                               config.bert_vocab_file(config.bert_type) if config.use_bert_input else None,
                                               config.bert_seq_len, config.bichar_vocab, config.word_vocab,
                                               config.use_word_input, config.charpos_vocab, config.use_softword_input,
                                               config.use_dictfeat_input, config.use_maxmatch_input)
    valid_generator = RecognitionDataGenerator(dev_data_type, config.batch_size, config.label_schema,
                                               config.label_to_one_hot[config.label_schema],
                                               config.vocab if config.use_char_input else None,
                                               config.bert_vocab_file(config.bert_type) if config.use_bert_input else None,
                                               config.bert_seq_len, config.bichar_vocab, config.word_vocab,
                                               config.use_word_input, config.charpos_vocab, config.use_softword_input,
                                               config.use_dictfeat_input, config.use_maxmatch_input)

    if not os.path.exists(model_save_path) or overwrite:
        start_time = time.time()
        model.train(train_generator, valid_generator)
        elapsed_time = time.time() - start_time
        print('Logging Info - Training time: %s' % time.strftime("%H:%M:%S", time.gmtime(elapsed_time)))
        train_log['train_time'] = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))

    model.load_best_model()

    print('Logging Info - Evaluate over valid data:')
    r, p, f1 = model.evaluate(valid_generator)
    train_log['dev_performance'] = (r, p, f1)

    swa_type = None
    if 'swa' in config.callbacks_to_add:
        swa_type = 'swa'
    elif 'swa_clr' in config.callbacks_to_add:
        swa_type = 'swa_clr'
    if swa_type:
        model.load_swa_model(swa_type)
        print('Logging Info - Evaluate over valid data based on swa model:')
        r, p, f1 = model.evaluate(valid_generator)
        train_log['swa_dev_performance'] = (r, p, f1)

    train_log['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    write_log(format_filename(LOG_DIR, PERFORMANCE_LOG, model_type='2step_er'), log=train_log, mode='a')

    del model
    gc.collect()
    K.clear_session()


if __name__ == '__main__':
    bert_types = ['bert', 'ernie', 'bert_wwm']
    use_bichar_inputs = [True, False]
    use_charpos_inputs = [True, False]
    encoder_types = ['bilstm_cnn', 'mullstm_cnn', 'stlstm_cnn']

    for bert_type, use_bichar_input, use_charpos_input, encoder_type in product(bert_types, use_bichar_inputs,
                                                                                use_charpos_inputs, encoder_types):
        train_recognition(model_name='2step_er', label_schema='BIOES', batch_size=32,
                          n_epoch=50, use_char_input=True, embed_type='c2v', embed_trainable=False,
                          use_bert_input=True, bert_type=bert_type, bert_trainable=False, bert_layer_num=1,
                          use_bichar_input=use_bichar_input, bichar_embed_type='bic2v', bichar_embed_trainable=False,
                          use_word_input=True, word_embed_type='w2v', word_embed_trainable=False,
                          use_charpos_input=use_charpos_input, charpos_embed_type='cpos2v', charpos_embed_trainable=False,
                          use_softword_input=True, use_dictfeat_input=True, use_maxmatch_input=True,
                          encoder_type=encoder_type, use_crf=True,
                          callbacks_to_add=['swa', 'modelcheckpoint', 'earlystopping'])
