from train import train
import matplotlib.pyplot as plt
import numpy as np
from models import transfer_model
from torchvision import models
from torchsummary import summary
import torch
import torch.nn as nn
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, Sequential
import os
from skimage import io as skio
from misc_functions import functions
from torchvision import transforms
from torch.utils.data import DataLoader, Dataset, TensorDataset

class CustomImageDataset:
    def __init__(self, dataset, transform=None):
        self.dataset = dataset
        self.transform = transform
        
    def __len__(self):
        return len(self.dataset[0])
    
    def __getitem__(self, index):
        x = self.dataset[0][index]
        if self.transform:
            x = self.transform(x)
        # y = self.dataset[1][index]
        return x
    

def load_data():
    from misc_functions import functions
    fcts = functions() 
    training_data = fcts.load('./Matlab/train_test_his/training_data.mat', 'training').astype(np.float16)   
    testing_data = fcts.load('./Matlab/train_test_his/testing_data.mat', 'testing').astype(np.float16)
    training_targets = fcts.load('./Matlab/train_test_his/training_rul.mat', 'rul')
    testing_targets = fcts.load('./Matlab/train_test_his/testing_rul.mat', 'rul')
    
    training_data = training_data.reshape([training_data.shape[0], training_data.shape[1], 1])
    testing_data = testing_data.reshape([testing_data.shape[0], testing_data.shape[1], 1])

    return training_data, training_targets, testing_data, testing_targets

def load_images():
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                              std=[0.229, 0.224, 0.225])
        ])
    train_data = skio.imread('./Matlab/train_test_images\\training_data.tif')
    test_data = skio.imread('./Matlab/train_test_images\\testing_data.tif')

    train_targets = ld.load('./Matlab/train_test_images\\training_targets.mat', 'rul').astype(np.int16)
    test_targets = ld.load('./Matlab/train_test_images\\testing_targets.mat', 'rul').astype(np.int16)
    
    train_data = CustomImageDataset(dataset=(train_data, train_targets), transform=transform)
    test_data = CustomImageDataset(dataset=(test_data, test_targets), transform=transform)
    # Build dataloader
    train_loader = DataLoader(train_data, shuffle=False, batch_size=1)
    test_loader = DataLoader(test_data, shuffle=False, batch_size=1)
    
    return train_loader, test_loader


class Identity(nn.Module):
    def __init__(self):
        super(Identity, self).__init__()
        
    def forward(self, x):
        return(x)

if __name__ == "__main__":
    ld = functions()
    epochs = 10
    batch_size = 256
    learning_rate = 0.001
    early_stop = 5
    model_name = 'alexnet'
    '''
    Available models:
        - resnet18;
        - resnet50;
        - resnet152;
        - vgg11;
        - googlenet;
        - alexnet
    '''
    
    ## Loading the transferred network
    train_data, test_data = load_images()
    
    model = models.alexnet(pretrained=True)
    for param in model.parameters():
        param.requires_grad = False 
    num_features = model.classifier[1].in_features
    model.classifier = Identity()
    summary(model,(3,224,224))
    
    tl_output = torch.empty(1,num_features).cuda()
    for i, x in enumerate(test_data): 
        x = x.cuda()
        tl_output = torch.cat((tl_output, model(x)))
        
    
    ## Training the LSTM
    training_data, training_targets, testing_data, testing_targets = load_data()
    
    lstm = keras.Sequential()
    lstm.add(keras.Input(shape=(training_data.shape[1], 1)))
    lstm.add(layers.LSTM(512, activation='relu', return_sequences=True, name='lstm_1'))
    lstm.add(layers.LSTM(256, activation='relu', return_sequences=True, name='lstm_2'))
    lstm.add(layers.Flatten())
    lstm.add(layers.Dropout(0.3))
    lstm.add(layers.Dense(256, activation='relu', name='dense_1'))
    lstm.add(layers.Dense(512, activation='relu', name='dense_2'))
    lstm.add(layers.Dense(1000, name='dense_3'))
    lstm.add(layers.Dense(1, name='output_layer'))
    
    checkpoint_filepath = './chkpt/checkpoint.index'
    checkpoint = tf.keras.callbacks.ModelCheckpoint(filepath=checkpoint_filepath, save_weights_only=True,
                                                    monitor='val_loss', mode='min', save_best_only='True')
    
    steps_per_epochs = np.ceil(training_data.shape[0] / batch_size)
    lr_schedule = keras.optimizers.schedules.ExponentialDecay(initial_learning_rate=learning_rate, 
                                                    decay_steps=10*steps_per_epochs, decay_rate=0.95)
    opt = keras.optimizers.Adam(learning_rate=lr_schedule)
    lstm.compile(optimizer=opt, loss='mape', metrics=['mae', 'mse'])
    lstm.summary()
    hist = lstm.fit(training_data, training_targets, batch_size=batch_size, epochs=epochs,
              validation_data = (testing_data, testing_targets), shuffle=True, callbacks=[checkpoint])
    
    plt.plot(hist.history['loss'], label='training loss')
    plt.plot(hist.history['val_loss'], label='validation loss')
    plt.xlabel('epochs')
    plt.ylabel('mean absolute percentage error loss')
    plt.legend()
    
    latest = tf.train.latest_checkpoint(os.path.dirname(checkpoint_filepath))
    lstm.load_weights(checkpoint_filepath)
    lstm.evaluate(testing_data, testing_targets)
    lstm.pop() # removes the final output layer of the LSTM
    lstm.summary()
    
    lstm_output = np.array(lstm.predict(training_data))
    lstm_output = torch.tensor(lstm_output)

    ## Adding a decoder layer
    ### TO THE SAME FOR THE TESTING DATA ###
    parallel_data = torch.cat((lstm_output, tl_output))
    parallel_targets = training_targets
    
    decoder = keras.Sequential()
    decoder.add(keras.Input(shape=(1000+num_features, 1)))
    decoder.add(layers.Dense(1024, activation='relu'))
    decoder.add(layers.Dense(512, activation='relu'))
    decoder.add(layers.Dense(128, activation='relu'))
    decoder.add(layers.Dense(1))
    
    decoder.compile(optimizer=opt, loss='mape', metrics=['mae', 'mse'])
    hist2 = decoder.fit(parallel_data, parallel_targets, batch_size=batch_size, epochs=epochs,
                        shuffle=True, callbacks=[checkpoint_filepath])
    
    
    
    
    
    
    
    
    