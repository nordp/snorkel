import cPickle as pkl
import numpy as np
import tensorflow as tf
import tensorflow.contrib.layers as layers

from snorkel.learning import NoiseAwareModel
from tensorflow.python.ops.functional_ops import map_fn
from time import asctime, time


class SymbolTable:
    """Wrapper for dict to encode unknown symbols"""
    def __init__(self, starting_symbol=2): 
        self.s = starting_symbol
        self.d = dict()

    def get(self, w):
        if w not in self.d:
            self.d[w] = self.s
            self.s += 1
        return self.d[w]

    def lookup(self, w):
        return self.d.get(w, 1)


def time_str():
    return asctime().replace(' ', '-').replace(':', '-')


class reLSTM(NoiseAwareModel):

    def __init__(self, save_file=None, **kwargs):
        """LSTM for relation extraction"""
        self.mx_len     = None
        self.prediction = None
        self.session    = None
        # Define input layers
        self.sentences = tf.placeholder(tf.int32, [None, None])
        self.sentence_length = tf.placeholder(tf.int32, [None])
        self.labels = tf.placeholder(tf.int32, [None])
        # Load model
        if save_file is not None:
            self.load(save_file)
        # Super constructor
        super(reLSTM, self).__init__(**kwargs)

    def _gen_marks(self, l, h, idx):
        """Produce markers based on argument positions"""
        return [(l, "{}{}".format('[[', idx)), (h+1, "{}{}".format(idx, ']]'))]

    def _mark_sentence(self, s, mids):
        """Insert markers around relation arguments in word sequence
        Example: Then Barack married Michelle.  
             ->  Then [[0 Barack 0]] married [[1 Michelle 1]].
        """
        marks = sorted([y for m in mids for y in self._mark(*m)], reverse=True)
        x = list(s)
        for k, v in marks:
            x.insert(k, v)
        return x

    def _preprocess_data(self, candidates):
        pass

    def _make_tensor(self, x, y):
        """Construct input tensor with padding"""
        batch_size = len(x)
        tx = np.zeros((self.mx_len, batch_size), dtype=np.int32)
        tlen = np.zeros(batch_size, dtype=np.int32)
        # Pad or trim each x
        # TODO: fix for arguments outside max length
        for k, u in enumerate(x):
            lu = min(len(u), self.mx_len)
            tx[0:lu, k] = u[0:lu]
            tx[lu:, k] = 0
            tlen[k] = lu
        return tx, np.ravel(y), tlen

    def _build_lstm(self, sents, sent_lens, labels, lr, n_hidden, dropout, n_v):
        pass

    def train(self, candidates, n_epochs=10, lr=0.01, n_hidden=20,
        batch_size=100, rebalance=False, dropout_rate=None,
        max_sentence_length=None, n_print=50, model_name=None):
        """ Train LSTM model """
        verbose = n_print > 0
        if verbose:
            print("[reLSTM] Layers={} LR={}".format(n_hidden, lr))
            print("[reLSTM] Begin preprocessing")
            st = time()
        # Text preprocessing
        train_x, train_y, words, labels = self._preprocess_data(candidates)
        # Build model
        dropout = None if dropout_rate is None else tf.constant(dropout_rate)
        self.prediction, cost, train_fn = build_lstm(
            self.sentences, self.sentence_length, self.labels, lr, n_hidden,
            dropout, words.current_symbol + 1
        )
        # Get training counts 
        if rebalance:
            pos, neg = np.where(train_y == 1)[0], np.where(train_y == -1)[0]
            k = min(len(pos), len(neg))
            idxs = np.concatenate((
                np.random.choice(pos, size=k, replace=False),
                np.random.choice(neg, size=k, replace=False)
            ))
        else:
            idxs = np.ravel(xrange(len(train_y)))
        # Shuffle training data
        np.random.shuffle(idxs)
        train_x, train_y = [train_x[j] for j in idxs], train_y[idxs]
        # Get max sentence size
        self.mx_len = max(train_x, lambda x: len(x))
        self.mx_len = int(min(self.mx_len, max_sentence_length or float('Inf')))
        # Get eval set
        #(tx,ty,t_lus) = make_our_tensor(train_x[0:args.max_eval_set], train_y[0:args.max_eval_set], max_sentence)
        # Run mini-batch SGD
        batch_size = min(batch_size, len(train_x))
        self.session = tf.Session()
        if verbose:
            print("[reLSTM] Preprocessing done ({0:.2f}s)".format(time()-st))
            st = time()
            print("[reLSTM] Begin training\tEpochs={0}\tBatch={1}".format(
                n_epochs, batch_size
            ))
        self.session.run(tf.global_variables_initializer())
        for t in range(n_epochs):
            epoch_error = 0
            for i in range(0, len(train_x), batch_size):
                # Get batch tensors
                x_batch, y_batch, x_batch_lens = self._make_tensor(
                    train_x[i:i+batch_size], train_y[i:i+batch_size],
                )
                # Run training step and evaluate cost function                  
                epoch_error, _ += self.session.run([cost, train_fn], {
                    self.sentences: x_batch,
                    self.sentence_length: x_batch_lens,
                    self.labels: y_batch,
                })
            # Print training stats
            if verbose and (t % n_print == 0 or t == (n_epochs - 1)):
                print("[reLSTM] Epoch {0} ({1:.2f}s)\tError={2:.6f}".format(
                    t, time.time() - st, epoch_error
                ))
        # Save model
        self.save(model_name)        
        if verbose:
            print("[reLSTM] Training done ({0:.2f}s)")
            print("[reLSTM] Model saved in file: {}".format(model_name))

    def marginals(self, test_candidates):
        if any(z is None for z in [self.session, self.prediction]):
            raise Exception("[reLSTM] Model not defined")
        test_x, _, _, _ = self._preprocess_data(test_candidates)
        x, _, x_lens = self._make_tensor(test_x, )
        return np.ravel(self.session.run([self.prediction], {
            self.sentences = x,
            self.sentence_length = x_lens,
            self.labels = None
        }))

    def save(self, model_name=None):
        """Save model"""
        model_name = model_name or ("relstm_" + time_str())
        saver = tf.train.Saver()
        saver.save(self.session, "./{0}.session".format(model_name))
        with open("./{0}.info".format(model_name)) as f:
            # TODO: save input, prediction, mx_len
            pass


    def load(self, model_name):
        """Load model"""
        # TODO: load info and session file
        pass
