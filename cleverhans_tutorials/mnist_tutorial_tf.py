"""
This tutorial shows how to generate adversarial examples using FGSM
and train a model using adversarial training with TensorFlow.
It is very similar to mnist_tutorial_keras_tf.py, which does the same
thing but with a dependence on keras.
The original paper can be found at:
https://arxiv.org/abs/1412.6572
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import tensorflow as tf
from tensorflow.python.platform import flags
import logging

import os
import sys
lib_path = os.path.abspath(os.path.join(__file__, '../..'))
sys.path.append(lib_path)
from cleverhans.loss import LossCrossEntropy
from cleverhans.utils_mnist import data_mnist
from cleverhans.utils_tf_pr_mnist import train, model_eval, tf_model_load
from cleverhans.attacks import FastGradientMethod, BasicIterativeMethod, MomentumIterativeMethod
from cleverhans.utils import AccuracyReport, set_log_level
from cleverhans_tutorials.tutorial_models import ModelBasicCNN

FLAGS = flags.FLAGS
flags.DEFINE_integer('nb_filters', 64, 'Model size multiplier')
flags.DEFINE_integer('nb_epochs', 10000, 'Number of epochs to train model')
flags.DEFINE_integer('batch_size', 128, 'Size of training batches')
flags.DEFINE_float('learning_rate', 0.001, 'Learning rate for training')
flags.DEFINE_bool('clean_train', True, 'Train on clean examples')
flags.DEFINE_bool('backprop_through_attack', False,
                  ('If True, backprop through adversarial example '
                   'construction process during adversarial training'))

os.environ['CUDA_VISIBLE_DEVICES'] = '3'

n_input = 28*28
numColorOutput = 3  # Always 3 for MNIST and Fashion MNIST
type = 'single'
type = 'multiple'
type = 'adv_train'
mode = "nonpr"
# mode = "train_test"
#mode = "yinyang"
file = "/home/labiai/Jiacang/Experiments/tmp/data/mnist"
save_dir = '/home/labiai/Jiacang/Experiments/tmp/pr/'+type+'/mnist_'+str(FLAGS.nb_epochs)+'_'+mode+'/'
# file = "/home/labiai/Jiacang/Experiments/tmp/data/fashion_mnist"
# save_dir = '/home/labiai/Jiacang/Experiments/tmp/pr/'+type+'/fmnist_'+str(FLAGS.nb_epochs)+'_'+mode+'/'

print("file:", file)
filename = 'network'

config = tf.ConfigProto(
device_count = {'GPU': 1}
)
def mnist_tutorial(train_start=0, train_end=60000, test_start=0,
                   test_end=10000, nb_epochs=6, batch_size=128,
                   learning_rate=0.001,
                   clean_train=True,
                   testing=False,
                   backprop_through_attack=False,
                   nb_filters=64, num_threads=None,
                   label_smoothing=0.1):
    """
    MNIST cleverhans tutorial
    :param train_start: index of first training set example
    :param train_end: index of last training set example
    :param test_start: index of first test set example
    :param test_end: index of last test set example
    :param nb_epochs: number of epochs to train model
    :param batch_size: size of training batches
    :param learning_rate: learning rate for training
    :param clean_train: perform normal training on clean examples only
                        before performing adversarial training.
    :param testing: if true, complete an AccuracyReport for unit tests
                    to verify that performance is adequate
    :param backprop_through_attack: If True, backprop through adversarial
                                    example construction process during
                                    adversarial training.
    :param clean_train: if true, train on clean examples
    :param label_smoothing: float, amount of label smoothing for cross entropy
    :return: an AccuracyReport object
    """

    # Object used to keep track of (and return) key accuracies
    report = AccuracyReport()

    # Set TF random seed to improve reproducibility
    tf.set_random_seed(1234)

    # Set logging level to see debug information
    set_log_level(logging.DEBUG)

    # Create TF session
    if num_threads:
        config_args = dict(intra_op_parallelism_threads=1)
    else:
        config_args = {}
    sess = tf.Session(config=tf.ConfigProto(device_count = {'GPU': 2}))

    # Get MNIST test data
    x_train, y_train, x_test, y_test = data_mnist(file, train_start=train_start,
                                                  train_end=train_end,
                                                  test_start=test_start,
                                                  test_end=test_end)
    # Use Image Parameters
    img_rows, img_cols, nchannels = x_train.shape[1:4]
    nb_classes = y_train.shape[1]

    # Define input TF placeholder
    x = tf.placeholder(tf.float32, shape=(None, img_rows, img_cols,
                                          nchannels))
    y = tf.placeholder(tf.float32, shape=(None, nb_classes))

    # Train an MNIST model
    train_params = {
        'nb_epochs': nb_epochs,
        'batch_size': batch_size,
        'learning_rate': learning_rate,
        'train_dir': save_dir,
        'filename': filename,
        'numColorOutput': numColorOutput
    }
    eval_params = {'batch_size': batch_size}
    fgsm_params = {
        'eps': 0.3,
        'clip_min': 0.,
        'clip_max': 1.
    }
    rng = np.random.RandomState([2017, 8, 30])

    def do_eval(preds, x_set, y_set, report_key, is_adv=None):
        acc = model_eval(sess, x, y, preds, x_set, y_set, args=eval_params)
        setattr(report, report_key, acc)
        if is_adv is None:
            report_text = None
        elif is_adv:
            report_text = 'adversarial'
        else:
            report_text = 'legitimate'
        if report_text:
            print('Test accuracy on %s examples: %0.4f' % (report_text, acc))

    if clean_train:
        model = ModelBasicCNN('model1', nb_classes, nb_filters)
        preds = model.get_logits(x)
        loss = LossCrossEntropy(model, smoothing=label_smoothing)

        def evaluate():
            do_eval(preds, x_test, y_test, 'clean_train_clean_eval', False)

        train(sess, loss, x, y, x_train, y_train, evaluate=evaluate,
              args=train_params, rng=rng, var_list=model.get_params())

        # Calculate training error
        if testing:
            do_eval(preds, x_train, y_train, 'train_clean_train_clean_eval')

        # Initialize the Fast Gradient Sign Method (FGSM) attack object and
        # graph
        fgsm = FastGradientMethod(model, sess=sess)
        adv_x = fgsm.generate(x, **fgsm_params)
        preds_adv = model.get_logits(adv_x)

        # Evaluate the accuracy of the MNIST model on adversarial examples
        do_eval(preds, x_test, y_test, 'clean_train_adv_eval', True)

        # Calculate training error
        if testing:
            do_eval(preds_adv, x_train, y_train, 'train_clean_train_adv_eval')

    '''
    print('Repeating the process, using adversarial training')

    # Create a new model and train it to be robust to FastGradientMethod
    model2 = ModelBasicCNN('model2', nb_classes, nb_filters)
    fgsm2 = FastGradientMethod(model2, sess=sess)

    def attack(x):
        return fgsm2.generate(x, **fgsm_params)

    loss2 = LossCrossEntropy(model2, smoothing=label_smoothing, attack=attack)
    preds2 = model2.get_logits(x)
    adv_x2 = attack(x)

    if not backprop_through_attack:
        # For the fgsm attack used in this tutorial, the attack has zero
        # gradient so enabling this flag does not change the gradient.
        # For some other attacks, enabling this flag increases the cost of
        # training, but gives the defender the ability to anticipate how
        # the atacker will change their strategy in response to updates to
        # the defender's parameters.
        adv_x2 = tf.stop_gradient(adv_x2)
    preds2_adv = model2.get_logits(adv_x2)

    def evaluate2():
        # Accuracy of adversarially trained model on legitimate test inputs
        do_eval(preds2, x_test, y_test, 'adv_train_clean_eval', False)
        # Accuracy of the adversarially trained model on adversarial examples
        do_eval(preds2_adv, x_test, y_test, 'adv_train_adv_eval', True)

    saveFileNum = 50
    # saveFileNum = 500
    # saveFileNum = 1000
    model_path = os.path.join(save_dir, filename+"-"+str(saveFileNum))

    print("Trying to load trained model from: " + model_path)
    if os.path.exists(model_path + ".meta"):
        tf_model_load(sess, model_path)
        print("Load trained model")
    else:
        # Perform and evaluate adversarial training
        train(sess, loss2, x, y, x_train, y_train, evaluate=evaluate2,
              args=train_params, rng=rng, var_list=model2.get_params(),
              save=True)

    # Calculate training errors
    if testing:
        do_eval(preds2, x_train, y_train, 'train_adv_train_clean_eval')
        do_eval(preds2_adv, x_train, y_train, 'train_adv_train_adv_eval')

    # Evaluate the accuracy of the MNIST model on adversarial examples
    do_eval(preds2_adv, x_test, y_test, 'adv_train_adv_eval', True)
    '''

    return report


def main(argv=None):
    mnist_tutorial(nb_epochs=FLAGS.nb_epochs, batch_size=FLAGS.batch_size,
                   learning_rate=FLAGS.learning_rate,
                   clean_train=FLAGS.clean_train,
                   backprop_through_attack=FLAGS.backprop_through_attack,
                   nb_filters=FLAGS.nb_filters)


if __name__ == '__main__':

    with tf.device('/GPU:0'):
        tf.app.run()
