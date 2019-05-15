# -*- coding:utf-8 -*-

import json
import time
import os

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

import mxnet as mx
from mxnet import nd
from mxnet import autograd
from mxnet import gluon
from mxnet.gluon import Trainer

from lib.utils import *
from model import STGCN

##########
# configuration part

# choose which device you want to use, if you want to use GPU, set ctx = mx.gpu(0)
ctx = mx.cpu()

# number of vertices in your graph
num_of_vertices = 307

# orders of chebyshev polynomials
orders_of_cheb = 3

# we use a Gaussian kernel to normalize the adjacency matrix, epsilon is the threshold
epsilon = 0.5

# how many points you want to train the model and how many you want to predict
num_points_for_train, num_points_for_predict = 12, 1

# learning rate
learning_rate = 1e-2

# optimizer
optimizer = 'RMSprop'

# decay rate
decay_rate = 0.7

# decay interval
decay_interval = 5

# training epochs
epochs = 10

# batch_size
batch_size = 32
##########

def data_preprocess(adj_filename):
    '''
    Returns
    ----------
    A: Adjacency matrix, np.ndarray, shape is (num_of_vertices, num_of_vertices)
    
    X: Graph signal matrix, np.ndarray, shape is (num_of_vertices, num_of_features, num_of_samples)
    '''
    
    # distance information between vertices in the graph
    distance = pd.read_csv(adj_filename)

    # initialize an adjacency matrix of the graph with 0
    A = np.zeros((num_of_vertices, num_of_vertices))
    
    # put distances into the corresponding position
    for x, y, dis in distance.values:
        x_index = int(x)
        y_index = int(y)
        A[x_index, y_index] = dis
        A[y_index, x_index] = dis

    # compute the variance of the all distances which does not equal zero
    tmp = A.flatten()
    var = np.var(tmp[tmp!=0])

    # normalization
    A = np.exp(- (A ** 2) / var)

    # drop the value less than threshold
    A[A < epsilon] = 0
    
    # preprocessing graph signal data
    with open('data/graph_signal_data_small.txt', 'r') as f:
        data = json.loads(f.read().strip())

    # initialize the graph signal matrix, shape is (num_of_vertices, num_of_features, num_of_samples)
    X = np.empty(shape = (num_of_vertices,  # num_of_vertices
                          len(data[list(data.keys())[0]].keys()),  # num_of_features
                          len(list(data[list(data.keys())[0]].values())[0])),  # num_of_samples
                )
    
    # i is the index of the vertice
    for i in range(num_of_vertices):
        X[i, 0, :] = np.array(data[str(i)]['flow'])
        X[i, 1, :] = np.array(data[str(i)]['occupy'])
        X[i, 2, :] = np.array(data[str(i)]['speed'])
    return A, X

def build_dataset(graph_signal_matrix):
    '''
    Parameters
    ----------
    graph_signal_matrix: np.ndarray, graph signal matrix, shape is (num_of_vertices, num_of_features, num_of_samples)
    
    Returns
    ----------
    features: np.ndarray, shape is (num_of_samples, num_of_features, num_of_vertices, num_points_for_training)
    
    target: np.ndarray, shape is (num_of_samples, num_of_vertices, num_points_for_prediction)
    '''
    
    # generate the beginning index and the ending index of a sample, which bounds (num_points_for_training + num_points_for_predicting) points
    indices = [(i, i + (num_points_for_train + num_points_for_predict)) 
                for i in range(graph_signal_matrix.shape[2] - (num_points_for_train + num_points_for_predict) + 1)]
    
    # save samples
    features, target = [], []
    for i, j in indices:
        features.append(graph_signal_matrix[:, :, i: i + num_points_for_train].transpose((1, 0, 2)))
        target.append(graph_signal_matrix[:, 0, i + num_points_for_train: j])
    
    features = np.concatenate([np.expand_dims(i, 0) for i in features], axis=0)
    target = np.concatenate([np.expand_dims(i, 0) for i in target], axis=0)
    
    return features, target

def train_model(net, training_dataloader, validation_dataloader, testing_dataloader):
    '''
    train the model
    
    Parameters
    ----------
    net: model which has been initialized
    
    training_dataloader, validation_dataloader, testing_dataloader: gluon.data.dataloader.DataLoader
    
    Returns
    ----------
    train_loss_list: list(float), which contains loss values of training process
    
    val_loss_list: list(float), which contains loss values of validation process
    
    test_loss_list: list(float), which contains loss values of testing process
    
    '''
    train_loss_list = []
    val_loss_list = []
    test_loss_list = []
    for epoch in range(epochs):
        t = time.time()

        train_loss_list_tmp = []
        for x, y in training_dataloader:
            with autograd.record():
                output = net(x)
                l = loss_function(output, y)
            l.backward()
            train_loss_list_tmp.append(l.mean().asnumpy()[0])
            trainer.step(batch_size)

        train_loss_list.append( sum(train_loss_list_tmp) / len(train_loss_list_tmp) )

        val_loss_list_tmp = []
        for x, y in validation_dataloader:
            output = net(x)
            val_loss_list_tmp.append(loss_function(output, y).mean().asnumpy()[0])

        val_loss_list.append( sum(val_loss_list_tmp) / len(val_loss_list_tmp) )

        test_loss_list_tmp = []
        for x, y in testing_dataloader:
            output = net(x)
            test_loss_list_tmp.append(loss_function(output, y).mean().asnumpy()[0])

        test_loss_list.append( sum(test_loss_list_tmp) / len(test_loss_list_tmp) )

        print('current epoch is %s'%(epoch + 1))
        print('training loss(MSE):', train_loss_list[-1])
        print('validation loss(MSE):', val_loss_list[-1])
        print('testing loss(MSE):', test_loss_list[-1])
        print('time:', time.time() - t)
        print()

        with open('results.log', 'a') as f:
            f.write('training loss(MSE): %s'%(train_loss_list[-1]))
            f.write('\n')
            f.write('validation loss(MSE): %s'%(val_loss_list[-1]))
            f.write('\n')
            f.write('testing loss(MSE): %s'%(test_loss_list[-1]))
            f.write('\n\n')

        if (epoch + 1) % 5 == 0:
            filename = 'stgcn_params/stgcn.params_%s'%(epoch)
            net.save_parameters(filename)

        if (epoch + 1) % decay_interval == 0:
            trainer.set_learning_rate(trainer.learning_rate * decay_rate)
    
    return train_loss_list, val_loss_list, test_loss_list

if __name__ == "__main__":
    A, X = data_preprocess('data/test_data1/distance.csv')

    L_tilde = scaled_Laplacian(A)
    cheb_polys = [nd.array(i, ctx=ctx) for i in cheb_polynomial(L_tilde, orders_of_cheb)]

    # training: validation: testing = 6: 2: 2
    split_line1 = int(X.shape[2] * 0.6)
    split_line2 = int(X.shape[2] * 0.8)

    train_original_data = X[:, :, : split_line1]
    val_original_data = X[:, :, split_line1: split_line2]
    test_original_data = X[:, :, split_line2: ]

    training_data, training_target = build_dataset(train_original_data)
    val_data, val_target = build_dataset(val_original_data)
    testing_data, testing_target = build_dataset(test_original_data)

    # Z-score preprocessing
    assert num_of_vertices == training_data.shape[2]
    assert num_points_for_train == training_data.shape[3]
    _, num_of_features, _, _ = training_data.shape

    transformer = StandardScaler()
    training_data_norm = transformer.fit_transform(training_data.reshape(training_data.shape[0], -1))\
        .reshape(training_data.shape[0], num_of_features, num_of_vertices, num_points_for_train)
    val_data_norm = transformer.transform(val_data.reshape(val_data.shape[0], -1))\
        .reshape(val_data.shape[0], num_of_features, num_of_vertices, num_points_for_train)
    testing_data_norm = transformer.transform(testing_data.reshape(testing_data.shape[0], -1))\
        .reshape(testing_data.shape[0], num_of_features, num_of_vertices, num_points_for_train)

    training_data_norm = nd.array(training_data_norm, ctx = ctx)
    val_data_norm = nd.array(val_data_norm, ctx = ctx)
    testing_data_norm = nd.array(testing_data_norm, ctx = ctx)

    training_target = nd.array(training_target, ctx = ctx)
    val_target = nd.array(val_target, ctx = ctx)
    testing_target = nd.array(testing_target, ctx = ctx)

    print('training data shape:', training_data_norm.shape, training_target.shape)
    print('validation data shape:', val_data_norm.shape, val_target.shape)
    print('testing data shape:', testing_data_norm.shape, testing_target.shape)

    # model initialization
    backbones = [
        {
            'num_of_time_conv_filters1': 32,
            'num_of_time_conv_filters2': 64,
            'K_t': 3,
            'num_of_cheb_filters': 32,
            'K': 1,
            'cheb_polys': cheb_polys
        },
        {
            'num_of_time_conv_filters1': 32,
            'num_of_time_conv_filters2': 128,
            'K_t': 3,
            'num_of_cheb_filters': 32,
            'K': 1,
            'cheb_polys': cheb_polys
        }
    ]
    net = STGCN(backbones, 128)
    net.initialize(ctx=ctx)

    loss_function = gluon.loss.L2Loss()

    trainer = Trainer(net.collect_params(), optimizer, {'learning_rate': learning_rate})
    training_dataloader = gluon.data.DataLoader(gluon.data.ArrayDataset(training_data_norm, training_target), batch_size=batch_size, shuffle=True)
    validation_dataloader = gluon.data.DataLoader(gluon.data.ArrayDataset(val_data_norm, val_target), batch_size=batch_size, shuffle=False)
    testing_dataloader = gluon.data.DataLoader(gluon.data.ArrayDataset(testing_data_norm, testing_target), batch_size=batch_size, shuffle=False)

    if not os.path.exists('stgcn_params'):
        os.mkdir('stgcn_params')

    train_loss_list, val_loss_list, test_loss_list = train_model(net, training_dataloader, validation_dataloader, testing_dataloader)
