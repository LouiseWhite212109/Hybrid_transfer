### Train model ###
from models import transfer_model
import numpy as np
import torch.nn as nn
import torch
import copy
from time import time
from torch.optim import Adam, lr_scheduler

class EarlyStopping:
    """Early stops the training if validation loss doesn't improve after a given patience."""
    def __init__(self, patience=7, verbose=False, delta=0, path='./result/checkpoint.pt', trace_func=print):
        """
        Args:
            patience (int): How long to wait after last time validation loss improved.
                            Default: 7
            verbose (bool): If True, prints a message for each validation loss improvement. 
                            Default: False
            delta (float): Minimum change in the monitored quantity to qualify as an improvement.
                            Default: 0
            path (str): Path for the checkpoint to be saved to.
                            Default: 'checkpoint.pt'
            trace_func (function): trace print function.
                            Default: print            
        """
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False
        self.val_loss_min = np.Inf
        self.delta = delta
        self.path = path
        self.trace_func = trace_func
        
    def __call__(self, val_loss):
        score = val_loss
        if self.best_score is None:
            self.best_score = score
        elif score < self.best_score:
            self.counter += 1
            self.trace_func(f'EarlyStopping counter: {self.counter} out of {self.patience}')
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            self.counter = 0

class train:
    
    def mape(y_true, y_pred):
        return (torch.sum(torch.div(torch.sub(y_true, y_pred).abs(), y_true.abs())))*100
        # return (torch.sum(((torch.sub(y_true, y_pred).abs()))) / torch.sum(y_true.abs())) * 100
        
    def train_model(training, validation, lr, epochs, model_name, early_stop=5, opt='Adam'):
        t0 = time()
        model = transfer_model.load_model(model_name)
        early_stopping = EarlyStopping(patience=early_stop)
        optimizer = Adam(model.parameters(), lr=lr)
        lr_decay = lr_scheduler.ExponentialLR(optimizer, gamma=0.95)
        train_loader, test_loader = training, validation      
        # Loss Criterion
        criterion = nn.MSELoss()
        train_loss = []
        val_loss = []
        best_train, best_val = 0.0, 0.0
        for epoch in range(1, epochs + 1):
            t1 = time()
            # Train and Validate
            print('epoch:', epoch)
            train_stats = train.train_step(model, criterion, optimizer, train_loader)
            valid_stats = train.valid_step(model, criterion, test_loader)
            train_loss.append(train_stats['loss'])
            val_loss.append(valid_stats['loss'])
            # Keep best model
            if valid_stats['accuracy'] > best_val or (valid_stats['MAE']==best_val and train_stats['accuracy']>=best_train):
                best_train  = train_stats['accuracy']
                print('training accuracy =', float(train_stats['accuracy']), '%')
                best_val    = valid_stats['accuracy']
                print('validation accuracy = ', float(valid_stats['accuracy']), '%')
                print('RMSE = ', float(valid_stats['RMSE']))
                print('MAE = ', float(valid_stats['MAE']))
                best_model_weights = copy.deepcopy(model.state_dict())
            lr_decay.step()
            early_stopping(val_loss)
            if early_stopping.early_stop:
                print("Early stopping")
                break
            print('Time taken for epoch = %ds' % (time() - t1))
        # Load best model and evaluate on test set
        model.load_state_dict(best_model_weights)
        test_stats = train.valid_step(model, criterion, test_loader)
        print("Total time = %ds" % (time() - t0))
        # print('\nBests Model Accuracies: Train: {:4.2f} | Val: {:4.2f} | Test: {:4.2f}'.format(best_train, best_val, test_stats['accuracy']))
        print('\nBest Validation Results: Average Loss: {:4.2f} | Accuracy: {:4.2f} | MAE: {:4.2f} | RMSE: {:4.2f}'.format(test_stats['loss'],
                                                                    test_stats['accuracy'], test_stats['MAE'], test_stats['RMSE']))
        return model, train_loss, val_loss
        
    def valid_step(model, criterion, val_loader):
        model.eval()
        avg_loss = 0.0
        absolute_percentage_error = 0.0
        pe, mae, se = 0.0, 0.0, 0.0
        for i, (x_imgs, labels) in enumerate(val_loader):
            if torch.cuda.is_available():
                x_imgs, labels = x_imgs.cuda(), labels.cuda()
            # forward pass
            output = model(x_imgs)
            loss = criterion(output, labels)
            # gather statistics
            avg_loss += loss.item()        
            mae += torch.sum((abs(output - labels)))
            se += torch.sum((abs(output - labels))**2)
            absolute_percentage_error += train.mape(labels, output)
        rmse = ((se/(len(val_loader.dataset)))**0.5)
        return {'loss' : avg_loss / len(val_loader.dataset), 'accuracy' : 100-(absolute_percentage_error / len(val_loader.dataset)),
                'MAE' : mae / len(val_loader.dataset), 'RMSE' : rmse}
    
    def train_step(model, criterion, optimizer, train_loader):
        model.train()
        avg_loss = 0.0
        absolute_percentage_error = 0.0
        for i, (x_imgs, labels) in enumerate(train_loader):
            if torch.cuda.is_available():
                x_imgs, labels = x_imgs.cuda(), labels.cuda()
            optimizer.zero_grad()
            # forward pass
            pred = model(x_imgs)
            loss = criterion(pred, labels.float())
            loss.backward()
            optimizer.step()
            # gather statistics
            avg_loss += loss.item()
            absolute_percentage_error += train.mape(labels, pred)
        return {'loss': avg_loss / len(train_loader.dataset), 'accuracy': 100-(absolute_percentage_error / len(train_loader.dataset))}
    
    def test_model(model, test_loader):
        criterion = nn.MSELoss()
        test_stats = train.valid_step(model, criterion, test_loader)
        return test_stats