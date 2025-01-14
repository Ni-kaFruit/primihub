from primihub.FL.model.logistic_regression.homo_lr_base import LRModel
import numpy as np
from os import path
import pandas as pd
import copy
from primihub.FL.proxy.proxy import ServerChannelProxy
from primihub.FL.proxy.proxy import ClientChannelProxy
import logging

proxy_server_arbiter = ServerChannelProxy("10090")  # guest接收arbiter消息
proxy_server_host = ServerChannelProxy("10093")  # guest接收Host消息
proxy_client_arbiter = ClientChannelProxy("127.0.0.1", "10094")  # guest发送消息给arbiter
proxy_client_host = ClientChannelProxy("127.0.0.1", "10095")  # guest发送消息给host

path = path.join(path.dirname(__file__), '../../../tests/data/wisconsin.data')


def get_logger(name):
    LOG_FORMAT = "[%(asctime)s][%(filename)s:%(lineno)d][%(levelname)s] %(message)s"
    DATE_FORMAT = "%m/%d/%Y %H:%M:%S %p"
    logging.basicConfig(level=logging.DEBUG,
                        format=LOG_FORMAT, datefmt=DATE_FORMAT)
    logger = logging.getLogger(name)
    return logger


logger = get_logger("Homo-LR-Guest")


def data_process():
    X1 = pd.read_csv(path, header=None)
    y1 = X1.iloc[:, -1]
    yy = copy.deepcopy(y1)
    # 处理标签
    for i in range(len(yy.values)):
        if yy[i] == 2:
            yy[i] = 0
        else:
            yy[i] = 1
    X1 = X1.iloc[:, :-1]
    return X1, yy


class Guest:
    def __init__(self, X, y):
        self.X = X
        self.y = y
        self.model = LRModel(X, y)
        self.iter = None
        self.need_one_vs_rest = None
        self.need_encrypt = False
        self.lr = None
        self.batch_size = None

    def predict(self, data=None):
        if self.need_one_vs_rest:
            pass
        else:
            pre = self.model.predict(data)
        return pre

    def fit_binary(self, X, y):
        # if self.need_encrypt == True:
        #     model_param = Utils.encrypt_vector(self.public_key, self.global_model.theta)
        #     neg_one = self.public_key.encrypt(-1)
        #
        #     for e in range(1):  # 10为本地epoch大小
        #         print("start epoch ", e)
        #         # 每一轮都随机挑选batch_size大小的训练数据进行训练
        #         idx = np.arange(X.shape[0])
        #         batch_idx = np.random.choice(idx, self.batch_size, replace=False)
        #         x = X[batch_idx]
        #         x = np.concatenate((np.ones((x.shape[0], 1)), x), axis=1)
        #         y = y[batch_idx].values.reshape((-1, 1))
        #         # 在加密状态下求取加密梯度
        #         batch_encrypted_grad = x.transpose() * (
        #                 0.25 * x.dot(model_param) + 0.5 * y.transpose() * neg_one)
        #         encrypted_grad = batch_encrypted_grad.sum(axis=1) / y.shape[0]
        #
        #         for j in range(len(model_param)):
        #             model_param[j] -= self.lr * encrypted_grad[j]
        #
        #     # weight_accumulators = []
        #     # for j in range(len(self.local_model.encrypt_weights)):
        #     #     weight_accumulators.append(self.local_model.encrypt_weights[j] - original_w[j])
        #     return model_param
        # plaintext
        self.model.theta = self.model.fit(X, y, eta=self.lr)
        self.model.theta = list(self.model.theta)
        return self.model.theta

    def batch_generator(self, all_data, batch_size, shuffle=True):
        """
        :param all_data : incluing features and label
        :param batch_size: number of samples in one batch
        :param shuffle: Whether to disrupt the order
        :return:iterator to generate every batch of features and labels
        """
        # Each element is a numpy array
        all_data = [np.array(d) for d in all_data]
        data_size = all_data[0].shape[0]
        logger.info("data_size: {}".format(data_size))
        if shuffle:
            p = np.random.permutation(data_size)
            all_data = [d[p] for d in all_data]
        batch_count = 0
        while True:
            # The epoch completes, disrupting the order once
            if batch_count * batch_size + batch_size > data_size:
                batch_count = 0
                if shuffle:
                    p = np.random.permutation(data_size)
                    all_data = [d[p] for d in all_data]
            start = batch_count * batch_size
            end = start + batch_size
            batch_count += 1
            yield [d[start: end] for d in all_data]


if __name__ == "__main__":
    conf = {'iter': 2,
            'lr': 0.01,
            'batch_size': 200,
            'epoch': 3}
    # load train data
    X, label = data_process()
    X = LRModel.normalization(X)
    count = X.shape[0]
    batch_num = count // conf['batch_size'] + 1

    client_guest = Guest(X, label)
    client_guest.iter = conf['iter']
    client_guest.lr = conf['lr']
    client_guest.batch_size = conf['batch_size']
    batch_gen_guest = client_guest.batch_generator([X, label], conf['batch_size'])
    proxy_server_arbiter.StartRecvLoop()

    # Send guest data weight to arbiter
    guest_data_weight = conf['batch_size']
    proxy_client_arbiter.Remote(guest_data_weight, "guest_data_weight")

    for i in range(conf['epoch']):
        logger.info("######### epoch %s ######### start " % i)
        for j in range(batch_num):
            batch_x, batch_y = next(batch_gen_guest)
            logger.info("batch_host_x.shape:{}".format(batch_x.shape))
            logger.info("batch_host_y.shape:{}".format(batch_y.shape))
            guest_param = client_guest.fit_binary(batch_x, batch_y)
            proxy_client_arbiter.Remote(guest_param, "guest_param")
            client_guest.model.theta = proxy_server_arbiter.Get("global_guest_model_param")
        logger.info("######### epoch %s ######### done " % i)
    logger.info("guest training process done!")

    proxy_server_arbiter.StopRecvLoop()
